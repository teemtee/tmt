from typing import Optional, cast
from unittest.mock import MagicMock

import _pytest.monkeypatch
import pytest

import tmt.guest
import tmt.queue
import tmt.steps
from tmt.log import Logger
from tmt.utils.environment import Environment


@pytest.fixture(name='mocked_queue')
def fixture_mocked_queue(
    root_logger: Logger, monkeypatch: _pytest.monkeypatch.MonkeyPatch
) -> tuple[tmt.steps.StepWithQueue, tmt.queue.Queue, tmt.steps.Plugin]:
    class DummyStep(tmt.steps.StepWithQueue[tmt.steps.StepData, None]):
        _plugin_base_class = tmt.steps.Plugin

        def summary(self) -> None:
            pass

    class DummyPlugin(tmt.steps.Plugin[tmt.steps.StepData, None]):
        _data_class = tmt.steps.StepData

        def go(
            self,
            *,
            guest: tmt.guest.Guest,
            environment: Optional[Environment] = None,
            logger: Logger,
        ) -> None:
            pass

    mock_plan = MagicMock(name='<mock>plan')

    step = DummyStep(plan=mock_plan, logger=root_logger)
    plugin = DummyPlugin(
        step=step, data=tmt.steps.StepData(name='default-0', how='foo'), logger=root_logger
    )

    monkeypatch.setattr(
        step._queue, 'enqueue_action', MagicMock(name='<mock>queue.enqueue_action')
    )
    monkeypatch.setattr(
        step._queue, 'enqueue_plugin', MagicMock(name='<mock>queue.enqueue_plugin')
    )

    return [step, step._queue, plugin]


def test_add_phase_added_to_queue(
    mocked_queue: tuple[tmt.steps.StepWithQueue, tmt.queue.Queue, tmt.steps.Plugin],
) -> None:
    step, queue, plugin = mocked_queue

    assert queue.is_running is False

    step.add_phase(plugin)

    cast(MagicMock, queue.enqueue_action).assert_not_called()
    cast(MagicMock, queue.enqueue_plugin).assert_not_called()

    queue.is_running = True

    step.add_phase(plugin)

    cast(MagicMock, queue.enqueue_action).assert_not_called()
    cast(MagicMock, queue.enqueue_plugin).assert_called_once_with(
        phase=plugin, guests=step._steppified_guests
    )
