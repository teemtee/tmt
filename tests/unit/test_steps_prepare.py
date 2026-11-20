import re
from collections.abc import Iterable, Iterator
from typing import Any, Literal, Optional
from unittest.mock import MagicMock

import _pytest.logging
import pytest

import tmt.log
import tmt.steps.prepare
import tmt.utils
from tmt.base.core import DependencySimple
from tmt.guest import Guest, GuestFacts, RebootMode, RebootModeNotSupportedError
from tmt.package_managers import Installable, Options
from tmt.steps.prepare.install import PrepareInstall, PrepareInstallData
from tmt.steps.provision.mock import GuestMock
from tmt.utils import Command, CommandOutput, Path, PrepareError, RunError

from . import SEARCH, assert_log, assert_not_log

#: Kernel release the simulated guest boots initially.
OLD_KERNEL_RELEASE = '6.11.0-1.fc41.x86_64'

#: Kernel release of the kernel package installed by tests.
NEW_KERNEL_RELEASE = '6.12.0-1.fc41.x86_64'

#: Kernel package installed by tests.
NEW_KERNEL = f'kernel-{NEW_KERNEL_RELEASE}'

#: Message logged when the reboot is skipped because nothing was installed.
SKIPPED_REBOOT_MESSAGE = r'Skipping reboot as no packages were installed\.'

#: Message logged when the ``bootc`` package manager already rebooted the guest.
BOOTC_REBOOT_MESSAGE = r"Reboot already handled by the 'bootc' package manager\."


class _SimulatedGuest:
    """
    State of a simulated guest, backing the mocked guest and its package manager.

    Mimics behavior of real guests relevant for the reboot decision:
    installation commands produce output even when they do not change
    anything, unavailable packages are reported in the output instead of
    being installed, and the guest boots the newly installed kernel after
    a reboot.

    :param present: packages present on the guest.
    :param available: packages an installation would add to the guest.
    """

    def __init__(self, *, present: Iterable[str] = (), available: Iterable[str] = ()) -> None:
        self.present: set[str] = set(present)
        self.available: set[str] = set(available)
        self.booted_kernel_release = OLD_KERNEL_RELEASE

    def _install(self, names: list[str]) -> CommandOutput:
        """
        Add available packages to the guest, report unavailable ones.

        :param names: names of packages to install.
        :returns: command output, never empty.
        """

        unavailable = [name for name in names if name not in self.present | self.available]
        self.present.update(name for name in names if name in self.available)

        return CommandOutput(
            stdout='Dependencies resolved.\nComplete!\n',
            stderr=''.join(f'No match for argument: {name}\n' for name in unavailable),
        )

    def install(
        self, *installables: Installable, options: Optional[Options] = None
    ) -> CommandOutput:
        """
        Simulate :py:meth:`tmt.package_managers.PackageManager.install`.

        With ``check_first`` set, present packages are skipped, and no
        command runs when all packages are present.
        """

        names = [str(installable) for installable in installables]

        if (options or Options()).check_first:
            names = [name for name in names if name not in self.present]

            if not names:
                return CommandOutput(stdout=None, stderr=None)

        return self._install(names)

    def install_local(
        self, *installables: Installable, options: Optional[Options] = None
    ) -> CommandOutput:
        """
        Simulate :py:meth:`tmt.package_managers.PackageManager.install_local`.

        Like real package managers, ignores ``check_first``.
        """

        return self._install([str(installable) for installable in installables])

    def install_debuginfo(
        self, *installables: Installable, options: Optional[Options] = None
    ) -> CommandOutput:
        """
        Simulate :py:meth:`tmt.package_managers.PackageManager.install_debuginfo`.
        """

        return self._install([f'{installable}-debuginfo' for installable in installables])

    def check_presence(self, *installables: Installable) -> dict[Installable, bool]:
        """
        Simulate :py:meth:`tmt.package_managers.PackageManager.check_presence`.
        """

        return {installable: str(installable) in self.present for installable in installables}

    def extract_package_name_from_package_manager_output(self, output: str) -> Iterator[str]:
        """
        Simulate extraction of failed package names from package manager output.
        """

        yield from re.findall(r'No match for argument: (\S+)', output)

    def execute(self, command: Command, **kwargs: Any) -> CommandOutput:
        """
        Simulate :py:meth:`tmt.guest.Guest.execute`, used by guest facts only.

        :returns: release of the booted kernel, as reported by ``uname -r``.
        """

        assert str(command) == 'uname -r'

        return CommandOutput(stdout=f'{self.booted_kernel_release}\n', stderr='')

    def reboot(self, mode: RebootMode = RebootMode.SOFT, **kwargs: Any) -> bool:
        """
        Simulate :py:meth:`tmt.guest.Guest.reboot`, boot the newly installed kernel.

        :returns: ``True``, the reboot always succeeds.
        """

        if NEW_KERNEL in self.present:
            self.booted_kernel_release = NEW_KERNEL_RELEASE

        return True


def _create_prepare_install(
    root_logger: tmt.log.Logger,
    *,
    packages: list[str],
    reboot: Literal['never', 'if-installed'] = 'never',
    missing: Literal['skip', 'fail'] = 'fail',
    check_first: bool = True,
    simulated_guest: Optional[_SimulatedGuest] = None,
    guest_class: type[Guest] = Guest,
) -> tuple[PrepareInstall, MagicMock]:
    """
    Create an install phase and a mocked guest to run the phase on.

    The guest and its package manager are backed by ``simulated_guest``,
    and the guest has real :py:class:`GuestFacts` which query the booted
    kernel release from the simulated guest.

    :param root_logger: logger to use for the phase.
    :param packages: packages requested by the phase.
    :param reboot: value of the ``reboot`` key of the phase.
    :param missing: value of the ``missing`` key of the phase.
    :param check_first: value of the ``check-first`` key of the phase.
    :param simulated_guest: guest state to use. A guest with no packages
        present and :py:data:`NEW_KERNEL` available is used by default.
    :param guest_class: class the mocked guest pretends to be.
    :returns: the phase and the mocked guest.
    """

    simulated_guest = simulated_guest or _SimulatedGuest(available=[NEW_KERNEL])

    mock_plan = MagicMock(name='<mock>plan')
    mock_plan.is_dry_run = False
    mock_plan.my_run.is_dry_run = False
    mock_plan.provision.is_multihost = False
    mock_plan.discover.dependencies_to_tests = ({}, {})

    step = tmt.steps.prepare.Prepare(plan=mock_plan, raw_data=[], logger=root_logger)
    data = PrepareInstallData(
        name='install-phase',
        how='install',
        package=[DependencySimple(pkg) for pkg in packages],
        reboot=reboot,
        missing=missing,
        check_first=check_first,
    )
    plugin = PrepareInstall(step=step, data=data, logger=root_logger)

    guest = MagicMock(spec=guest_class)
    guest.name = 'default-0'
    guest.safe_name = 'default-0'
    guest.multihost_name = 'default-0'
    guest.localhost = False
    guest.facts = GuestFacts(
        package_manager='dnf',
        is_container=False,
        kernel_release=OLD_KERNEL_RELEASE,
    )
    guest.execute.side_effect = simulated_guest.execute
    guest.reboot.side_effect = simulated_guest.reboot

    package_manager = guest.package_manager
    package_manager.install.side_effect = simulated_guest.install
    package_manager.install_local.side_effect = simulated_guest.install_local
    package_manager.install_debuginfo.side_effect = simulated_guest.install_debuginfo
    package_manager.check_presence.side_effect = simulated_guest.check_presence
    package_manager.extract_package_name_from_package_manager_output.side_effect = (
        simulated_guest.extract_package_name_from_package_manager_output
    )
    package_manager.finalize_installation.return_value = CommandOutput(stdout=None, stderr=None)

    return plugin, guest


def test_debuginfo(root_logger: tmt.log.Logger) -> None:
    """
    Check debuginfo package parsing
    """

    plugin = MagicMock(spec=PrepareInstall)

    PrepareInstall._prepare_installables(
        plugin,
        dependencies=[
            # Regular packages
            DependencySimple("wget"),
            DependencySimple("debuginfo-something"),
            DependencySimple("elfutils-debuginfod"),
            # Debuginfo packages
            DependencySimple("grep-debuginfo"),
            DependencySimple("elfutils-debuginfod-debuginfo"),
        ],
        directories=[],
        logger=root_logger,
    )

    assert plugin.packages == [
        "wget",
        "debuginfo-something",
        "elfutils-debuginfod",
    ]
    assert plugin.debuginfo_packages == [
        "grep",
        "elfutils-debuginfod",
    ]


def test_install_reboot_disabled_by_default(root_logger: tmt.log.Logger) -> None:
    """
    Verify reboot is disabled by default and no extra presence checks are made
    """

    plugin, guest = _create_prepare_install(root_logger, packages=[NEW_KERNEL])
    assert plugin.data.reboot == 'never'

    plugin.go(guest=guest, logger=root_logger)

    guest.package_manager.install.assert_called_once()
    guest.package_manager.check_presence.assert_not_called()
    guest.reboot.assert_not_called()


def test_install_reboot_disabled_keeps_skip_missing_presence_check(
    root_logger: tmt.log.Logger,
) -> None:
    """
    Verify only the debuginfo presence check of ``missing: skip`` runs without reboot
    """

    plugin, guest = _create_prepare_install(
        root_logger,
        packages=[NEW_KERNEL, 'grep-debuginfo'],
        missing='skip',
        simulated_guest=_SimulatedGuest(available=[NEW_KERNEL, 'grep-debuginfo']),
    )

    plugin.go(guest=guest, logger=root_logger)

    guest.package_manager.check_presence.assert_called_once_with('grep-debuginfo')
    guest.reboot.assert_not_called()


def test_install_reboot_enabled(
    root_logger: tmt.log.Logger, caplog: _pytest.logging.LogCaptureFixture
) -> None:
    """
    Verify the guest boots the installed kernel and kernel_release fact is refreshed
    """

    plugin, guest = _create_prepare_install(
        root_logger, packages=[NEW_KERNEL], reboot='if-installed'
    )

    plugin.go(guest=guest, logger=root_logger)

    guest.package_manager.install.assert_called_once()
    guest.reboot.assert_called_once_with(mode=RebootMode.SOFT)
    assert_log(caplog, message=SEARCH(r'reboot: Rebooting guest after package installation'))
    # The fact is queried from the guest after the reboot, the guest reports
    # the new kernel only after it was rebooted.
    assert guest.facts.kernel_release == NEW_KERNEL_RELEASE


def test_install_reboot_skipped_when_already_installed(
    root_logger: tmt.log.Logger, caplog: _pytest.logging.LogCaptureFixture
) -> None:
    """
    Verify reboot is skipped when requested packages are already present
    """

    plugin, guest = _create_prepare_install(
        root_logger,
        packages=[NEW_KERNEL],
        reboot='if-installed',
        simulated_guest=_SimulatedGuest(present=[NEW_KERNEL]),
    )

    plugin.go(guest=guest, logger=root_logger)

    guest.reboot.assert_not_called()
    assert guest.facts.kernel_release == OLD_KERNEL_RELEASE
    assert_log(caplog, message=SEARCH(SKIPPED_REBOOT_MESSAGE))


def test_install_reboot_skipped_when_already_installed_without_check_first(
    root_logger: tmt.log.Logger, caplog: _pytest.logging.LogCaptureFixture
) -> None:
    """
    Verify reboot is skipped with ``check-first: false`` when packages are already present

    The installation command runs and produces output, yet installs nothing.
    """

    plugin, guest = _create_prepare_install(
        root_logger,
        packages=['tree'],
        reboot='if-installed',
        check_first=False,
        simulated_guest=_SimulatedGuest(present=['tree'], available=['tree']),
    )

    plugin.go(guest=guest, logger=root_logger)

    guest.package_manager.install.assert_called_once()
    assert guest.package_manager.install.call_args.kwargs['options'].check_first is False
    guest.reboot.assert_not_called()
    assert_log(caplog, message=SEARCH(SKIPPED_REBOOT_MESSAGE))


def test_install_reboot_skipped_when_no_packages_specified(root_logger: tmt.log.Logger) -> None:
    """
    Verify reboot is skipped when no packages or directories are configured
    """

    plugin, guest = _create_prepare_install(root_logger, packages=[], reboot='if-installed')

    plugin.go(guest=guest, logger=root_logger)

    guest.package_manager.install.assert_not_called()
    guest.reboot.assert_not_called()


@pytest.mark.parametrize(
    ('packages', 'present'),
    [
        (['nonexistent-pkg'], []),
        (['tree', 'nonexistent-pkg'], ['tree']),
    ],
    ids=['all-missing', 'present-and-missing'],
)
def test_install_reboot_skipped_when_missing_skip_installs_nothing(
    root_logger: tmt.log.Logger,
    caplog: _pytest.logging.LogCaptureFixture,
    packages: list[str],
    present: list[str],
) -> None:
    """
    Verify reboot is skipped with ``missing: skip`` when only unavailable packages were missing
    """

    plugin, guest = _create_prepare_install(
        root_logger,
        packages=packages,
        reboot='if-installed',
        missing='skip',
        simulated_guest=_SimulatedGuest(present=present),
    )

    plugin.go(guest=guest, logger=root_logger)

    guest.package_manager.install.assert_called_once()
    guest.reboot.assert_not_called()
    assert_log(caplog, message=SEARCH(SKIPPED_REBOOT_MESSAGE))


def test_install_reboot_when_missing_skip_installs_some(root_logger: tmt.log.Logger) -> None:
    """
    Verify reboot happens with ``missing: skip`` when at least one missing package was installed
    """

    plugin, guest = _create_prepare_install(
        root_logger,
        packages=[NEW_KERNEL, 'nonexistent-pkg'],
        reboot='if-installed',
        missing='skip',
    )

    plugin.go(guest=guest, logger=root_logger)

    guest.reboot.assert_called_once_with(mode=RebootMode.SOFT)


def test_install_reboot_after_debuginfo_installation(root_logger: tmt.log.Logger) -> None:
    """
    Verify an installed debuginfo package counts as an installation
    """

    plugin, guest = _create_prepare_install(
        root_logger,
        packages=['grep-debuginfo'],
        reboot='if-installed',
        simulated_guest=_SimulatedGuest(available=['grep-debuginfo']),
    )

    plugin.go(guest=guest, logger=root_logger)

    guest.package_manager.install_debuginfo.assert_called_once()
    guest.reboot.assert_called_once_with(mode=RebootMode.SOFT)


@pytest.mark.parametrize('package_kind', ['local', 'remote'])
def test_install_reboot_after_local_or_remote_packages(
    root_logger: tmt.log.Logger,
    monkeypatch: pytest.MonkeyPatch,
    tmppath: Path,
    package_kind: str,
) -> None:
    """
    Verify local and remote packages always count as an installation

    Their presence cannot be checked by name, therefore no presence
    checks are made.
    """

    if package_kind == 'local':
        package = str(tmppath / f'{NEW_KERNEL}.rpm')

        def _prepare_install_local(self: PrepareInstall, guest: Guest) -> None:
            """
            Skip copying of local packages to the guest.
            """

            self.package_directory = tmppath

        monkeypatch.setattr(PrepareInstall, '_prepare_install_local', _prepare_install_local)

    else:
        package = f'https://example.com/{NEW_KERNEL}.rpm'

    plugin, guest = _create_prepare_install(
        root_logger,
        packages=[package],
        reboot='if-installed',
        simulated_guest=_SimulatedGuest(available=[package]),
    )

    plugin.go(guest=guest, logger=root_logger)

    guest.package_manager.check_presence.assert_not_called()
    guest.reboot.assert_called_once_with(mode=RebootMode.SOFT)


def test_install_reboot_skipped_on_bootc(
    root_logger: tmt.log.Logger, caplog: _pytest.logging.LogCaptureFixture
) -> None:
    """
    Verify PrepareInstall does not trigger a second reboot when bootc handles it
    """

    simulated_guest = _SimulatedGuest(available=[NEW_KERNEL])
    plugin, guest = _create_prepare_install(
        root_logger,
        packages=[NEW_KERNEL],
        reboot='if-installed',
        simulated_guest=simulated_guest,
    )
    guest.facts.package_manager = 'bootc'

    def _finalize_installation() -> CommandOutput:
        """
        Simulate bootc switching to the new image and rebooting the guest.
        """

        simulated_guest.reboot()

        return CommandOutput(stdout='Built image', stderr='')

    guest.package_manager.finalize_installation.side_effect = _finalize_installation

    plugin.go(guest=guest, logger=root_logger)

    guest.package_manager.finalize_installation.assert_called_once()
    guest.reboot.assert_not_called()
    assert_log(caplog, message=SEARCH(BOOTC_REBOOT_MESSAGE))
    assert_not_log(caplog, message=SEARCH(SKIPPED_REBOOT_MESSAGE))


def test_install_reboot_skipped_on_bootc_when_nothing_installed(
    root_logger: tmt.log.Logger, caplog: _pytest.logging.LogCaptureFixture
) -> None:
    """
    Verify bootc reports skipped reboot, not a handled one, when nothing was installed
    """

    plugin, guest = _create_prepare_install(
        root_logger,
        packages=['tree'],
        reboot='if-installed',
        simulated_guest=_SimulatedGuest(present=['tree']),
    )
    guest.facts.package_manager = 'bootc'

    plugin.go(guest=guest, logger=root_logger)

    guest.reboot.assert_not_called()
    assert_log(caplog, message=SEARCH(SKIPPED_REBOOT_MESSAGE))
    assert_not_log(caplog, message=SEARCH(BOOTC_REBOOT_MESSAGE))


def test_install_reboot_not_called_on_failed_install(root_logger: tmt.log.Logger) -> None:
    """
    Verify guest.reboot is not called when package installation fails
    """

    plugin, guest = _create_prepare_install(
        root_logger, packages=[NEW_KERNEL], reboot='if-installed'
    )
    run_error = RunError(
        'Failed to install package',
        Command('dnf', 'install', '-y', NEW_KERNEL),
        1,
        stdout='',
        stderr=f'Error: Unable to find a match: {NEW_KERNEL}',
    )
    guest.package_manager.install.side_effect = run_error

    with pytest.raises(RunError):
        plugin.go(guest=guest, logger=root_logger)

    assert guest.package_manager.install.call_count == 2
    guest.package_manager.refresh_metadata.assert_called_once()
    guest.reboot.assert_not_called()


def test_install_reboot_after_metadata_refresh_retry(root_logger: tmt.log.Logger) -> None:
    """
    Verify reboot happens when the first attempt installed packages before failing

    The retry finds all packages present and installs nothing, the
    packages installed by the first attempt must still trigger the reboot.
    """

    plugin, guest = _create_prepare_install(
        root_logger, packages=[NEW_KERNEL], reboot='if-installed'
    )
    guest.package_manager.finalize_installation.side_effect = [
        RunError('Failed to finalize installation', Command('false'), 1),
        CommandOutput(stdout=None, stderr=None),
    ]

    plugin.go(guest=guest, logger=root_logger)

    assert guest.package_manager.install.call_count == 2
    guest.package_manager.refresh_metadata.assert_called_once()
    guest.reboot.assert_called_once_with(mode=RebootMode.SOFT)
    assert guest.facts.kernel_release == NEW_KERNEL_RELEASE


@pytest.mark.parametrize(
    'reboot_side_effect',
    [
        False,
        RebootModeNotSupportedError(guest=MagicMock(spec=Guest), mode=RebootMode.SOFT),
        tmt.utils.ProvisionError('Provisioner reboot failed.'),
        RunError('Reboot command failed.', Command('reboot'), 1),
    ],
    ids=['returns-false', 'mode-not-supported', 'provision-error', 'run-error'],
)
def test_install_failed_reboot_raises_prepare_error(
    root_logger: tmt.log.Logger,
    reboot_side_effect: object,
) -> None:
    """
    Verify a failed reboot raises PrepareError without triggering package install retry
    """

    plugin, guest = _create_prepare_install(
        root_logger, packages=[NEW_KERNEL], reboot='if-installed'
    )
    if isinstance(reboot_side_effect, Exception):
        guest.reboot.side_effect = reboot_side_effect
    else:
        guest.reboot.side_effect = None
        guest.reboot.return_value = reboot_side_effect

    with pytest.raises(
        PrepareError,
        match="Failed to reboot guest 'default-0' after package installation",
    ):
        plugin.go(guest=guest, logger=root_logger)

    guest.package_manager.install.assert_called_once()
    guest.package_manager.refresh_metadata.assert_not_called()
    guest.reboot.assert_called_once_with(mode=RebootMode.SOFT)


@pytest.mark.parametrize(
    ('guest_class', 'is_localhost', 'is_container', 'expected_message'),
    [
        (Guest, True, False, 'Reboot after package installation is not supported on local guest.'),
        (
            Guest,
            False,
            True,
            'Reboot after package installation is not supported on container guests.',
        ),
        (
            GuestMock,
            False,
            False,
            'Reboot after package installation is not supported on mock guests.',
        ),
    ],
    ids=['local-guest', 'container-guest', 'mock-guest'],
)
def test_install_reboot_unsupported_guests(
    root_logger: tmt.log.Logger,
    guest_class: type[Guest],
    is_localhost: bool,
    is_container: bool,
    expected_message: str,
) -> None:
    """
    Verify reboot option is rejected on unsupported guests before package installation
    """

    plugin, guest = _create_prepare_install(
        root_logger, packages=[NEW_KERNEL], reboot='if-installed', guest_class=guest_class
    )
    guest.localhost = is_localhost
    guest.facts.is_container = is_container

    with pytest.raises(PrepareError, match=re.escape(expected_message)):
        plugin.go(guest=guest, logger=root_logger)

    guest.package_manager.check_presence.assert_not_called()
    guest.package_manager.install.assert_not_called()
    guest.reboot.assert_not_called()


@pytest.mark.parametrize(
    ('guest_class', 'is_localhost', 'is_container'),
    [
        (Guest, True, False),
        (Guest, False, True),
        (GuestMock, False, False),
    ],
    ids=['local-guest', 'container-guest', 'mock-guest'],
)
def test_install_reboot_never_on_unsupported_guests(
    root_logger: tmt.log.Logger,
    guest_class: type[Guest],
    is_localhost: bool,
    is_container: bool,
) -> None:
    """
    Verify the default ``reboot: never`` does not reject guests which cannot reboot
    """

    plugin, guest = _create_prepare_install(
        root_logger, packages=[NEW_KERNEL], reboot='never', guest_class=guest_class
    )
    guest.localhost = is_localhost
    guest.facts.is_container = is_container

    plugin.go(guest=guest, logger=root_logger)

    guest.package_manager.install.assert_called_once()
    guest.reboot.assert_not_called()
