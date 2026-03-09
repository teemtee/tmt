import re
from typing import Optional

from tmt.package_managers import (
    FileSystemPath,
    Installable,
    Options,
    PackageManager,
    PackageManagerEngine,
    PackagePath,
    escape_installables,
    provides_package_manager,
)
from tmt.utils import Command, CommandOutput, GeneralError, RunError, ShellScript


class RpmOstreeEngine(PackageManagerEngine):
    def prepare_command(self) -> tuple[Command, Command]:
        """
        Prepare installation command for rpm-ostree
        """

        assert self.guest.facts.sudo_prefix is not None  # Narrow type

        command = Command('rpm-ostree')

        if self.guest.facts.sudo_prefix:
            command = Command(self.guest.facts.sudo_prefix, 'rpm-ostree')

        options = Command('--apply-live', '--idempotent', '--allow-inactive', '--assumeyes')

        return (command, options)

    def _construct_presence_script(self, *installables: Installable) -> ShellScript:
        if len(installables) == 1 and isinstance(installables[0], FileSystemPath):
            return ShellScript(f'rpm -qf {installables[0]}')

        return ShellScript(f'rpm -q --whatprovides {" ".join(escape_installables(*installables))}')

    def check_presence(self, *installables: Installable) -> ShellScript:
        if len(installables) == 1 and isinstance(installables[0], FileSystemPath):
            return ShellScript(f'rpm -qf {installables[0]}')

        return ShellScript(f'rpm -q --whatprovides {" ".join(escape_installables(*installables))}')

    def _extra_options(self, options: Options) -> Command:
        extra_options = Command()

        for package in options.excluded_packages:
            self.warn(
                "There is no support for rpm-ostree exclude,"
                f" package '{package}' may still be installed."
            )

        if options.install_root is not None:
            extra_options += Command(f'--installroot={options.install_root}')

        if options.release_version is not None:
            extra_options += Command(f'--releasever={options.release_version}')

        return extra_options

    def refresh_metadata(self) -> ShellScript:
        self.guest.warn("Metadata refresh is not supported with rpm-ostree.")

        return ShellScript('/bin/true')

        # The following should work, but it hits some ostree issue:
        #
        #   System has not been booted with systemd as init system (PID 1). Can't operate.
        #   Failed to connect to bus: Host is down
        #   System has not been booted with systemd as init system (PID 1). Can't operate.
        #   Failed to connect to bus: Host is down
        #   error: Loading sysroot: exit status: 1
        #
        # script = ShellScript(f'{self.command.to_script()} refresh-md --force')
        # return self.guest.execute(script)

    def install(
        self,
        *installables: Installable,
        options: Optional[Options] = None,
    ) -> ShellScript:
        options = options or Options()

        extra_options = self._extra_options(options)

        script = ShellScript(
            f'{self.command.to_script()} install '
            f'{self.options.to_script()} {extra_options} '
            f'{" ".join(escape_installables(*installables))}'
        )

        if options.check_first:
            script = self._construct_presence_script(*installables) | script

        if options.skip_missing:
            script = script | ShellScript('/bin/true')

        return script

    def reinstall(
        self,
        *installables: Installable,
        options: Optional[Options] = None,
    ) -> ShellScript:
        raise GeneralError("rpm-ostree does not support reinstall operation.")

    def install_debuginfo(
        self,
        *installables: Installable,
        options: Optional[Options] = None,
    ) -> ShellScript:
        raise GeneralError("rpm-ostree does not support debuginfo packages.")


@provides_package_manager('rpm-ostree')
class RpmOstree(PackageManager[RpmOstreeEngine]):
    NAME = 'rpm-ostree'

    _engine_class = RpmOstreeEngine

    probe_command = Command('stat', '/run/ostree-booted')
    # Needs to be bigger than priorities of `yum`, `dnf` and `dnf5`.
    probe_priority = 100

    def check_presence(self, *installables: Installable) -> dict[Installable, bool]:
        script = self.engine.check_presence(*installables)

        if len(installables) == 1 and isinstance(installables[0], FileSystemPath):
            try:
                self.guest.execute(script)

            except RunError as exc:
                if exc.returncode == 1:
                    return {installables[0]: False}

                raise exc

            return {installables[0]: True}

        try:
            output = self.guest.execute(script)
            stdout = output.stdout

        except RunError as exc:
            stdout = exc.stdout

        if stdout is None:
            raise GeneralError("rpm presence check provided no output")

        results: dict[Installable, bool] = {}

        for line, installable in zip(stdout.strip().splitlines(), installables):
            match = re.match(rf'package {re.escape(str(installable))} is not installed', line)
            if match is not None:
                results[installable] = False
                continue

            match = re.match(rf'no package provides {re.escape(str(installable))}', line)
            if match is not None:
                results[installable] = False
                continue

            results[installable] = True

        return results

    def refresh_metadata(self) -> CommandOutput:
        self.guest.warn("Metadata refresh is not supported with rpm-ostree.")

        return CommandOutput(stdout=None, stderr=None)

        # The following should work, but it hits some ostree issue:
        #
        #   System has not been booted with systemd as init system (PID 1). Can't operate.
        #   Failed to connect to bus: Host is down
        #   System has not been booted with systemd as init system (PID 1). Can't operate.
        #   Failed to connect to bus: Host is down
        #   error: Loading sysroot: exit status: 1
        #
        # script = ShellScript(f'{self.command.to_script()} refresh-md --force')
        # return self.guest.execute(script)

    def reinstall(
        self,
        *installables: Installable,
        options: Optional[Options] = None,
    ) -> CommandOutput:
        raise GeneralError("rpm-ostree does not support reinstall operation.")

    def install_debuginfo(
        self,
        *installables: Installable,
        options: Optional[Options] = None,
    ) -> CommandOutput:
        self.warn("Installation of debuginfo packages not supported yet.")
        return CommandOutput(stdout=None, stderr=None)

    def enable_copr(self, *repositories: str) -> None:
        """
        Enable COPR repositories by delegating to a Dnf5 package manager instance.
        """

        if not repositories:
            return

        from tmt.package_managers.dnf import Dnf5

        Dnf5(guest=self.guest, logger=self._logger).enable_copr(*repositories)

    def sort_packages(
        self,
        *installables: Installable,
        options: Options,
    ) -> None:
        """Sort packages into required and recommended based on presence and skip_missing."""
        self.required: list[Installable] = []
        self.recommended: list[Installable] = []

        for installable in installables:
            if all(self.check_presence(installable).values()):
                continue
            if options.skip_missing:
                self.recommended.append(installable)
            else:
                self.required.append(installable)

    def install_from_repository(
        self,
        *installables: Installable,
        options: Optional[Options] = None,
    ) -> CommandOutput:
        options = options or Options()
        self.sort_packages(*installables, options=options)

        for package in self.recommended:
            self.info('package', str(package), 'green')
            try:
                self.install(package)
            except RunError as error:
                self.debug(f"Package installation failed: {error}")
                self.warn(f"Unable to install recommended package '{package}'.")

        if self.required:
            return self.install(*self.required)

        return CommandOutput(stdout=None, stderr=None)

    def install_local(
        self,
        *installables: Installable,
        options: Optional[Options] = None,
    ) -> CommandOutput:

        options = options or Options()
        options = Options(
            excluded_packages=options.excluded_packages,
            skip_missing=options.skip_missing,
            check_first=False,
        )

        for package in installables:
            assert isinstance(package, PackagePath)
            try:
                self.install(package, options=options)
            except RunError as error:
                self.warn(f"Local package '{package.name}' not installed: {error.stderr}")

        return CommandOutput(stdout=None, stderr=None)
