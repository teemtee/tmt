import dataclasses
import functools
from collections.abc import Iterator
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from typing import TYPE_CHECKING, Any, Generic, Optional, TypeVar

from tmt.log import Logger

if TYPE_CHECKING:
    from tmt._compat.typing import Self
    from tmt.steps.provision import Guest


TaskResultT = TypeVar('TaskResultT')


@dataclasses.dataclass
class Task(Generic[TaskResultT]):
    """
    A base class for queueable actions.

    The class provides not just the tracking, but the implementation of the said
    action as well. Child classes must implement their action functionality in
    :py:meth:`go`.

    .. note::

        This class and its subclasses must provide their own ``__init__``
        methods, and cannot rely on :py:mod:`dataclasses` generating one. This
        is caused by subclasses often adding fields without default values,
        and ``dataclasses`` module does not allow non-default fields to be
        specified after those with default values. Therefore initialize fields
        to their defaults "manually".
    """

    #: A logger to use for logging events related to the outcome.
    logger: Logger

    result: Optional[TaskResultT]

    #: Guest on which the phase was executed. May be unset, some tasks
    #: may handle multiguest actions on their own.
    guest: Optional['Guest']

    #: If set, an exception was raised by the running task, and the exception
    #: is saved in this field.
    exc: Optional[Exception]

    #: If set, the task raised :py:class:`SystemExit` exception, and wants to
    #: terminate the run completely.
    requested_exit: Optional[SystemExit]

    # Custom yet trivial `__init__` is necessary, see note in `tmt.queue.Task`.
    def __init__(self, logger: Logger, **kwargs: Any) -> None:
        self.logger = logger

        self.result = kwargs.get('result', None)
        self.guest = kwargs.get('guest', None)
        self.exc = kwargs.get('exc', None)
        self.requested_exit = kwargs.get('requested_exit', None)

    @property
    def name(self) -> str:
        """
        A name of this task.

        Left for child classes to implement, because the name depends on the
        actual task.
        """

        raise NotImplementedError

    def go(self) -> Iterator['Self']:
        """
        Perform the task.

        Called by :py:class:`Queue` machinery to accomplish the task.

        :yields: instances of the same class, describing invocations of the
            task and their outcome. The task might be executed multiple times,
            depending on how exactly it was queued, and method would yield
            corresponding results.
        """

        raise NotImplementedError


TaskT = TypeVar('TaskT', bound='Task')  # type: ignore[type-arg]


def prepare_loggers(logger: Logger, labels: list[str]) -> dict[str, Logger]:
    """
    Create loggers for a set of labels.

    Guests are assumed to be a group a phase would be executed on, and
    therefore their labels need to be set, to provide context, plus their
    labels need to be properly aligned for more readable output.
    """

    loggers: dict[str, Logger] = {}

    # First, spawn all loggers, and set their labels if needed.
    # Don't bother with labels if there's just a single guest.
    for label in labels:
        new_logger = logger.clone()

        if len(labels) > 1:
            new_logger.labels.append(label)

        loggers[label] = new_logger

    # Second, find the longest label, and instruct all loggers to pad their
    # labels to match this length. This should create well-indented messages.
    max_label_span = max(new_logger.labels_span for new_logger in loggers.values())

    for new_logger in loggers.values():
        new_logger.labels_padding = max_label_span

    return loggers


@dataclasses.dataclass
class GuestlessTask(Task[TaskResultT]):
    """
    A task not assigned to a particular set of guests.

    An extension of the :py:class:`Task` class, provides a quite generic wrapper
    for the actual task which takes care of catching exceptions and proper
    reporting.
    """

    # Custom yet trivial `__init__` is necessary, see note in `tmt.queue.Task`.
    def __init__(self, logger: Logger, **kwargs: Any) -> None:
        super().__init__(logger, **kwargs)

    def run(self, logger: Logger) -> TaskResultT:
        """
        Perform the task.

        Called once from :py:meth:`go`. Subclasses of :py:class:`GuestlessTask`
        should implement their logic in this method rather than in
        :py:meth:`go` which is already provided. If your task requires different
        handling in :py:class:`go`, it might be better derived directly from
        :py:class:`Task`.
        """

        raise NotImplementedError

    def go(self) -> Iterator['Self']:
        """
        Perform the task.

        Called by :py:class:`Queue` machinery to accomplish the task. It expects
        the child class would implement :py:meth:`run`, with ``go`` taking care
        of task/queue interaction.

        :yields: since the task is not expected to run on multiple guests,
            only a single instance of the class is yielded to describe the task
            and its outcome.
        """

        try:
            self.result = self.run(self.logger)

        except Exception as exc:
            self.result = None
            self.exc = exc

            yield self

        else:
            self.exc = None

            yield self


@dataclasses.dataclass
class MultiGuestTask(Task[TaskResultT]):
    """
    A task assigned to a particular set of guests.

    An extension of the :py:class:`Task` class, provides a quite generic wrapper
    for the actual task which takes care of catching exceptions and proper
    reporting.
    """

    guests: list['Guest']

    # Custom yet trivial `__init__` is necessary, see note in `tmt.queue.Task`.
    def __init__(self, logger: Logger, guests: list['Guest'], **kwargs: Any) -> None:
        super().__init__(logger, **kwargs)

        self.guests = guests

    @functools.cached_property
    def guest_ids(self) -> list[str]:
        return sorted([guest.multihost_name for guest in self.guests])

    def run_on_guest(self, guest: 'Guest', logger: Logger) -> None:
        """
        Perform the task.

        Called from :py:meth:`go` once for every guest to run on. Subclasses of
        :py:class:`GuestlessTask` should implement their logic in this method
        rather than in :py:meth:`go` which is already provided. If your task
        requires different handling in :py:class:`go`, it might be better
        derived directly from :py:class:`Task`.
        """

        raise NotImplementedError

    def go(self) -> Iterator['Self']:
        """
        Perform the task.

        Called by :py:class:`Queue` machinery to accomplish the task. It expects
        the child class would implement :py:meth:`run`, with ``go`` taking care
        of task/queue interaction.

        :yields: instances of the same class, describing invocations of the
            task and their outcome. For each guest, one instance would be
            yielded.
        """

        multiple_guests = len(self.guests) > 1

        new_loggers = prepare_loggers(self.logger, [guest.multihost_name for guest in self.guests])
        old_loggers: dict[str, Logger] = {}

        with ThreadPoolExecutor(max_workers=len(self.guests)) as executor:
            futures: dict[Future[None], Guest] = {}

            for guest in self.guests:
                # Swap guest's logger for the one we prepared, with labels
                # and stuff.
                #
                # We can't do the same for phases - phase is shared among
                # guests, its `self.$loggingmethod()` calls need to be
                # fixed to use a logger we pass to it through the executor.
                #
                # Possibly, the same thing should happen to guest methods as
                # well, then the phase would pass the given logger to guest
                # methods when it calls them, propagating the single logger we
                # prepared...
                old_loggers[guest.multihost_name] = guest._logger
                new_logger = new_loggers[guest.multihost_name]

                guest.inject_logger(new_logger)

                if multiple_guests:
                    new_logger.info('started', color='cyan')

                # Submit each task/guest combination (save the guest & logger
                # for later)...
                futures[
                    executor.submit(self.run_on_guest, guest, new_logger)
                    ] = guest

            # ... and then sit and wait as they get delivered to us as they
            # finish. Unpack the guest and logger, so we could preserve logging
            # and prepare the right outcome package.
            for future in as_completed(futures):
                guest = futures[future]

                old_logger = old_loggers[guest.multihost_name]
                new_logger = new_loggers[guest.multihost_name]

                if multiple_guests:
                    new_logger.info('finished', color='cyan')

                # `Future.result()` will either 1. reraise an exception the
                # callable raised, if any, or 2. return whatever the callable
                # returned - which is `None` in our case, therefore we can
                # ignore the return value.
                try:
                    result = future.result()

                except SystemExit as exc:
                    task = dataclasses.replace(self, result=None, exc=None, requested_exit=exc)

                except Exception as exc:
                    task = dataclasses.replace(self, result=None, exc=exc, requested_exit=None)

                else:
                    task = dataclasses.replace(self, result=result, exc=None, requested_exit=None)

                task.guest = guest

                yield task

                # Don't forget to restore the original logger.
                guest.inject_logger(old_logger)


class Queue(list[TaskT]):
    """ Queue class for running tasks """

    def __init__(self, name: str, logger: Logger) -> None:
        super().__init__()

        self.name = name
        self._logger = logger

    def enqueue_task(self, task: TaskT) -> None:
        """ Put new task into a queue """

        self.append(task)

        self._logger.info(
            f'queued {self.name} task #{len(self)}',
            task.name,
            color='cyan')

    def run(self) -> Iterator[TaskT]:
        """
        Start crunching the queued tasks.

        Tasks are executed in the order, for each task/guest
        combination a :py:class:`Task` instance is yielded.
        """

        for i, task in enumerate(self):
            self._logger.info('')

            self._logger.info(
                f'{self.name} task #{i + 1}',
                task.name,
                color='cyan')

            failed_tasks: list[TaskT] = []

            for outcome in task.go():
                if outcome.exc:
                    failed_tasks.append(outcome)

                yield outcome

            # TODO: make this optional
            if failed_tasks:
                return
