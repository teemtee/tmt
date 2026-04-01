from typing import Optional, cast
from unittest.mock import MagicMock, patch

import _pytest.monkeypatch
import pytest

import tmt
import tmt.guest
import tmt.queue
import tmt.steps
import tmt.utils
from tmt.log import Logger
from tmt.steps import Phase
from tmt.utils import GeneralError


class TestPhaseAssertFeelingSafe:
    def setup_method(self):
        self.mock_logger = MagicMock()
        self.phase = Phase(logger=self.mock_logger)

    @pytest.mark.parametrize(
        ("tmt_version", "deprecated_version", "expect_warn", "expect_exception"),
        [
            ('1.30', '1.38', True, False),  # warn for older version
            ('1.4.0.dev1595+ga35d7140.d20240806', '1.38', True, False),  # warn for older version
            ('1.40', '1.38', False, True),  # raise exception for newer version
            ('1.38', '1.38', False, True),  # raise exception for same version
        ],
        ids=(
            'warn for older version',
            'warn for older version with commit ID',
            'raise exception for newer version',
            'raise exception for same version',
        ),
    )
    def test_assert_feeling_safe(
        self, tmt_version, deprecated_version, expect_warn, expect_exception
    ):
        with patch.object(self.phase, 'warn') as mock_warn:
            tmt.__version__ = tmt_version

            if expect_exception:
                with pytest.raises(GeneralError):
                    self.phase.assert_feeling_safe(deprecated_version, 'Local provision plugin')
            else:
                self.phase.assert_feeling_safe(deprecated_version, 'Local provision plugin')

            assert mock_warn.called == expect_warn

    def test_assert_feeling_safe_feeling_safe(self):
        with (
            patch.object(Phase, 'is_feeling_safe', True),
            patch.object(self.phase, 'warn') as mock_warn,
        ):
            tmt.__version__ = '1.40'
            self.phase.assert_feeling_safe('1.38', 'Local provision plugin')

            # Check that warn is not called when feeling safe
            assert not mock_warn.called


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
            environment: Optional[tmt.utils.Environment] = None,
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


def test_add_phase_addeed_to_queue(
    mocked_queue: tuple[
        tmt.steps.StepWithQueue, tmt.queue.Queue, tmt.steps.Plugin, tmt.steps.Action
    ],
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
