import os
import re
from typing import Any
from unittest.mock import MagicMock

import _pytest.logging
import pytest
from pytest_container.container import ContainerData

from tmt.log import Logger
from tmt.steps.provision import Guest, GuestData, GuestSsh, GuestSshData, Provision
from tmt.steps.provision.podman import GuestContainer
from tmt.utils import Command, CommandOutput, Path, RunError, ShellScript

from . import TEST_CONTAINERS


def test_multihost_name(root_logger: Logger) -> None:
    assert (
        Guest(logger=root_logger, name='foo', data=GuestData(primary_address='bar')).multihost_name
        == 'foo'
    )

    assert (
        Guest(
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
