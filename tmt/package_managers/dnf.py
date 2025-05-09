import re
from typing import Optional, cast

from tmt.package_managers import (
    FileSystemPath,
    Installable,
    Options,
    Package,
    PackageManager,
    PackageManagerEngine,
    escape_installables,
    provides_package_manager,
)
from tmt.utils import Command, GeneralError, RunError, ShellScript


class DnfEngine(PackageManagerEngine):
    _base_command = Command('dnf')
    _base_debuginfo_command = Command('debuginfo-install')

    skip_missing_packages_option = '--skip-broken'
    skip_missing_debuginfo_option = skip_missing_packages_option

    def prepare_command(self) -> tuple[Command, Command]:
        options = Command('-y')
        command = Command()

        if self.guest.facts.is_superuser is False:
            command += Command('sudo')

        command += self._base_command

        return (command, options)

    def _extra_dnf_options(self, options: Options, command: Optional[Command] = None) -> Command:
        """
        Collect additional options for ``yum``/``dnf`` based on given options
        """

        command = command or self._base_command

        extra_options = Command()

        for package in options.excluded_packages:
            extra_options += Command('--exclude', package)

        if options.skip_missing:
            if str(command) == str(self._base_command):
                extra_options += Command(self.skip_missing_packages_option)

            elif str(command) == str(self._base_debuginfo_command):
                extra_options += Command(self.skip_missing_debuginfo_option)

            else:
                raise GeneralError(f"Unhandled package manager command '{command}'.")

        return extra_options

    def _construct_presence_script(
        self, *installables: Installable, what_provides: bool = True
    ) -> ShellScript:
        if what_provides:
            return ShellScript(
                f'rpm -q --whatprovides {" ".join(escape_installables(*installables))}'
            )

        return ShellScript(f'rpm -q {" ".join(escape_installables(*installables))}')

    def check_presence(self, *installables: Installable) -> ShellScript:
        return self._construct_presence_script(*installables)

    def _construct_install_script(
        self, *installables: Installable, options: Optional[Options] = None
    ) -> ShellScript:
        options = options or Options()

        extra_options = self._extra_dnf_options(options)

        script = ShellScript(
            f'{self.command.to_script()} install '
            f'{self.options.to_script()} {extra_options} '
            f'{" ".join(escape_installables(*installables))}'
        )

        if options.check_first:
            script = self._construct_presence_script(*installables) | script

        return script

    def _construct_reinstall_script(
        self, *installables: Installable, options: Optional[Options] = None
    ) -> ShellScript:
        options = options or Options()

        extra_options = self._extra_dnf_options(options)

        script = ShellScript(
            f'{self.command.to_script()} reinstall '
            f'{self.options.to_script()} {extra_options} '
            f'{" ".join(escape_installables(*installables))}'
        )

        if options.check_first:
            script = self._construct_presence_script(*installables) & script

        return script

    def _construct_install_debuginfo_script(
        self, *installables: Installable, options: Optional[Options] = None
    ) -> ShellScript:
        options = options or Options()

        extra_options = self._extra_dnf_options(options, command=self._base_debuginfo_command)

        return ShellScript(
            f'{self._base_debuginfo_command.to_script()} '
            f'{self.options.to_script()} {extra_options} '
            f'{" ".join(escape_installables(*installables))}'
        )

    def refresh_metadata(self) -> ShellScript:
        return ShellScript(
            f'{self.command.to_script()} makecache {self.options.to_script()} --refresh'
        )

    def install(
        self,
        *installables: Installable,
        options: Optional[Options] = None,
    ) -> ShellScript:
        return self._construct_install_script(*installables, options=options)

    def reinstall(
        self,
        *installables: Installable,
        options: Optional[Options] = None,
    ) -> ShellScript:
        return self._construct_reinstall_script(*installables, options=options)

    def install_debuginfo(
        self,
        *installables: Installable,
        options: Optional[Options] = None,
    ) -> ShellScript:
        # Make sure debuginfo-install is present on the target system
        script = self.install(FileSystemPath('/usr/bin/debuginfo-install'))

        options = options or Options()

        script &= cast(  # type: ignore[redundant-cast]
            ShellScript,
            self._construct_install_debuginfo_script(  # type: ignore[reportGeneralIssues,unused-ignore]
                *installables, options=options
            ),
        )

        # Extra ignore/check for yum to workaround BZ#1920176
        if not options.skip_missing:
            script &= cast(  # type: ignore[redundant-cast]
                ShellScript,
                self._construct_presence_script(  # type: ignore[reportGeneralIssues,unused-ignore]
                    *tuple(Package(f'{installable}-debuginfo') for installable in installables),
                    what_provides=False,
                ),
            )

        return script


@provides_package_manager('dnf')
class Dnf(PackageManager[DnfEngine]):
    NAME = 'dnf'

    _engine_class = DnfEngine

    bootc_builder = True

    probe_command = ShellScript(
        """
        type dnf && ((dnf --version | grep -E 'dnf5 version') && exit 1 || exit 0)
        """
    ).to_shell_command()
    # The priority of preference: `rpm-ostree` > `dnf5` > `dnf` > `yum`.
    # `rpm-ostree` has its own implementation and its own priority, and
    # the `dnf` family just stays below it.
    probe_priority = 50

    def check_presence(self, *installables: Installable) -> dict[Installable, bool]:
        try:
            output = self.guest.execute(self.engine.check_presence(*installables))
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


class Dnf5Engine(DnfEngine):
    _base_command = Command('dnf5')
    skip_missing_packages_option = '--skip-unavailable'


@provides_package_manager('dnf5')
class Dnf5(Dnf):
    NAME = 'dnf5'

    _engine_class = Dnf5Engine

    probe_command = probe_command = Command('dnf5', '--version')
    probe_priority = 60


class YumEngine(DnfEngine):
    _base_command = Command('yum')

    # TODO: get rid of those `type: ignore` below. I think it's caused by the
    # decorator, it might be messing with the class inheritance as seen by pyright,
    # but mypy sees no issue, pytest sees no issue, everything works. Silencing
    # for now.
    def install(
        self, *installables: Installable, options: Optional[Options] = None
    ) -> ShellScript:
        options = options or Options()

        script = cast(  # type: ignore[redundant-cast]
            ShellScript,
            self._construct_install_script(  # type: ignore[reportGeneralIssues,unused-ignore]
                *installables, options=options
            ),
        )

        # Extra ignore/check for yum to workaround BZ#1920176
        if options.skip_missing:
            script |= ShellScript('/bin/true')

        else:
            script &= cast(  # type: ignore[redundant-cast]
                ShellScript,
                self._construct_presence_script(  # type: ignore[reportGeneralIssues,unused-ignore]
                    *installables
                ),
            )

        return script

    def reinstall(
        self, *installables: Installable, options: Optional[Options] = None
    ) -> ShellScript:
        options = options or Options()

        script = cast(  # type: ignore[redundant-cast]
            ShellScript,
            self._construct_reinstall_script(  # type: ignore[reportGeneralIssues,unused-ignore]
                *installables, options=options
            ),
        )

        # Extra ignore/check for yum to workaround BZ#1920176
        if options.skip_missing:
            script |= ShellScript('/bin/true')

        else:
            script &= cast(  # type: ignore[redundant-cast]
                ShellScript,
                self._construct_presence_script(  # type: ignore[reportGeneralIssues,unused-ignore]
                    *installables
                ),
            )

        return script

    def refresh_metadata(self) -> ShellScript:
        return ShellScript(f'{self.command.to_script()} makecache')


@provides_package_manager('yum')
class Yum(Dnf):
    NAME = 'yum'

    _engine_class = YumEngine

    bootc_builder = False

    probe_command = ShellScript(
        """
        type yum && ((yum --version | grep -E 'dnf5 version') && exit 1 || exit 0)
        """
    ).to_shell_command()
    probe_priority = 40
