import datetime
import time
from typing import Callable, TypeVar

import tmt.log
from tmt.container import container
from tmt.utils import GeneralError

T = TypeVar('T')

# Default for wait()-related options
DEFAULT_WAIT_TICK: float = 30.0
DEFAULT_WAIT_TICK_INCREASE: float = 1.0

# A type for callbacks given to wait()
WaitCheckType = Callable[[], T]


class WaitingIncompleteError(GeneralError):
    """
    Waiting incomplete
    """

    def __init__(self) -> None:
        super().__init__('Waiting incomplete')


class WaitingTimedOutError(GeneralError):
    """
    Waiting ran out of time
    """

    def __init__(
        self,
        check: 'WaitCheckType[T]',
        timeout: datetime.timedelta,
        check_success: bool = False,
    ) -> None:
        if check_success:
            super().__init__(
                f"Waiting for condition '{check.__name__}' succeeded but took too much time "
                f"after waiting {timeout}."
            )

        else:
            super().__init__(
                f"Waiting for condition '{check.__name__}' timed out after waiting {timeout}."
            )

        self.check = check
        self.timeout = timeout
        self.check_success = check_success


class Deadline:
    """
    A point in time when something should end.

    Instead of raw timeouts that represent remaining time, we deal more
    with points when things should stop. Timeouts must be updated
    regularly, decreased as time progresses, while deadlines are set
    and can be easily tested.
    """

    # `_deadline` holds the timestamp of when things should stop, while
    # `_now` holds the current "now" as established by the context
    # manager `Deadline` is. When entered, `_now` is updated, and is
    # used by all remaining methods instead of calling `monotonic()`
    # all the time. This makes the accounting and logging stable because
    # the timestamps and deltas will not differ as long as printed out
    # in the same context.
    _deadline: float
    _now: float

    #: The original timeout that populated this deadline.
    original_timeout: datetime.timedelta

    def __init__(self, timeout: datetime.timedelta) -> None:
        self.original_timeout = timeout

        self._now = time.monotonic()
        self._deadline = self._now + timeout.total_seconds()

    def __repr__(self) -> str:
        return f'<Deadline: now={self._now} deadline={self._deadline}>'

    @classmethod
    def from_delta(cls, timeout: datetime.timedelta) -> 'Deadline':
        """
        Create a deadline from a delta.
        """

        return Deadline(timeout)

    @classmethod
    def from_seconds(cls, timeout: float) -> 'Deadline':
        """
        Create a deadline from the number of seconds of a timeout.
        """

        return Deadline(datetime.timedelta(seconds=timeout))

    @property
    def is_due(self) -> bool:
        """
        ``True`` when the deadline has been reached, ``False`` otherwise.
        """

        return self._now >= self._deadline

    @property
    def time_left(self) -> datetime.timedelta:
        """
        The remaining time left.

        .. note::

            The value will be negative when the deadline has been
            reached already.
        """

        return datetime.timedelta(seconds=self._deadline - self._now)

    @property
    def time_over(self) -> datetime.timedelta:
        """
        The time past the deadline.

        .. note::

            The value will be negative when the deadline has not been
            reached yet.
        """

        return datetime.timedelta(self._now - self._deadline)

    def __enter__(self) -> 'Deadline':
        self._now = time.monotonic()
        return self

    def __exit__(self, *args: object) -> None:
        pass


@container
class Waiting:
    """
    Context describing how to wait for a condition with limited deadline.
    """

    #: The deadline that limits the waiting.
    deadline: Deadline

    #: How many seconds to wait between two consecutive checks whether
    #: the condition is satisfied.
    tick: float = DEFAULT_WAIT_TICK

    #: A multiplier applied to :py:attr:`tick` after every attempt.
    tick_increase: float = DEFAULT_WAIT_TICK_INCREASE

    def wait(self, check: WaitCheckType[T], logger: tmt.log.Logger) -> T:
        """
        Wait for a condition to become true.

        To test the condition state, a ``check`` callback is called every
        :py:attr:`tick` seconds until ``check`` reports a success. The
        callback may:

        * decide the condition has been fulfilled. This is a successful
          outcome, ``check`` shall then simply return, and waiting ends.
          Or,
        * decide more time is needed. This is not a successful outcome,
          ``check`` shall then raise :py:class:`WaitingIncomplete`
          exception, and ``wait()`` will try again later.

        ``wait()`` will also stop and quit if tmt has been interrupted.

        :param check: a callable responsible for testing the condition.
            Accepts no arguments. To indicate more time and attempts are
            needed, the callable shall raise :py:class:`WaitingIncomplete`,
            otherwise it shall return without exception. Its return
            value will be returned by ``wait()`` itself. All other
            exceptions raised by ``check`` will be propagated upstream,
            terminating the wait.
        :returns: value returned by ``check`` reporting success.
        :raises WaitingTimedOutError: when time quota has been consumed.
        :raises Interrupted: when tmt has been interrupted.
        """

        from tmt.utils.signals import INTERRUPT_PENDING, Interrupted

        def _check_interrupted() -> None:
            if INTERRUPT_PENDING.is_set():
                logger.debug('wait', f"'{check.__name__}' interrupted")

                raise Interrupted

        logger.debug(
            'wait',
            f"waiting for condition '{check.__name__}'"
            f" with timeout {self.deadline.original_timeout},"
            f" deadline in {self.deadline.original_timeout.total_seconds()} seconds,"
            f" checking every {self.tick:.2f} seconds",
        )

        while True:
            _check_interrupted()

            with self.deadline:
                if self.deadline.is_due:
                    logger.debug(
                        'wait',
                        f"'{check.__name__}' did not succeed,"
                        f" {self.deadline.time_over.total_seconds():.2f} over quota",
                    )

                    raise WaitingTimedOutError(check, self.deadline.original_timeout)

            try:
                ret = check()

                # Make sure interrupt is honored.
                _check_interrupted()

                # Perform one extra check: if `check()` succeeded, but took more time than
                # allowed, it should be recognized as a failed waiting too.
                with self.deadline:
                    if self.deadline.is_due:
                        logger.debug(
                            'wait',
                            f"'{check.__name__}' finished successfully but took too much time,"
                            f" {self.deadline.time_over.total_seconds():.2f} over quota",
                        )

                        raise WaitingTimedOutError(
                            check, self.deadline.original_timeout, check_success=True
                        )

                    logger.debug(
                        'wait',
                        f"'{check.__name__}' finished successfully,"
                        f" {self.deadline.time_left.total_seconds():.2f} seconds left",
                    )

                    return ret

            except WaitingIncompleteError:
                # Update timestamp for more accurate logging - check() could have taken minutes
                # to complete, using the pre-check timestamp for logging would be misleading.
                with self.deadline:
                    logger.debug(
                        'wait',
                        f"'{check.__name__}' still pending,"
                        f" {self.deadline.time_left.total_seconds():.2f} seconds left,"
                        f" current tick {self.tick:.2f} seconds",
                    )

                time.sleep(self.tick)

                self.tick *= self.tick_increase

                continue
