import os
import threading
import time
from collections.abc import Iterator
from typing import Optional
from unittest.mock import MagicMock

import pytest

from tmt._compat.typing import Self
from tmt.guest import Guest
from tmt.log import Logger
from tmt.queue import MultiGuestTask as _MultiGuestTask
from tmt.queue import Queue
from tmt.queue import Task as _Task


class Task(_Task[None]):
    def __init__(self, name: str, logger: Logger) -> None:
        super().__init__(logger)

        self._name = name

    @property
    def name(self) -> str:
        return self._name

    def go(self) -> Iterator[Self]:
        return


def test_head_tail_numbers(root_logger: Logger) -> None:
    queue: Queue[Task] = Queue('dummy queue', root_logger)

    assert queue._head_task_number is None
    assert queue._tail_task_number is None

    queue.enqueue_task(Task('task 1', root_logger))

    assert queue._head_task_number == 1
    assert queue._tail_task_number == 1

    queue.enqueue_task(Task('task 2', root_logger))

    assert queue._head_task_number == 1
    assert queue._tail_task_number == 2

    queue.enqueue_task(Task('task 3', root_logger))

    assert queue._head_task_number == 1
    assert queue._tail_task_number == 3

    # Simulate the first task has been invoked:
    queue.pop(0)
    queue._invoked_tasks += 1

    assert queue._head_task_number == 2
    assert queue._tail_task_number == 3


def test_reordering(root_logger: Logger, caplog) -> None:
    """
    Test whether tasks are correctly ordered.
    """

    queue: Queue[Task] = Queue('dummy queue', root_logger)

    tasks: list[Task[None]] = [
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

    assert [task.name for task in queue] == expected_order


# This is the current expression the `ThreadExecutor` uses to find the
# best number of workers available. Using it an upper bound in our test,
# because a constant wouldn't work as the test may land on various machines.
if hasattr(os, 'process_cpu_count'):
    _THREAD_EXECUTOR_WORKER_GUESSTIMATE = min(32, (os.process_cpu_count() or 1) + 4)
else:
    _THREAD_EXECUTOR_WORKER_GUESSTIMATE = min(32, (os.cpu_count() or 1) + 4)


@pytest.mark.parametrize(
    ('max_workers', 'task_count', 'expected_worker_count'),
    [
        # `unlimited` *by us* - executor can still apply its own limits.
        pytest.param(
            None,
            _THREAD_EXECUTOR_WORKER_GUESSTIMATE,
            _THREAD_EXECUTOR_WORKER_GUESSTIMATE,
            id='unlimited',
        ),
        pytest.param(
            2,
            8,
            2,
            id='limited',
        ),
    ],
)
def test_max_workers(
    max_workers: Optional[int], task_count: int, expected_worker_count: int, root_logger: Logger
) -> None:
    class MultiGuestTask(_MultiGuestTask[None]):
        seen_threads: set[int]
        max_workers: Optional[int]

        def __init__(
            self, name: str, guests: list[Guest], max_workers: Optional[int], logger: Logger
        ) -> None:
            super().__init__(guests, logger)

            self._name = name
            self.guests = guests
            self.seen_threads = set()
            self.max_workers = max_workers

        @property
        def name(self) -> str:
            return self._name

        def run_on_guest(self, guest: Guest, logger: Logger) -> None:
            # Important: just adding to the list is quick, and the task
            # would finish before the executor gets a chance to invoke
            # the task with another guest. This results in reusing threads.
            time.sleep(1)

            self.seen_threads.add(threading.current_thread().name)

        def go(self) -> Iterator['Self']:
            yield from self._invoke_in_pool(
                # Run across all guests known to this task.
                units=self.guests,
                max_workers=self.max_workers,
                # Unit ID here is guest's multihost name
                get_label=lambda task, guest: guest.multihost_name,
                extract_logger=lambda task, guest: guest._logger,
                inject_logger=lambda task, guest, logger: guest.inject_logger(logger),
                # Submit work for the executor pool.
                submit=lambda task, guest, logger, executor: executor.submit(
                    self.run_on_guest, guest, logger
                ),
                logger=self.logger,
            )

    queue: Queue[Task] = Queue('dummy queue', root_logger)

    task = MultiGuestTask(
        'dummy task',
        [
            MagicMock(
                name=f'guest[{i}]',
                multihost_name=f'guest[{i}]',
            )
            for i in range(task_count)
        ],
        max_workers,
        root_logger,
    )

    queue.enqueue_task(task)

    for _ in queue.run():
        pass

    assert len(task.seen_threads) == expected_worker_count
