import re
from typing import Optional, Union

import tmt.package_managers
import tmt.utils
from tmt.package_managers import (
    FileSystemPath,
    Installable,
    Options,
    Package,
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

PACKAGE_PATH: dict[FileSystemPath, str] = {
    FileSystemPath('/usr/bin/arch'): 'busybox',
    FileSystemPath('/usr/bin/flock'): 'flock',
    FileSystemPath('/usr/bin/python3'): 'python3',
    # Note: not used for anything serious, serves for unit tests as
    # an installable path.
    FileSystemPath('/usr/bin/dos2unix'): 'dos2unix'
    }


@provides_package_manager('apk')
class Apk(tmt.package_managers.PackageManager):
    NAME = 'apk'

    probe_command = Command('apk', '--version')

    install_command = Command('add')

    _sudo_prefix: Command

    def prepare_command(self) -> tuple[Command, Command]:
        """ Prepare installation command for apk """

        if self.guest.facts.is_superuser is False:
            self._sudo_prefix = Command('sudo')

        else:
            self._sudo_prefix = Command()

        command = Command()

        command += self._sudo_prefix
        command += Command('apk')

        return (command, Command())

    def path_to_package(self, path: FileSystemPath) -> Package:
        """
        Find a package providing given filesystem path.

        This is not easily possible in Alpine. There is `apk-file` utility
        available but it seems unrealiable. Support only a fixed set
        of mappings until a better solution is available.
        """

        if path in PACKAGE_PATH:
            return Package(PACKAGE_PATH[path])

        raise GeneralError(f"Unsupported package path '{path} for Alpine Linux.")

    def _reduce_to_packages(self, *installables: Installable) -> ReducedPackages:
        packages: ReducedPackages = []

        for installable in installables:
            if isinstance(installable, (Package, PackagePath)):
                packages.append(installable)

            elif isinstance(installable, FileSystemPath):
                packages.append(self.path_to_package(installable))

            else:
                raise GeneralError(f"Package specification '{installable}' is not supported.")

        return packages

    def _construct_presence_script(
            self, *installables: Installable) -> tuple[ReducedPackages, ShellScript]:
        reduced_packages = self._reduce_to_packages(*installables)

        shell_script = ShellScript(
            f'apk info -e {" ".join(escape_installables(*reduced_packages))}')

        return reduced_packages, shell_script

    def check_presence(self, *installables: Installable) -> dict[Installable, bool]:
        reduced_packages, presence_script = self._construct_presence_script(*installables)

        try:
            output = self.guest.execute(presence_script)
            stdout, stderr = output.stdout, output.stderr

        except RunError as exc:
            stdout, stderr = exc.stdout, exc.stderr

        if stdout is None or stderr is None:
            raise GeneralError("apk presence check output provided no output")

        results: dict[Installable, bool] = {}

        for installable, package in zip(installables, reduced_packages):
            match = re.search(rf'^{re.escape(str(package))}\s', stdout)

            if match is not None:
                results[installable] = True
                continue

            results[installable] = False

        return results

    def refresh_metadata(self) -> CommandOutput:
        script = ShellScript(
            f'{self.command.to_script()} update')

        return self.guest.execute(script)

    def install(
            self,
            *installables: Installable,
            options: Optional[Options] = None) -> CommandOutput:
        options = options or Options()

        packages = self._reduce_to_packages(*installables)

        script = ShellScript(
            f'{self.command.to_script()} {self.install_command.to_script()} '
            f'{"--allow-untrusted " if options.allow_untrusted else ""}'
            f'{" ".join(escape_installables(*packages))}')

        if options.check_first:
            script = self._construct_presence_script(*packages)[1] | script

        if options.skip_missing:
            script = script | ShellScript('/bin/true')

        return self.guest.execute(script)

    def reinstall(
            self,
            *installables: Installable,
            options: Optional[Options] = None) -> CommandOutput:
        options = options or Options()

        packages = self._reduce_to_packages(*installables)

        script = ShellScript(
            f'{self.command.to_script()} fix '
            f'{" ".join(escape_installables(*packages))}')

        if options.check_first:
            script = self._construct_presence_script(*packages)[1] & script

        if options.skip_missing:
            script = script | ShellScript('/bin/true')

        return self.guest.execute(script)

    def install_debuginfo(
            self,
            *installables: Installable,
            options: Optional[Options] = None) -> CommandOutput:
        raise tmt.utils.GeneralError("There is no support for debuginfo packages in apk.")
