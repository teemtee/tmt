import os
from typing import Any
from unittest.mock import MagicMock

import pytest

from tmt.log import Logger
from tmt.steps.provision import (
    Guest,
    GuestCapability,
    GuestData,
    GuestFacts,
    GuestSsh,
    GuestSshData,
    Provision,
)
from tmt.utils import Command, CommandOutput


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


def test_guest_capability_values() -> None:
    """Test that GuestCapability enum values match kernel capabilities"""
    assert GuestCapability.CAP_CHOWN.value == 0
    assert GuestCapability.CAP_DAC_OVERRIDE.value == 1
    assert GuestCapability.CAP_SETUID.value == 7
    assert GuestCapability.CAP_SYS_ADMIN.value == 21
    assert GuestCapability.CAP_SYSLOG.value == 34
    assert GuestCapability.CAP_CHECKPOINT_RESTORE.value == 40


def test_guest_facts_default_values(root_logger: Logger) -> None:
    """Test GuestFacts default values"""
    facts = GuestFacts()
    assert facts.in_sync is False
    assert facts.arch is None
    assert facts.distro is None
    assert facts.kernel_release is None
    assert facts.package_manager is None
    assert facts.has_selinux is None
    assert facts.is_superuser is None
    assert facts.is_ostree is None
    assert facts.capabilities is None


def test_guest_facts_capability_checking(root_logger: Logger) -> None:
    """Test GuestFacts capability checking"""
    facts = GuestFacts()

    # No capabilities set
    assert facts.has_capabilities(GuestCapability.CAP_SYS_ADMIN) is False

    # Single capability
    facts.capabilities = [GuestCapability.CAP_SYS_ADMIN]
    assert facts.has_capabilities(GuestCapability.CAP_SYS_ADMIN) is True
    assert facts.has_capabilities(GuestCapability.CAP_CHOWN) is False

    # Multiple capabilities
    facts.capabilities = [
        GuestCapability.CAP_CHOWN,
        GuestCapability.CAP_DAC_OVERRIDE,
        GuestCapability.CAP_SETUID,
    ]
    assert facts.has_capabilities(GuestCapability.CAP_CHOWN) is True
    assert facts.has_capabilities(GuestCapability.CAP_DAC_OVERRIDE) is True
    assert facts.has_capabilities(GuestCapability.CAP_SETUID) is True
    assert facts.has_capabilities(GuestCapability.CAP_SYS_ADMIN) is False

    # Check multiple capabilities at once
    assert (
        facts.has_capabilities(GuestCapability.CAP_CHOWN, GuestCapability.CAP_DAC_OVERRIDE) is True
    )
    assert (
        facts.has_capabilities(GuestCapability.CAP_CHOWN, GuestCapability.CAP_SYS_ADMIN) is False
    )


def test_guest_facts_serialization(root_logger: Logger) -> None:
    """Test GuestFacts serialization/deserialization"""
    facts = GuestFacts()
    facts.capabilities = [
        GuestCapability.CAP_CHOWN,
        GuestCapability.CAP_DAC_OVERRIDE,
        GuestCapability.CAP_SETUID,
    ]

    # Serialize
    serialized = facts.to_serialized()
    assert 'capabilities' in serialized
    assert serialized['capabilities'] == [0, 1, 7]  # Enum values

    # Deserialize
    new_facts = GuestFacts.from_serialized(serialized)
    assert new_facts.capabilities == facts.capabilities
    assert new_facts.has_capabilities(GuestCapability.CAP_CHOWN) is True
    assert new_facts.has_capabilities(GuestCapability.CAP_DAC_OVERRIDE) is True
    assert new_facts.has_capabilities(GuestCapability.CAP_SETUID) is True
    assert new_facts.has_capabilities(GuestCapability.CAP_SYS_ADMIN) is False


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
