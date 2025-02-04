import re
from typing import Optional

import tmt.package_managers
import tmt.utils
from tmt.package_managers import (
    FileSystemPath,
    Installable,
    Options,
    escape_installables,
    provides_package_manager,
    )
from tmt.utils import Command, CommandOutput, GeneralError, RunError, ShellScript


@provides_package_manager('rpm-ostree')
class RpmOstree(tmt.package_managers.PackageManager):
    NAME = 'rpm-ostree'

    probe_command = Command('stat', '/run/ostree-booted')
    # Needs to be bigger than priorities of `yum`, `dnf` and `dnf5`.
    probe_priority = 100

    def prepare_command(self) -> tuple[Command, Command]:
        """ Prepare installation command for rpm-ostree"""

        command = Command()

        if self.guest.facts.is_superuser is False:
            command += Command('sudo')

        command += Command('rpm-ostree')

        options = Command('--apply-live', '--idempotent', '--allow-inactive', '--assumeyes')

        return (command, options)

    def _construct_presence_script(self, *installables: Installable) -> ShellScript:
        if len(installables) == 1 and isinstance(installables[0], FileSystemPath):
            return ShellScript(f'rpm -qf {installables[0]}')

        return ShellScript(
            f'rpm -q --whatprovides {" ".join(escape_installables(*installables))}')

    def check_presence(self, *installables: Installable) -> dict[Installable, bool]:
        if len(installables) == 1 and isinstance(installables[0], FileSystemPath):
            try:
                self.guest.execute(ShellScript(f'rpm -qf {installables[0]}'))

            except RunError as exc:
                if exc.returncode == 1:
                    return {installables[0]: False}

                raise exc

            return {installables[0]: True}

        try:
            output = self.guest.execute(ShellScript(
                f'rpm -q --whatprovides {" ".join(escape_installables(*installables))}'))
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

    def _extra_options(
            self,
            options: Options) -> Command:
        extra_options = Command()

        for package in options.excluded_packages:
            self.warn("There is no support for rpm-ostree exclude,"
                      f" package '{package}' may still be installed.")

        if options.install_root is not None:
            extra_options += Command(f'--installroot={options.install_root}')

        if options.release_version is not None:
            extra_options += Command(f'--releasever={options.release_version}')

        return extra_options

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

    def install(
            self,
            *installables: Installable,
            options: Optional[Options] = None) -> CommandOutput:
        options = options or Options()

        extra_options = self._extra_options(options)

        script = ShellScript(
            f'{self.command.to_script()} install '
            f'{self.options.to_script()} {extra_options} '
            f'{" ".join(escape_installables(*installables))}')

        if options.check_first:
            script = self._construct_presence_script(*installables) | script

        if options.skip_missing:
            script = script | ShellScript('/bin/true')

        return self.guest.execute(script)

    def reinstall(
            self,
            *installables: Installable,
            options: Optional[Options] = None) -> CommandOutput:
        raise GeneralError("rpm-ostree does not support reinstall operation.")

    def install_debuginfo(
            self,
            *installables: Installable,
            options: Optional[Options] = None) -> CommandOutput:
        raise GeneralError("rpm-ostree does not support debuginfo packages.")
