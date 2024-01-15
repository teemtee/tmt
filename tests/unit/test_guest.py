import os
from typing import Any
from unittest.mock import MagicMock

import pytest

from tmt.log import Logger
from tmt.steps.provision import Guest, GuestData, GuestSsh, GuestSshData
from tmt.utils import Command, CommandOutput


def test_multihost_name(root_logger: Logger) -> None:
    assert Guest(
        logger=root_logger,
        name='foo',
        data=GuestData(guest='bar')).multihost_name == 'foo'

    assert Guest(
        logger=root_logger,
        name='foo',
        data=GuestData(guest='bar', role='client')).multihost_name == 'foo (client)'


@pytest.mark.parametrize(('stdout', 'expected'), [
    (
        # no-connection-closed
        os.linesep + 'last-line' + os.linesep,
        os.linesep + 'last-line' + os.linesep
        ),
    (
        # connection-closed-not-last-line
        os.linesep + 'Connection to 127.0.0.1 closed.' + os.linesep + 'last-line' + os.linesep,
        os.linesep + 'Connection to 127.0.0.1 closed.' + os.linesep + 'last-line' + os.linesep
        ),
    (
        # connection-closed
        os.linesep + 'some-line' + os.linesep + 'Connection to 127.0.0.1 closed.' + os.linesep,
        os.linesep + 'some-line' + os.linesep
        ),
    (
        # shared-connection-closed
        os.linesep + 'some-line' + os.linesep + 'Shared connection to 127.0.0.1 closed.' \
        + os.linesep,
        os.linesep + 'some-line' + os.linesep
        )
    ], ids=(
    'no-connection-closed',
    'connection-closed-not-last-line',
    'connection-closed',
    'shared-connection-closed'
    ))
def test_execute_no_connection_closed(
        root_logger: Logger,
        stdout: str,
        expected: str,
        monkeypatch: Any) -> None:
    guest = GuestSsh(
        logger=root_logger,
        name='foo',
        data=GuestSshData(guest='bar')
        )

    monkeypatch.setattr(
        guest,
        '_run_guest_command',
        MagicMock(return_value=CommandOutput(stdout=stdout, stderr=None))
        )
    monkeypatch.setattr(guest, 'parent', MagicMock())

    output = guest.execute(Command('some-command'), test_session=True)
    assert output.stdout == expected

    output = guest.execute(Command('some-command'))
    assert output.stdout == stdout
