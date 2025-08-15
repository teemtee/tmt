from unittest import mock

import pytest

from tmt._compat.pathlib import Path
from tmt.trying import Try
from tmt.utils import RunError, style


class TestHostCommandExecution:
    @pytest.fixture
    def mock_try_instance(self):
        instance = mock.MagicMock()
        instance.print = mock.MagicMock()
        return instance

    @pytest.fixture
    def mock_plan(self):
        plan = mock.MagicMock()
        plan.workdir = Path("/test/workdir")
        return plan

    @pytest.mark.parametrize(
        ("inputs", "effects", "expected_outputs"),
        [
            # Single command success
            (
                ["pwd", "q"],
                [mock.Mock(stdout="/test/workdir\n")],
                [
                    style("Enter command (or 'q' to quit): ", fg="green"),
                    "pwd: /test/workdir",
                    style("Enter command (or 'q' to quit): ", fg="green"),
                    "Exiting host command mode. Bye for now!",
                ],
            ),
            # Command failure
            (
                ["abcde", "q"],
                [RunError(command="abcde", returncode=127, message="command not found")],
                [
                    style("Enter command (or 'q' to quit): ", fg="green"),
                    "Failed to run command 'abcde' on the host: command not found",
                    style("Enter command (or 'q' to quit): ", fg="green"),
                    "Exiting host command mode. Bye for now!",
                ],
            ),
            # Multiple command success & no command
            (
                ["pwd", "ls -la", ""],
                [
                    mock.Mock(stdout="/test/workdir\n"),
                    mock.Mock(stdout="file1.txt\nfile2.txt\n"),
                ],
                [
                    style("Enter command (or 'q' to quit): ", fg="green"),
                    "pwd: /test/workdir",
                    style("Enter command (or 'q' to quit): ", fg="green"),
                    "ls -la: file1.txt\nfile2.txt",
                    style("Enter command (or 'q' to quit): ", fg="green"),
                    "Exiting host command mode. Bye for now!",
                ],
            ),
            # KeyboardInterrupt and EOFError handling
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
    )
    @mock.patch("tmt.utils.Command.run")
    @mock.patch("builtins.input")
    def test_action_host(
        self,
        mock_input,
        mock_command_run,
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
