"""
Unit tests of package managers which do not need real guests.

Guests and package manager engines are replaced with mocks, therefore
these tests verify only the logic implemented by package manager
classes, not the actual commands.
"""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

import tmt.log
import tmt.package_managers.bootc
import tmt.package_managers.dnf
import tmt.utils
from tmt.package_managers import (
    FileSystemPath,
    Installable,
    Package,
    PackageManager,
    PackageManagerEngine,
)
from tmt.steps.provision.mock import GuestMock
from tmt.utils import Command, Path


def _create_package_manager(
    package_manager_class: type[PackageManager[Any]],
    logger: tmt.log.Logger,
) -> PackageManager[Any]:
    """
    Create a package manager with a mocked guest and a mocked engine.
    """

    guest = MagicMock(spec=GuestMock)
    guest.root_path = Path('/var/lib/mock/root')

    with patch.object(package_manager_class, '_engine_class', MagicMock()):
        return package_manager_class(guest=guest, logger=logger)


def test_bootc_build_container_failed_reboot(
    root_logger: tmt.log.Logger,
    tmppath: Path,
) -> None:
    """
    A failed reboot into the new image is reported and facts are not refreshed.
    """

    package_manager = _create_package_manager(tmt.package_managers.bootc.Bootc, root_logger)
    assert isinstance(package_manager, tmt.package_managers.bootc.Bootc)

    guest = package_manager.guest
    assert isinstance(guest, MagicMock)

    guest.is_dry_run = False
    guest.reboot.return_value = False
    guest.run_workdir = Path('/var/tmp/tmt/run-001')
    guest.guest_workdir = tmppath
    guest.mkdtemp.return_value.__enter__.return_value = Path('/var/tmp/containerfile')

    engine = package_manager.engine
    assert isinstance(engine, MagicMock)

    engine.containerfile_directives = ['RUN dnf -y install foo']
    engine.prepare_command.return_value = (Command('bootc'), Command())

    with pytest.raises(tmt.utils.PrepareError, match='Failed to reboot guest'):
        package_manager.build_container()

    guest.reboot.assert_called_once()
    guest.facts.sync.assert_not_called()
    engine.flush_containerfile_directives.assert_called_once()


#: Installables covering all kinds of presence checks: a NEVRA, a NEVRA
#: with an epoch, a plain package name, a file path and a capability.
PRESENCE_INSTALLABLES: tuple[Installable, ...] = (
    Package('kernel-6.12.0-1.fc41.x86_64'),
    Package('kernel-0:6.12.0-1.fc41.x86_64'),
    Package('coreutils'),
    FileSystemPath('/usr/bin/arch'),
    Package('dnf5-command(config-manager)'),
)

PRESENCE_SCRIPT = """rpm -q --whatprovides kernel-6.12.0-1.fc41.x86_64 >&2 || rpm -q kernel-6.12.0-1.fc41.x86_64 >&2 || echo kernel-6.12.0-1.fc41.x86_64
rpm -q --whatprovides kernel-0:6.12.0-1.fc41.x86_64 >&2 || rpm -q kernel-0:6.12.0-1.fc41.x86_64 >&2 || echo kernel-0:6.12.0-1.fc41.x86_64
rpm -q --whatprovides coreutils >&2 || rpm -q coreutils >&2 || echo coreutils
rpm -q --whatprovides /usr/bin/arch >&2 || rpm -q /usr/bin/arch >&2 || echo /usr/bin/arch
rpm -q --whatprovides 'dnf5-command(config-manager)' >&2 || rpm -q 'dnf5-command(config-manager)' >&2 || echo 'dnf5-command(config-manager)'"""  # noqa: E501


@pytest.mark.parametrize(
    'engine_class',
    [
        tmt.package_managers.dnf.DnfEngine,
        tmt.package_managers.dnf.Dnf5Engine,
    ],
    ids=lambda engine_class: engine_class.__name__,
)
def test_dnf_check_presence_script(
    engine_class: type[PackageManagerEngine],
    root_logger: tmt.log.Logger,
) -> None:
    """
    Presence check falls back to plain ``rpm -q`` to detect NEVRAs.
    """

    guest = MagicMock(spec=GuestMock)
    guest.facts.sudo_prefix = ''
    guest.root = None

    engine = engine_class(guest=guest, logger=root_logger)

    assert str(engine.check_presence(*PRESENCE_INSTALLABLES)) == PRESENCE_SCRIPT


def test_bootc_check_presence_script(root_logger: tmt.log.Logger) -> None:
    """
    Bootc presence check is delegated to its dnf-family builder engine.
    """

    guest = MagicMock(spec=GuestMock)
    guest.facts.sudo_prefix = ''
    guest.bootc_builder = tmt.package_managers.dnf.Dnf5

    engine = tmt.package_managers.bootc.BootcEngine(guest=guest, logger=root_logger)

    assert str(engine.check_presence(*PRESENCE_INSTALLABLES)) == PRESENCE_SCRIPT
