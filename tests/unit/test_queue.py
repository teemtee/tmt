from collections.abc import Iterator

from tmt._compat.typing import Self
from tmt.log import Logger
from tmt.queue import Queue
from tmt.queue import Task as _Task

from . import MATCH, assert_log


class Task(_Task[None]):
    def __init__(self, name: str, logger: Logger) -> None:
        super().__init__(logger)

        self._name = name

    @property
    def name(self) -> str:
        return self._name

    def go(self) -> Iterator[Self]:
        return


def test_reordering(root_logger: Logger, caplog) -> None:
    """
    Test whether tasks are correctly ordered.
    """

    queue: Queue[Task] = Queue('dummy queue', root_logger)

    tasks: Task[None] = [
        Task('task 1', root_logger),
        Task('task 2', root_logger),
        Task('task 3', root_logger),
        Task('task 4', root_logger),
        Task('task 5', root_logger),
        Task('task 6', root_logger),
        Task('task 7', root_logger),
    ]

    # First, some tasks that should land at the end:
    tasks[0].order = 5
    tasks[1].order = 4
    # But not at the very end, following two tasks should be even further
    # in the queue:
    tasks[2].order = None
    tasks[3].order = None
    # These two should be sorted in at the very end of the block of tasks
    # with `order` set, and at the very beginning, respectively.
    tasks[4].order = 6
    tasks[5].order = 3
    # This one should remain the last
    tasks[6].order = None

    expected_order = [
        'task 6',  # order 3
        'task 2',  # order 4
        'task 1',  # order 5
        'task 5',  # order 6
        # the rest have order None, should remain in their original order
        'task 3',
        'task 4',
        'task 7',
    ]

    for task in tasks:
        queue.enqueue_task(task)

    assert_log(caplog, message=MATCH(r'queued dummy queue task #1: task 1'))
    assert_log(
        caplog, message=MATCH(r'queued dummy queue task #2, caused queue reordering: task 2')
    )
    assert_log(
        caplog, message=MATCH(r'queued dummy queue task #5, caused queue reordering: task 5')
    )
    assert_log(
        caplog, message=MATCH(r'queued dummy queue task #6, caused queue reordering: task 6')
    )

    assert [task.name for task in queue] == expected_order
