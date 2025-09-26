import os
import re
from typing import Any, Optional, Union
from unittest.mock import MagicMock

import _pytest.logging
import pytest
from pytest_container.container import ContainerData

from tmt.log import Logger, LoggingFunction
from tmt.steps.provision import (
    AnsibleApplicable,
    Guest,
    GuestData,
    GuestSsh,
    GuestSshData,
    Provision,
    TransferOptions,
)
from tmt.steps.provision.podman import GuestContainer
from tmt.utils import (
    Command,
    CommandOutput,
    Environment,
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
