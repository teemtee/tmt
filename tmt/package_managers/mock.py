from typing import (
    Optional,
)

from tmt.package_managers import (
    Installable,
    Options,
    PackageManager,
    PackageManagerEngine,
    PackagePath,
    escape_installables,
    provides_package_manager,
)
from tmt.steps.provision.mock import GuestMock
from tmt.utils import Command, CommandOutput, PrepareError, ShellScript


class MockEngine(PackageManagerEngine):
    """
    We use `mock --pm-cmd ...` to execute the package manager commands inside
    the mock. Such scripts need to be executed locally and not inside the mock
    shell.
    """

    def _prepare_mock_command_script(self, script: str) -> ShellScript:
        return ShellScript(f'{self.command} {self.options.to_script()} {script}')

    def _prepare_mock_install_script(
        self,
        installword: str,
        *installables: Installable,
        options: Optional[Options] = None,
    ) -> ShellScript:
        options = options or Options()
        extra_options = Command()

        for package in options.excluded_packages:
            extra_options += Command('--exclude', package)

        if options.skip_missing:
            extra_options += Command('--skip-broken')

        return self._prepare_mock_command_script(
            f'{installword} {extra_options} {" ".join(escape_installables(*installables))}'
        )

    def prepare_command(self) -> tuple[Command, Command]:
        options = Command()
        assert isinstance(self.guest, GuestMock)
        if self.guest.root is not None:
            options += Command('-r', self.guest.root)
        options += Command('--pm-cmd')
        return (Command('mock'), options)

    def check_presence(self, *installables: Installable) -> ShellScript:
        parts = [
            f"rpm -q --whatprovides '{escaped}' >&2 || echo '{escaped}'"
            for escaped in escape_installables(*installables)
        ]
        return ShellScript('\n'.join(parts))

    def install(
        self,
        *installables: Installable,
        options: Optional[Options] = None,
    ) -> ShellScript:
        return self._prepare_mock_install_script('install', *installables, options=options)

    def reinstall(
        self,
        *installables: Installable,
        options: Optional[Options] = None,
    ) -> ShellScript:
        return self._prepare_mock_install_script('reinstall', *installables, options=options)

    def install_debuginfo(
        self,
        *installables: Installable,
        options: Optional[Options] = None,
    ) -> ShellScript:
        return self._prepare_mock_install_script(
            'debuginfo-install', *installables, options=options
        )

    def refresh_metadata(self) -> ShellScript:
        return self._prepare_mock_command_script('makecache --refresh')

    def enable_repo(self, *repo_ids: str) -> ShellScript:
        raise PrepareError("Package manager 'mock' does not support enabling repositories.")

    def disable_repo(self, *repo_ids: str) -> ShellScript:
        raise PrepareError("Package manager 'mock' does not support disabling repositories.")


class _MockPackageManager(PackageManager[MockEngine]):
    """
    Base class implementing the package manager for mock-provisioned guests.
    Note:
    * self.guest.run - execute a command *on the host*.
    * self.guest.execute - execute a command *in the mock shell*.
    """

    probe_command = Command('/usr/bin/false')
    probe_priority = 130
    _engine_class = MockEngine

    def check_presence(self, *installables: Installable) -> dict[Installable, bool]:
        if not installables:
            return {}

        results: dict[Installable, bool] = dict.fromkeys(installables, True)

        # Script always exits 0; stdout contains one line per missing package.
        output = self.guest.execute(self.engine.check_presence(*installables))
        missing = {line.strip() for line in (output.stdout or '').splitlines() if line.strip()}

        for installable in installables:
            if str(installable) in missing:
                results[installable] = False

        return results

    def install(
        self,
        *installables: Installable,
        options: Optional[Options] = None,
    ) -> CommandOutput:
        options = options or Options()

        if not options.check_first or not installables:
            return self.guest.run(
                self.engine.install(*installables, options=options).to_shell_command()
            )

        presence = self.check_presence(*installables)
        missing = tuple(p for p, present in presence.items() if not present)

        if not missing:
            return CommandOutput(stdout=None, stderr=None)

        return self.guest.run(self.engine.install(*missing, options=options).to_shell_command())

    def reinstall(
        self,
        *installables: Installable,
        options: Optional[Options] = None,
    ) -> CommandOutput:
        options = options or Options()

        if not options.check_first or not installables:
            return self.guest.run(
                self.engine.reinstall(*installables, options=options).to_shell_command()
            )

        presence = self.check_presence(*installables)
        present = tuple(p for p, is_present in presence.items() if is_present)

        if not present:
            return CommandOutput(stdout=None, stderr=None)

        return self.guest.run(self.engine.reinstall(*present, options=options).to_shell_command())

    def install_debuginfo(
        self,
        *installables: Installable,
        options: Optional[Options] = None,
    ) -> CommandOutput:
        return self.guest.run(
            self.engine.install_debuginfo(*installables, options=options).to_shell_command()
        )

    def refresh_metadata(self) -> CommandOutput:
        return self.guest.run(self.engine.refresh_metadata().to_shell_command())

    def install_local(
        self,
        *installables: Installable,
        options: Optional[Options] = None,
    ) -> CommandOutput:

        assert isinstance(self.guest, GuestMock)

        options = options or Options()
        options.check_first = False

        # mock's package manager mounts the buildroot directory, so we need to
        # prefix the path with the guest's root_path.
        filelist = [
            PackagePath(self.guest.root_path / p.relative_to('/'))
            for p in installables
            if isinstance(p, PackagePath)
        ]

        # Use both install/reinstall to get all packages refreshed
        # FIXME Simplify this once BZ#1831022 is fixed/implemented.
        output = self.install(*filelist, options=options)
        self.reinstall(*filelist, options=options)
        return output


@provides_package_manager('mock-yum')
class MockYum(_MockPackageManager):
    NAME = 'mock-yum'


@provides_package_manager('mock-dnf')
class MockDnf(_MockPackageManager):
    NAME = 'mock-dnf'


@provides_package_manager('mock-dnf5')
class MockDnf5(_MockPackageManager):
    NAME = 'mock-dnf5'
