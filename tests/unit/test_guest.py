import os
import re
from typing import Any, Optional, Union
from unittest.mock import MagicMock, Mock, patch

import _pytest.logging
import pytest
from pytest_container.container import ContainerData

import tmt
from tmt.guest import (
    AnsibleApplicable,
    Guest,
    GuestData,
    GuestSsh,
    GuestSshData,
    TransferOptions,
)
from tmt.log import Logger, LoggingFunction
from tmt.steps.provision import Provision
from tmt.steps.provision.podman import GuestContainer, PodmanGuestData
from tmt.utils import (
    Command,
    CommandOutput,
    Environment,
    GeneralError,
    OnProcessEndCallback,
    OnProcessStartCallback,
    Path,
    RunError,
    ShellScript,
)
from tmt.utils.wait import Waiting

from . import TEST_CONTAINERS


class MockGuest(Guest):
    def reboot(
        self,
        hard: bool = False,
        command: Optional[Union[Command, ShellScript]] = None,
        waiting: Optional[Waiting] = None,
    ) -> bool:
        raise RuntimeError("Mocked but not used")

    def stop(self) -> None:
        raise RuntimeError("Mocked but not used")

    def pull(
        self,
        source: Optional[Path] = None,
        destination: Optional[Path] = None,
        options: Optional[TransferOptions] = None,
    ) -> None:
        raise RuntimeError("Mocked but not used")

    def push(
        self,
        source: Optional[Path] = None,
        destination: Optional[Path] = None,
        options: Optional[TransferOptions] = None,
        superuser: bool = False,
    ) -> None:
        raise RuntimeError("Mocked but not used")

    def execute(
        self,
        command: Union[Command, ShellScript],
        cwd: Optional[Path] = None,
        env: Optional[Environment] = None,
        friendly_command: Optional[str] = None,
        test_session: bool = False,
        tty: bool = False,
        silent: bool = False,
        log: Optional[LoggingFunction] = None,
        interactive: bool = False,
        on_process_start: Optional[OnProcessStartCallback] = None,
        on_process_end: Optional[OnProcessEndCallback] = None,
        **kwargs: Any,
    ) -> CommandOutput:
        raise RuntimeError("Mocked but not used")

    def _run_ansible(
        self,
        playbook: AnsibleApplicable,
        playbook_root: Optional[Path] = None,
        extra_args: Optional[str] = None,
        friendly_command: Optional[str] = None,
        log: Optional[LoggingFunction] = None,
        silent: bool = False,
    ) -> CommandOutput:
        raise RuntimeError("Mocked but not used")

    @property
    def is_ready(self) -> bool:
        raise RuntimeError("Mocked but not used")


def test_multihost_name(root_logger: Logger) -> None:
    assert (
        MockGuest(
            logger=root_logger, name='foo', data=GuestData(primary_address='bar')
        ).multihost_name
        == 'foo'
    )

    assert (
        MockGuest(
            logger=root_logger, name='foo', data=GuestData(primary_address='bar', role='client')
        ).multihost_name
        == 'foo (client)'
    )


@pytest.mark.parametrize(
    ('stdout', 'expected'),
    [
        (
            # no-connection-closed
            os.linesep + 'last-line' + os.linesep,
            os.linesep + 'last-line' + os.linesep,
        ),
        (
            # connection-closed-not-last-line
            os.linesep + 'Connection to 127.0.0.1 closed.' + os.linesep + 'last-line' + os.linesep,
            os.linesep + 'Connection to 127.0.0.1 closed.' + os.linesep + 'last-line' + os.linesep,
        ),
        (
            # connection-closed
            os.linesep + 'some-line' + os.linesep + 'Connection to 127.0.0.1 closed.' + os.linesep,
            os.linesep + 'some-line' + os.linesep,
        ),
        (
            # shared-connection-closed
            os.linesep
            + 'some-line'
            + os.linesep
            + 'Shared connection to 127.0.0.1 closed.'
            + os.linesep,
            os.linesep + 'some-line' + os.linesep,
        ),
    ],
    ids=(
        'no-connection-closed',
        'connection-closed-not-last-line',
        'connection-closed',
        'shared-connection-closed',
    ),
)
def test_execute_no_connection_closed(
    root_logger: Logger, stdout: str, expected: str, monkeypatch: Any
) -> None:
    step = Provision(plan=MagicMock(name='mock<plan>'), data={}, logger=root_logger)
    guest = GuestSsh(
        logger=root_logger, parent=step, name='foo', data=GuestSshData(primary_address='bar')
    )

    monkeypatch.setattr(
        guest,
        '_run_guest_command',
        MagicMock(return_value=CommandOutput(stdout=stdout, stderr=None)),
    )

    output = guest.execute(Command('some-command'), test_session=True)
    assert output.stdout == expected

    output = guest.execute(Command('some-command'))
    assert output.stdout == stdout


@pytest.mark.containers
@pytest.mark.parametrize(
    ('container',),  # noqa: PT006
    [(TEST_CONTAINERS[container_name],) for container_name in sorted(TEST_CONTAINERS.keys())],
    indirect=["container"],
    ids=[TEST_CONTAINERS[container_name].url for container_name in sorted(TEST_CONTAINERS.keys())],
)
def test_mkdtemp(
    container: ContainerData,
    guest: GuestContainer,
    root_logger: Logger,
    caplog: _pytest.logging.LogCaptureFixture,
) -> None:
    guest.execute(ShellScript('mkdir -p /tmp/qux'))

    with guest.mkdtemp(
        prefix='bar',
        template='XXXXXXbazXXXXXX',
        parent=Path('/tmp/qux'),
    ) as path:
        guest.execute(ShellScript(f'ls -al {path}'))

    with pytest.raises(RunError) as exc_context:
        guest.execute(ShellScript(f'ls -al {path}'))

    assert re.match(r'(?i).*?No such file or directory.*', exc_context.value.stderr or '')


class TestPodmanNetworkSetup:
    """Tests for GuestContainer._setup_network() method"""

    @pytest.fixture
    def mock_provision_setup(self) -> Mock:
        """Create a mock provision step with proper attributes"""
        mock_provision = Mock(spec=Provision)
        mock_provision.run_workdir.name = 'test-run-123'
        mock_provision.plan = Mock()
        mock_provision.plan.pathless_safe_name = 'test-plan'
        return mock_provision

    @pytest.fixture
    def mock_shared_provision_setup(self) -> Mock:
        """Create a mock provision step for multi-guest testing"""
        mock_provision = Mock(spec=Provision)
        mock_provision.run_workdir.name = 'shared-run-123'
        mock_provision.plan = Mock()
        mock_provision.plan.pathless_safe_name = 'shared-plan'
        return mock_provision

    def test_setup_network_success(self, root_logger: Logger, mock_provision_setup: Mock) -> None:
        """Test successful network creation"""
        # Create GuestContainer instance
        guest_data = PodmanGuestData(image='fedora:latest')
        guest = GuestContainer(
            logger=root_logger, data=guest_data, name='test-container', parent=mock_provision_setup
        )

        # Mock the podman method
        guest.podman = Mock(return_value=CommandOutput(stdout='', stderr=''))

        # Call _setup_network
        result = guest._setup_network()

        # Verify network name is set correctly
        assert guest.network == 'tmt-test-run-123-test-plan-network'

        # Verify podman network create was called
        guest.podman.assert_called_once()
        call_args = guest.podman.call_args
        assert call_args is not None
        args, kwargs = call_args
        assert len(args) == 1
        assert args[0]._command == ['network', 'create', 'tmt-test-run-123-test-plan-network']
        assert kwargs == {'message': "Create network 'tmt-test-run-123-test-plan-network'."}

        # Verify return value
        assert result == ['--network', 'tmt-test-run-123-test-plan-network']

    def test_setup_network_multi_guest_same_provision(
        self, root_logger: Logger, mock_shared_provision_setup: Mock
    ) -> None:
        """Test scenario where all guests share the same network"""
        # Create multiple guests for the same provision step
        guests = []
        for i in range(3):
            guest_data = PodmanGuestData(image='fedora:latest')
            guest = GuestContainer(
                logger=root_logger,
                data=guest_data,
                name=f'guest-{i}',
                parent=mock_shared_provision_setup,
            )
            guests.append(guest)

        # Mock podman calls - first succeeds, subsequent calls get "already exists"
        run_error = RunError(
            'Network creation failed',
            Command('network', 'create', 'test-network'),
            1,
            stdout='',
            stderr='Error: network already exists',
        )

        # Use side_effect with a list: first call succeeds, subsequent calls raise error
        shared_podman_mock = Mock(
            side_effect=[
                CommandOutput(stdout='', stderr=''),  # First call succeeds
                run_error,  # Second call raises error
                run_error,  # Third call raises error
            ]
        )

        # All guests share the same mock to simulate the real-world scenario
        for guest in guests:
            guest.podman = shared_podman_mock
            guest.debug = Mock()

        # Setup networks for all guests and verify behavior immediately
        results = []
        expected_network = 'tmt-shared-run-123-shared-plan-network'
        expected_args = ['--network', expected_network]

        for i, guest in enumerate(guests):
            result = guest._setup_network()
            results.append(result)

            # Verify network name is set correctly
            assert guest.network == expected_network
            # Verify return value
            assert result == expected_args

            # Verify subsequent guests handle "already exists" gracefully
            if i > 0:  # For guests after the first one
                guest.debug.assert_called_once_with(
                    f"Network '{expected_network}' already exists.", level=3
                )

        # Verify first guest creates the network
        call_args = guests[0].podman.call_args
        assert call_args is not None
        args, kwargs = call_args
        assert len(args) == 1
        assert args[0]._command == ['network', 'create', expected_network]
        assert kwargs == {'message': f"Create network '{expected_network}'."}

        # Verify all calls happened (3 total: 1 success + 2 errors)
        assert shared_podman_mock.call_count == 3

    def test_setup_network_with_custom_prefix(
        self, root_logger: Logger, mock_provision_setup: Mock, monkeypatch
    ) -> None:
        """Test network creation with custom prefix for collision avoidance"""
        monkeypatch.setenv("TMT_PLUGIN_PROVISION_CONTAINER_NETWORK_PREFIX", "tf-pipeline-456")

        guest_data = PodmanGuestData(image='fedora:latest', network_prefix='tf-pipeline-456')
        guest = GuestContainer(
            logger=root_logger, data=guest_data, name='test-container', parent=mock_provision_setup
        )

        # Mock the podman method
        guest.podman = Mock(return_value=CommandOutput(stdout='', stderr=''))

        # Call _setup_network
        result = guest._setup_network()

        # Verify network name includes the custom prefix
        expected_network = 'tf-pipeline-456tmt-test-run-123-test-plan-network'
        assert guest.network == expected_network

        # Verify podman network create was called with prefixed name
        guest.podman.assert_called_once()
        call_args = guest.podman.call_args
        assert call_args is not None
        args, kwargs = call_args
        assert len(args) == 1
        assert args[0]._command == ['network', 'create', expected_network]
        assert kwargs == {'message': f"Create network '{expected_network}'."}

        # Verify return value includes prefixed network name
        assert result == ['--network', expected_network]
