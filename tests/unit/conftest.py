from unittest.mock import MagicMock

import pytest

from tmt.guest import GuestSsh, GuestSshData
from tmt.log import Logger
from tmt.steps.provision import Provision
from tmt.utils import Path

_SSH_TEST_GUEST_SPECS: tuple[tuple[str, str], ...] = (
    ('guest-one', '192.0.2.1'),
    ('guest-two', '192.0.2.2'),
)


@pytest.fixture(name='ssh_test_provision')
def fixture_ssh_test_provision(tmppath: Path) -> MagicMock:
    """Create a provision step shared by SSH test guests."""
    provision = MagicMock(spec=Provision)
    provision.run_workdir = tmppath

    return provision


@pytest.fixture(name='ssh_test_guests')
def fixture_ssh_test_guests(
    root_logger: Logger, ssh_test_provision: MagicMock
) -> dict[str, GuestSsh]:
    """Create SSH guests with distinct connection endpoints."""
    return {
        name: GuestSsh(
            logger=root_logger,
            parent=ssh_test_provision,
            name=name,
            data=GuestSshData(primary_address=address),
        )
        for name, address in _SSH_TEST_GUEST_SPECS
    }
