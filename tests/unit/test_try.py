from typing import Any
from unittest import mock

import pytest

import tmt.cli.trying
from tmt.trying import Action, Try


@pytest.mark.parametrize(
    ('params', 'expected'),
    [
        (
            {'image_and_how': ('fedora@virtual',), 'arch': None},
            {'image': 'fedora', 'how': 'virtual'},
        ),
        (
            {'image_and_how': ('fedora@virtual',), 'arch': 'aarch64'},
            {'image': 'fedora', 'how': 'virtual', 'arch': 'aarch64'},
        ),
        (
            {'image_and_how': ('@local',), 'arch': None},
            {'how': 'local'},
        ),
        (
            {'image_and_how': (), 'arch': 'aarch64'},
            {'arch': 'aarch64'},
        ),
    ],
)
def test_options_arch(params: dict[str, Any], expected: dict[str, Any]):
    assert tmt.cli.trying._construct_trying_provision_options(params) == expected


class TestHostCommandExecution:
    """
    Test the action_host method
    TODO: Extend tests for different scenarios:
    1. Multiple commands execution
    2. Command execution with output capture
    3. Command failure handling
    4. KeyboardInterrupt handling
    ... etc.
    """

    @mock.patch('subprocess.run')
    @mock.patch('builtins.input')
    def test_action_host_executes_single_command_successfully(self, mock_input, mock_subprocess):
        mock_input.side_effect = ["pwd", Action.QUIT.key]

        mock_try_instance = mock.MagicMock()
        mock_plan = mock.MagicMock()
        mock_plan.workdir = "/test/workdir"

        Try.action_host(mock_try_instance, mock_plan)

        mock_subprocess.assert_called_once_with(["pwd"], cwd="/test/workdir", check=True)
