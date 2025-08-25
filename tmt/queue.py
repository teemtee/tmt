import copy
from collections.abc import Iterator
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from typing import TYPE_CHECKING, Callable, Generic, Optional, TypeVar

from tmt._compat.typing import ParamSpec
from tmt.log import Logger

if TYPE_CHECKING:
    from tmt._compat.typing import Self
    from tmt.steps.provision import Guest


T = TypeVar('T')
P = ParamSpec('P')
TaskResultT = TypeVar('TaskResultT')
TaskT = TypeVar('TaskT', bound='Task')  # type: ignore[type-arg]


class Task(Generic[TaskResultT]):
    """
    A base class for queueable actions.

    .. note::

        The class provides both the implementation of the action, but
        also serves as a container for outcome of the action: every time
        the task is invoked by :py:class:`<Queue>`, the queue yields an
        instance of the same class, but filled with information related
        to the result of its action.
    """

    #: A logger to use for logging events related to the outcome.
    logger: Logger

    #: Result returned by the task when executed.
    result: Optional[TaskResultT] = None

    #: If set, an exception was raised by the running task, and said
    #: exception is saved in this field.
    exc: Optional[Exception] = None

    #: If set, the task raised :py:class:`SystemExit` exception, and
    #: wants to terminate the run completely. Original exception is
    #: assigned to this field.
    requested_exit: Optional[SystemExit] = None

    def __init__(self, logger: Logger) -> None:
        self.logger = logger

    @property
    def name(self) -> str:
        """
        A name of this task.

        Left for child classes to implement, because the name depends on
        the actual task.
        """

        raise NotImplementedError

    def _extract_task_outcome(
        self, logger: Logger, extract: Callable[P, TaskResultT], *args: P.args, **kwargs: P.kwargs
    ) -> 'Self':
        """
        A helper for extracting the task outcome and recording it.

        :param logger: used for logging, and will be attached to the
            returned instance.
        :param extract: a callable responsible for extracting outcome
            of the task. It will be passed rest of positional and
            keyword arguments.
        :param args: positional arguments for ``extract`` callable.
        :param kwargs: keyword arguments for ``extract`` callable.
        :returns: new instance of this class, with :py:attr:`logger`,
            :py:attr:`result`, :py:attr:`exc` and
            :py:attr:`requested_exit` attributes filled according to the
            result of ``extract``.
        """

        task = copy.copy(self)

        task.logger = logger
        task.result = None
        task.exc = None
        task.requested_exit = None

        try:
            task.result = extract(*args, **kwargs)

        except SystemExit as exc:
            task.requested_exit = exc

        except Exception as exc:
            task.exc = exc

        return task

    def _invoke_in_pool(
        self,
        *,
        units: list[T],
        get_label: Callable[['Self', T], str],
        extract_logger: Callable[['Self', T], Logger],
        inject_logger: Callable[['Self', T, Logger], None],
        submit: Callable[['Self', T, Logger, ThreadPoolExecutor], Future[TaskResultT]],
        on_complete: Optional[Callable[['Self', T], 'Self']] = None,
        logger: Logger,
    ) -> Iterator['Self']:
        """
        Execute the task across a list of "units" of work.

        A helper for situations where the task is to be applied at
        multiple guests, phases or other objects at the same time. The
        task is scheduled as a :py:class:`Future` for each unit of
        ``units`` list; results of these futures are then collected, and
        yielded as instances of the task's class.

        :param units: list of units the task should run for.
        :param get_label: a callable that shall return a logger label for
            the given unit. The label is than added to a custom logger
            passed to ``inject_logger``.
        :param extract_logger: a callable that shall return the current
            logger of the given unit. The logger is saved and then
            restored when the task for the given unit is complete.
        :param inject_logger: a callable that should update the given
            unit with the given unit-specific logger. It will be called
            twice, to inject the custom logger first, and then to restore
            the original logger.
        :param submit: a callable that shall submit the task, with the
            given unit, to the executor, and return the :py:class:`Future`
            instance it receives from the executor.
        :param on_complete: if set, it will be called once the task
            completes for the given unit.
        :param logger: used for logging.
        """

        multiple_units = len(units) > 1

        new_loggers = prepare_loggers(logger, [get_label(self, unit) for unit in units])
        old_loggers: dict[str, Logger] = {}

        with ThreadPoolExecutor(max_workers=len(units)) as executor:
            futures: dict[Future[TaskResultT], T] = {}

            for unit in units:
                # Swap unit's logger for the one we prepared, with labels
                # and stuff.
                old_loggers[get_label(self, unit)] = extract_logger(self, unit)
                new_logger = new_loggers[get_label(self, unit)]

                inject_logger(self, unit, new_logger)

                if multiple_units:
                    new_logger.info('started', color='cyan')

                # Submit each task/unit combination, and save the unit
                # and logger for later.
                futures[submit(self, unit, new_logger, executor)] = unit

            # ... and then sit and wait as they get delivered to us as they
            # finish. Unpack the guest and logger, so we could preserve logging
            # and prepare the right outcome package.
            for future in as_completed(futures):
                unit = futures[future]

                old_logger = old_loggers[get_label(self, unit)]
                new_logger = new_loggers[get_label(self, unit)]

                if multiple_units:
                    new_logger.info('finished', color='cyan')

                # `Future.result()` will either 1. reraise an exception the
                # callable raised, if any, or 2. return whatever the callable
                # returned - which is `None` in our case, therefore we can
                # ignore the return value.
                task = self._extract_task_outcome(new_logger, future.result)

                if on_complete:
                    task = on_complete(task, unit)

                # Don't forget to restore the original logger.
                inject_logger(task, unit, old_logger)

                yield task

    def go(self) -> Iterator['Self']:
        """
        Perform the task.

        Called by :py:class:`Queue` machinery to accomplish the task.

        :yields: instances of the same class, describing invocations of
            the task and their outcome. The task might be executed
            multiple times, depending on how exactly it was queued, and
            method would yield corresponding results.
        """

        raise NotImplementedError


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


class GuestlessTask(Task[TaskResultT]):
    """
    A task not assigned to a particular set of guests.

    An extension of the :py:class:`Task` class, provides a starting
    point for tasks that do not need to run on any guest.
    """

    def run(self, logger: Logger) -> TaskResultT:
        """
        Perform the task.

        Called once from :py:meth:`go`. Subclasses of must implement
        their logic in this method rather than in :py:meth:`go` which is
        already provided.
        """

        raise NotImplementedError

    def go(self) -> Iterator['Self']:
        """
        Perform the task.

        Called by :py:class:`Queue` machinery to accomplish the task.

        Invokes :py:meth:`run` method to perform the task itself, and
        derived classes therefore must provide implementation of ``run``
        method.

        :yields: instances of the same class, describing invocations of
            the task and their outcome. The task might be executed
            multiple times, depending on how exactly it was queued, and
            method would yield corresponding results.
        """

        yield self._extract_task_outcome(self.logger, self.run, self.logger)


class MultiGuestTask(Task[TaskResultT]):
    """
    A task assigned to a particular set of guests.

    An extension of the :py:class:`Task` class, provides a starting
    point for tasks that do need to run on a set of guests.
    """

    #: List of guests to run the task on.
    guests: list['Guest']

    #: Guest on which the phase was executed.
    guest: Optional['Guest'] = None

    def __init__(self, guests: list['Guest'], logger: Logger) -> None:
        super().__init__(logger)

        self.guests = guests

    @property
    def guest_ids(self) -> list[str]:
        return sorted([guest.multihost_name for guest in self.guests])

    def run_on_guest(self, guest: 'Guest', logger: Logger) -> TaskResultT:
        """
        Perform the task.

        Called once from :py:meth:`go`. Subclasses of must implement
        their logic in this method rather than in :py:meth:`go` which is
        already provided.
        """

        raise NotImplementedError

    def go(self) -> Iterator['Self']:
        """
        Perform the task.

        Called by :py:class:`Queue` machinery to accomplish the task.

        Invokes :py:meth:`run_on_guest` method to perform the task itself,
        and derived classes therefore must provide implementation of
        ``run_on_guest`` method.

        :yields: instances of the same class, describing invocations of
            the task and their outcome. The task might be executed
            multiple times, depending on how exactly it was queued, and
            method would yield corresponding results.
        """

        def _on_complete(task: 'Self', guest: 'Guest') -> 'Self':
            task.guest = guest

            return task

        yield from self._invoke_in_pool(
            # Run across all guests known to this task.
            units=self.guests,
            # Unit ID here is guest's multihost name
            get_label=lambda task, guest: guest.multihost_name,
            extract_logger=lambda task, guest: guest._logger,
            inject_logger=lambda task, guest, logger: guest.inject_logger(logger),
            # Submit work for the executor pool.
            submit=lambda task, guest, logger, executor: executor.submit(
                self.run_on_guest, guest, logger
            ),
            on_complete=_on_complete,
            logger=self.logger,
        )


class Queue(list[TaskT]):
    """
    Queue class for running tasks.
    """

    def __init__(self, name: str, logger: Logger) -> None:
        super().__init__()

        self.name = name
        self._logger = logger

    def enqueue_task(self, task: TaskT) -> None:
        """
        Put new task into a queue
        """

        self.append(task)

        self._logger.info(
            f'queued {self.name} task #{len(self)}',
            task.name,
            color='cyan',
        )

    def run(self) -> Iterator[TaskT]:
        """
        Start crunching the queued tasks.

        Tasks are executed in the order, for each invoked task new
        instance of this class is yielded.
        """

        for i, task in enumerate(self):
            self._logger.info('')

            self._logger.info(
                f'{self.name} task #{i + 1}',
                task.name,
                color='cyan',
            )

            failed_tasks: list[TaskT] = []

            for outcome in task.go():
                if outcome.exc:
                    failed_tasks.append(outcome)

                yield outcome

            # TODO: make this optional
            if failed_tasks:
                return
