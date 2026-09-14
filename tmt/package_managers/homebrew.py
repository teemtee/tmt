import re
from typing import Optional, Union

import tmt.utils
from tmt.package_managers import (
    FileSystemPath,
    Installable,
    Options,
    Package,
    PackageManager,
    PackageManagerEngine,
    PackagePath,
    escape_installables,
    provides_package_manager,
)
from tmt.utils import (
    Command,
    CommandOutput,
    GeneralError,
    RunError,
    ShellScript,
)

ReducedPackages = list[Union[Package, PackagePath]]

#: Homebrew prefixes on Apple silicon and Intel Macs, not on the ``PATH`` of ssh sessions.
HOMEBREW_PREFIXES = ('/opt/homebrew/bin', '/usr/local/bin')

HOMEBREW_PATH = ':'.join([*HOMEBREW_PREFIXES, '/usr/bin', '/bin', '/usr/sbin', '/sbin'])

PACKAGE_PATH: dict[FileSystemPath, str] = {
    FileSystemPath('/usr/bin/awk'): 'gawk',
    FileSystemPath('/usr/bin/flock'): 'flock',
    FileSystemPath('/usr/bin/python3'): 'python',
}


class HomebrewEngine(PackageManagerEngine):
    install_command = Command('install')

    def prepare_command(self) -> tuple[Command, Command]:
        """
        Prepare installation command for Homebrew, which refuses to run under ``sudo``.

        Homebrew does not run as ``root`` either, so there is no ``sudo_prefix`` to
        apply, and a guest logged in as ``root`` cannot use it at all.
        """

        if self.guest.facts.is_superuser:
            raise GeneralError(
                f"Homebrew does not run as root, log in to guest '{self.guest.name}' as "
                "a regular user and use 'become' for elevated privileges."
            )

        return (
            Command('env', f'PATH={HOMEBREW_PATH}', 'HOMEBREW_NO_AUTO_UPDATE=1', 'brew'),
            Command(),
        )

    def path_to_package(self, path: FileSystemPath) -> Package:
        """
        Find a formula providing given filesystem path.

        Homebrew cannot look up files outside its prefix, support a fixed set of mappings.
        """

        if path in PACKAGE_PATH:
            return Package(PACKAGE_PATH[path])

        raise GeneralError(f"Unsupported package path '{path}' for Homebrew.")

    def _reduce_to_packages(self, *installables: Installable) -> ReducedPackages:
        packages: ReducedPackages = []

        for installable in installables:
            if isinstance(installable, (Package, PackagePath)):
                packages.append(installable)

            elif isinstance(installable, FileSystemPath):
                packages.append(self.path_to_package(installable))

            else:
                raise tmt.utils.PrepareError(
                    f"Package manager 'homebrew' does not support installing from a remote "
                    f"URL '{installable}'."
                )

        return packages

    def _assert_supported_options(self, options: Options) -> None:
        if options.excluded_packages:
            raise tmt.utils.PrepareError(
                "Package manager 'homebrew' does not support excluding packages."
            )

    def _construct_presence_script(
        self, *installables: Installable
    ) -> tuple[ReducedPackages, ShellScript]:
        reduced_packages = self._reduce_to_packages(*installables)

        shell_script = ShellScript(
            f'{self.command.to_script()} list --versions '
            f'{" ".join(escape_installables(*reduced_packages))}'
        )

        return reduced_packages, shell_script

    def check_presence(self, *installables: Installable) -> ShellScript:
        return self._construct_presence_script(*installables)[1]

    def refresh_metadata(self) -> ShellScript:
        return ShellScript(f'{self.command.to_script()} update')

    def enable_repo(self, *repo_ids: str) -> ShellScript:
        raise tmt.utils.PrepareError(
            "Package manager 'homebrew' does not support enabling repositories."
        )

    def disable_repo(self, *repo_ids: str) -> ShellScript:
        raise tmt.utils.PrepareError(
            "Package manager 'homebrew' does not support disabling repositories."
        )

    def install(
        self,
        *installables: Installable,
        options: Optional[Options] = None,
    ) -> ShellScript:
        options = options or Options()

        self._assert_supported_options(options)

        packages = self._reduce_to_packages(*installables)

        script = ShellScript(
            f'{self.command.to_script()} {self.install_command.to_script()} '
            f'{" ".join(escape_installables(*packages))}'
        )

        if options.skip_missing:
            script = script | ShellScript('/bin/true')

        return script

    def reinstall(
        self,
        *installables: Installable,
        options: Optional[Options] = None,
    ) -> ShellScript:
        options = options or Options()

        self._assert_supported_options(options)

        packages = self._reduce_to_packages(*installables)

        script = ShellScript(
            f'{self.command.to_script()} reinstall {" ".join(escape_installables(*packages))}'
        )

        if options.skip_missing:
            script = script | ShellScript('/bin/true')

        return script

    def install_debuginfo(
        self,
        *installables: Installable,
        options: Optional[Options] = None,
    ) -> ShellScript:
        raise tmt.utils.GeneralError("There is no support for debuginfo packages in Homebrew.")


@provides_package_manager('homebrew')
class Homebrew(PackageManager[HomebrewEngine]):
    NAME = 'homebrew'

    _engine_class = HomebrewEngine

    _FAILED_PACKAGE_INSTALLATION_PATTERNS = [
        re.compile(r'No available formula with the name "([^"]+)"', re.IGNORECASE),
    ]

    # Probed after the package managers with the default priority: a Linux guest with
    # Homebrew under one of the prefixes keeps its native package manager.
    probe_priority = -10

    # Probe only the prefixes the engine can run, `brew` elsewhere on the `PATH` would be
    # detected and then fail to run.
    probe_command = ShellScript(
        ' || '.join(f'test -x {prefix}/brew' for prefix in HOMEBREW_PREFIXES)
    ).to_shell_command()

    def check_presence(self, *installables: Installable) -> dict[Installable, bool]:
        reduced_packages, presence_script = self.engine._construct_presence_script(*installables)

        try:
            output = self.guest.execute(presence_script)
            stdout = output.stdout

        except RunError as exc:
            stdout = exc.stdout

        if stdout is None:
            raise GeneralError("Homebrew presence check output provided no output")

        results: dict[Installable, bool] = {}

        for installable, package in zip(installables, reduced_packages):
            # Aliases such as `python` are listed under the formula they resolve to, `python@3.14`.
            match = re.search(rf'^{re.escape(str(package))}(@\S+)?\s', stdout, re.MULTILINE)

            results[installable] = match is not None

        return results

    def install_debuginfo(
        self,
        *installables: Installable,
        options: Optional[Options] = None,
    ) -> CommandOutput:
        raise tmt.utils.PrepareError(
            f'Package manager "{self.guest.facts.package_manager}" does not support '
            'installing debuginfo packages.'
        )

    def install_local(
        self,
        *installables: Installable,
        options: Optional[Options] = None,
    ) -> CommandOutput:
        raise tmt.utils.PrepareError(
            f'Package manager "{self.guest.facts.package_manager}" does not support '
            'installing local packages.'
        )
