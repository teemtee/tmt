import dataclasses
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from typing import TYPE_CHECKING, Dict, Generator, Generic, List, Optional, TypeVar

import fmf.utils

from tmt.log import Logger

if TYPE_CHECKING:
    from typing_extensions import Self

    from tmt.steps.provision import Guest


TaskT = TypeVar('TaskT', bound='_Task')


@dataclasses.dataclass
class TaskOutcome(Generic[TaskT]):
    """
    Outcome of a queued task executed on a guest.

    Bundles together interesting objects related to how the task has been
    executed, where and what was the result.
    """

    #: A :py:`_Task` instace the outcome relates to.
    task: TaskT

    #: A logger to use for logging events related to the outcome.
    logger: Logger

    #: Guest on which the phase was executed. May be unset, some tasks
    #: may handle multiguest actions on their own.
    guest: Optional['Guest']

    #: If set, an exception was raised by the running task, and the exception
    #: is saved in this field.
    exc: Optional[Exception]


@dataclasses.dataclass
class _Task:
    """ A base class for tasks to be executed on one or more guests """

    #: A list of guests to execute the task on.
    guests: List['Guest']

    #: A logger to use for logging events related to the task. It serves as
    #: a root logger for new loggers queue may spawn for each guest.
    logger: Logger

    @property
    def name(self) -> str:
        """
        A name of this task.

        Left for child classes to implement, because the name depends on the
        actual task.
        """

        raise NotImplementedError

    @property
    def guest_ids(self) -> List[str]:
        return [guest.multihost_name for guest in self.guests]

    def go(self) -> Generator[TaskOutcome['Self'], None, None]:
        """ Perform the task """

        raise NotImplementedError


@dataclasses.dataclass
class GuestlessTask(_Task):
    """
    A task that does not run on a particular guest.

    .. note::

       This may sound unexpected, but there are tasks that need to be part
       of the queue, but need no specific guest to run on. Usualy, they handle
       the multihost environment on their own. See :py:class:`tmt.steps.Login`
       and :py:class:`tmt.steps.Reboot`.
    """

    def run(self, logger: Logger) -> None:
        raise NotImplementedError

    def go(self) -> Generator[TaskOutcome['Self'], None, None]:
        try:
            self.run(self.logger)

        except Exception as exc:
            # logger.info('finished', color='cyan')

            yield TaskOutcome(
                task=self,
                logger=self.logger,
                guest=None,
                exc=exc)

        else:
            # logger.info('finished', color='cyan')

            yield TaskOutcome(
                task=self,
                logger=self.logger,
                guest=None,
                exc=None)


@dataclasses.dataclass
class Task(_Task):
    """ A task that should run on multiple guests at the same time """

    def run_on_guest(self, guest: 'Guest', logger: Logger) -> None:
        raise NotImplementedError

    def prepare_loggers(
            self,
            logger: Logger) -> Dict[str, Logger]:
        """
        Create loggers for a set of guests.

        Guests are assumed to be a group a phase would be executed on, and
        therefore their labels need to be set, to provide context, plus their
        labels need to be properly aligned for more readable output.
        """

        loggers: Dict[str, Logger] = {}

        # First, spawn all loggers, and set their labels if needed. Don't bother
        # with labels if there's just a single guest.
        for guest in self.guests:
            new_logger = logger.clone()

            if len(self.guests) > 1:
                new_logger.labels.append(guest.multihost_name)

            loggers[guest.name] = new_logger

        # Second, find the longest labels, and instruct all loggers to pad their
        # labels to match this length. This should create well-indented messages.
        max_label_span = max(new_logger.labels_span for new_logger in loggers.values())

        for new_logger in loggers.values():
            new_logger.labels_padding = max_label_span

        return loggers

    def go(self) -> Generator[TaskOutcome['Self'], None, None]:
        multiple_guests = len(self.guests) > 1

        new_loggers = self.prepare_loggers(self.logger)
        old_loggers: Dict[str, Logger] = {}

        with ThreadPoolExecutor(max_workers=len(self.guests)) as executor:
            futures: Dict[Future[None], Guest] = {}

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
                old_loggers[guest.name] = guest._logger
                new_logger = new_loggers[guest.name]

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

                old_logger = old_loggers[guest.name]
                new_logger = new_loggers[guest.name]

                if multiple_guests:
                    new_logger.info('finished', color='cyan')

                # `Future.result()` will either 1. reraise an exception the
                # callable raised, if any, or 2. return whatever the callable
                # returned - which is `None` in our case, therefore we can
                # ignore the return value.
                try:
                    future.result()

                except Exception as exc:
                    yield TaskOutcome(
                        task=self,
                        logger=new_logger,
                        guest=guest,
                        exc=exc)

                else:
                    yield TaskOutcome(
                        task=self,
                        logger=new_logger,
                        guest=guest,
                        exc=None)

                # Don't forget to restore the original logger.
                guest.inject_logger(old_logger)


class Queue(List[TaskT]):
    """ Queue class for running phases on guests """

    def __init__(self, name: str, logger: Logger) -> None:
        super().__init__()

        self.name = name
        self._logger = logger

    def enqueue_task(self, task: TaskT) -> None:
        """ Put new task into a queue """

        self.append(task)

        self._logger.info(
            f'queued {self.name} task #{len(self)}',
            f'{task.name} on {fmf.utils.listed(task.guest_ids)}',
            color='cyan')

    def run(self) -> Generator[TaskOutcome[TaskT], None, None]:
        """
        Start crunching the queued phases.

        Queued tasks are executed in the order, for each task/guest
        combination a :py:class:`TaskOutcome` instance is yielded.
        """

        for i, task in enumerate(self):
            self._logger.info('')

            self._logger.info(
                f'{self.name} task #{i + 1}',
                f'{task.name} on {fmf.utils.listed(task.guest_ids)}',
                color='cyan')

            failed_outcomes: List[TaskOutcome[TaskT]] = []

            for outcome in task.go():
                if outcome.exc:
                    failed_outcomes.append(outcome)

                yield outcome

            # TODO: make this optional
            if failed_outcomes:
                return
