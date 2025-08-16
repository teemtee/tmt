from unittest import mock

import pytest

from tmt._compat.pathlib import Path
from tmt.trying import Try
from tmt.utils import RunError, style


class TestHostCommandExecution:
    @pytest.fixture
    def mock_try_instance(self):
        return mock.MagicMock()

    @pytest.fixture
    def mock_plan(self):
        plan = mock.MagicMock()
        plan.workdir = Path("/test/workdir")
        return plan

    @pytest.mark.parametrize(
        ("inputs", "effects", "expected_outputs"),
        [
            (
                ["pwd", "q"],
                [None],
                [
                    style("Enter command (or 'q' to quit): ", fg="green"),
                    style("Enter command (or 'q' to quit): ", fg="green"),
                    "Exiting host command mode. Bye for now!",
                ],
            ),
            (
                ["abcde", "q"],
                [RunError("command not found", "abcde", 127)],
                [
                    style("Enter command (or 'q' to quit): ", fg="green"),
                    style("Enter command (or 'q' to quit): ", fg="green"),
                    "Exiting host command mode. Bye for now!",
                ],
            ),
            (
                ["pwd", "ls -la", ""],
                [None, None],
                [
                    style("Enter command (or 'q' to quit): ", fg="green"),
                    style("Enter command (or 'q' to quit): ", fg="green"),
                    style("Enter command (or 'q' to quit): ", fg="green"),
                    "Exiting host command mode. Bye for now!",
                ],
            ),
            *[
                (
                    [exc],
                    [],
                    [
                        style("Enter command (or 'q' to quit): ", fg="green"),
                        "Exiting host command mode. Bye for now!",
                    ],
                )
                for exc in (KeyboardInterrupt, EOFError)
            ],
        ],
        ids=(
            'Single command success',
            'Command failure',
            'Multiple commands success',
            'KeyboardInterrupt',
            'EOFError',
        ),
    )
    @mock.patch("tmt.utils.show_exception_as_warning")
    @mock.patch("tmt.utils.Command.run")
    @mock.patch("builtins.input")
    def test_action_host(
        self,
        mock_input,
        mock_command_run,
        mock_show_exception,
        mock_try_instance,
        mock_plan,
        inputs,
        effects,
        expected_outputs,
    ):
        mock_input.side_effect = inputs
        mock_command_run.side_effect = effects

        Try.action_host(mock_try_instance, mock_plan)

        printed = [args[0] for args, _ in mock_try_instance.print.call_args_list]
        assert printed == expected_outputs
