from unittest import mock

import pytest

from tmt._compat.pathlib import Path
from tmt.trying import Try
from tmt.utils import RunError, style


@pytest.fixture
def mock_try_instance():
    instance = mock.MagicMock()
    instance._handle_interactive_prompt = Try._handle_interactive_prompt.__get__(instance, Try)
    return instance


@pytest.fixture
def mock_plan():
    plan = mock.MagicMock()
    plan.workdir = Path("/test/workdir")
    return plan


@pytest.mark.parametrize(
    ("inputs", "effects", "expected_outputs"),
    [
        (
            ["pwd", r"\q"],
            [None],
            [
                style(r"Enter command (or '\q' to quit): ", fg="green"),
                style(r"Enter command (or '\q' to quit): ", fg="green"),
                "Exiting host command mode.",
            ],
        ),
        (
            ["abcde", r"\q"],
            [RunError("abcde command failed to run.", "abcde", 127)],
            [
                style(r"Enter command (or '\q' to quit): ", fg="green"),
                style(r"Enter command (or '\q' to quit): ", fg="green"),
                "Exiting host command mode.",
            ],
        ),
        (
            ["pwd", "ls -la", ""],
            [None, None],
            [
                style(r"Enter command (or '\q' to quit): ", fg="green"),
                style(r"Enter command (or '\q' to quit): ", fg="green"),
                style(r"Enter command (or '\q' to quit): ", fg="green"),
                "Exiting host command mode.",
            ],
        ),
        *[
            (
                [exc],
                [],
                [
                    style(r"Enter command (or '\q' to quit): ", fg="green"),
                    "Exiting host command mode.",
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


@pytest.mark.parametrize(
    ("inputs", "effects", "expected_outputs"),
    [
        (
            ["/tests", r"\q"],
            [None],
            [
                style(r"Enter directory path (or '\q' to quit): ", fg="green"),
                "Changed directory to: /tests",
                "Matching tests found\n/tests/base/bad\n/tests/base/good",
                style(r"Enter directory path (or '\q' to quit): ", fg="green"),
                "Exiting local change directory mode.",
            ],
        ),
    ],
)
@mock.patch("pathlib.Path.exists", return_value=True)
@mock.patch("pathlib.Path.cwd", return_value=Path("/tests"))
@mock.patch("os.chdir")
@mock.patch("tmt.utils.show_exception_as_warning")
@mock.patch("builtins.input")
def test_action_local_change_directory(
    mock_input,
    mock_show_exception,
    mock_chdir,
    mock_cwd,
    mock_exists,
    mock_try_instance,
    mock_plan,
    inputs,
    effects,
    expected_outputs,
):
    mock_plan.fmf_root = Path("/")
    mock_try_instance._previous_test_dir = Path("/old/dir")
    mock_input.side_effect = inputs
    mock_try_instance.check_tests = mock.MagicMock()
    mock_try_instance.tests = ["/tests/base/bad", "/tests/base/good"]

    Try.action_local_change_directory(mock_try_instance, mock_plan)

    printed = [args[0] for args, _ in mock_try_instance.print.call_args_list]
    assert printed == expected_outputs
    mock_try_instance.check_tests.assert_called_once_with(Path("/tests"))
