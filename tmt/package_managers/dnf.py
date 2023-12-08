import re
from typing import Optional, cast

import tmt.package_managers
from tmt.package_managers import (
    FileSystemPath,
    Installable,
    Options,
    escape_installables,
    provides_package_manager,
    )
from tmt.utils import Command, CommandOutput, GeneralError, RunError, ShellScript


@provides_package_manager('dnf')
class Dnf(tmt.package_managers.PackageManager):
    probe_command = Command('dnf', '--version')

    _base_command = Command('dnf')

    skip_missing_option = '--skip-broken'

    def prepare_command(self) -> tuple[Command, Command]:
        options = Command('-y')
        command = Command()

        if self.guest.facts.is_superuser is False:
            command += Command('sudo')

        command += self._base_command

        return (command, options)

    def _extra_dnf_options(self, options: Options) -> Command:
        """ Collect additional options for ``yum``/``dnf`` based on given options """

        extra_options = Command()

        for package in options.excluded_packages:
            extra_options += Command('--exclude', package)

        if options.skip_missing:
            extra_options += Command(self.skip_missing_option)

        return extra_options

    def _construct_presence_script(self, *installables: Installable) -> ShellScript:
        return ShellScript(
            f'rpm -q --whatprovides {" ".join(escape_installables(*installables))}'
            )

    def check_presence(self, *installables: Installable) -> dict[Installable, bool]:
        try:
            output = self.guest.execute(self._construct_presence_script(*installables))
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

    def _construct_install_script(
            self,
            *installables: Installable,
            options: Optional[Options] = None) -> ShellScript:
        options = options or Options()

        extra_options = self._extra_dnf_options(options)

        script = ShellScript(
            f'{self.command.to_script()} install '
            f'{self.options.to_script()} {extra_options} '
            f'{" ".join(escape_installables(*installables))}')

        if options.check_first:
            script = self._construct_presence_script(*installables) | script

        return script

    def _construct_reinstall_script(
            self,
            *installables: Installable,
            options: Optional[Options] = None) -> ShellScript:
        options = options or Options()

        extra_options = self._extra_dnf_options(options)

        script = ShellScript(
            f'{self.command.to_script()} reinstall '
            f'{self.options.to_script()} {extra_options} '
            f'{" ".join(escape_installables(*installables))}')

        if options.check_first:
            script = self._construct_presence_script(*installables) & script

        return script

    def install(
            self,
            *installables: Installable,
            options: Optional[Options] = None) -> CommandOutput:
        return self.guest.execute(self._construct_install_script(
            *installables,
            options=options))

    def reinstall(
            self,
            *installables: Installable,
            options: Optional[Options] = None) -> CommandOutput:
        return self.guest.execute(self._construct_reinstall_script(
            *installables,
            options=options
            ))

    def install_debuginfo(
            self,
            *installables: Installable,
            options: Optional[Options] = None) -> CommandOutput:
        # Make sure debuginfo-install is present on the target system
        self.install(FileSystemPath('/usr/bin/debuginfo-install'))

        options = options or Options()

        extra_options = self._extra_dnf_options(options)

        return self.guest.execute(ShellScript(
            f'debuginfo-install -y '
            f'{self.options.to_script()} {extra_options} '
            f'{" ".join(escape_installables(*installables))}'))


@provides_package_manager('dnf5')
class Dnf5(Dnf):
    probe_command = Command('dnf5', '--version')

    _base_command = Command('dnf5')
    skip_missing_option = '--skip-unavailable'


@provides_package_manager('yum')
class Yum(Dnf):
    probe_command = Command('yum', '--version')

    _base_command = Command('yum')

    # TODO: get rid of those `type: ignore` below. I think it's caused by the
    # decorator, it might be messing with the class inheritance as seen by pyright,
    # but mypy sees no issue, pytest sees no issue, everything works. Silencing
    # for now.
    def install(
            self,
            *installables: Installable,
            options: Optional[Options] = None) -> CommandOutput:

        options = options or Options()

        script = cast(  # type: ignore[redundant-cast]
            ShellScript,
            self._construct_install_script(  # type: ignore[reportGeneralIssues,unused-ignore]
                *installables,
                options=options
                ))

        # Extra ignore/check for yum to workaround BZ#1920176
        if options.skip_missing:
            script |= ShellScript('/bin/true')

        else:
            script &= cast(  # type: ignore[redundant-cast]
                ShellScript,
                self._construct_presence_script(  # type: ignore[reportGeneralIssues,unused-ignore]
                    *installables))

        return self.guest.execute(script)

    def reinstall(
            self,
            *installables: Installable,
            options: Optional[Options] = None) -> CommandOutput:

        options = options or Options()

        script = cast(  # type: ignore[redundant-cast]
            ShellScript,
            self._construct_reinstall_script(  # type: ignore[reportGeneralIssues,unused-ignore]
                *installables,
                options=options
                ))

        # Extra ignore/check for yum to workaround BZ#1920176
        if options.skip_missing:
            script |= ShellScript('/bin/true')

        else:
            script &= cast(  # type: ignore[redundant-cast]
                ShellScript,
                self._construct_presence_script(  # type: ignore[reportGeneralIssues,unused-ignore]
                    *installables))

        return self.guest.execute(script)
