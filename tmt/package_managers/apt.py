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
    Environment,
    EnvVarValue,
    GeneralError,
    RunError,
    ShellScript,
    )

ReducedPackages = list[Union[Package, PackagePath]]


@provides_package_manager('apt')
class Apt(tmt.package_managers.PackageManager):
    NAME = 'apt'

    probe_command = Command('apt', '--version')

    install_command = Command('install')

    _sudo_prefix: Command

    def prepare_command(self) -> tuple[Command, Command]:
        """ Prepare installation command for apt """

        if self.guest.facts.is_superuser is False:
            self._sudo_prefix = Command('sudo')

        else:
            self._sudo_prefix = Command()

        command = Command()
        options = Command('-y')

        command += self._sudo_prefix
        command += Command('apt')

        return (command, options)

    def _enable_apt_file(self) -> None:
        self.install(Package('apt-file'))
        self.guest.execute(ShellScript(f'{self._sudo_prefix} apt-file update'))

    def path_to_package(self, path: FileSystemPath) -> Package:
        """
        Find a package providing given filesystem path.

        This is not trivial as some are used to from ``yum`` or ``dnf``,
        it requires installation of ``apt-file`` utility and building
        an index of packages and filesystem paths.
        """

        self._enable_apt_file()

        output = self.guest.execute(ShellScript(f'apt-file search {path} || exit 0'))

        assert output.stdout is not None

        package_names = output.stdout.strip().splitlines()

        if not package_names:
            raise GeneralError(f"No package provides {path}.")

        return Package(package_names[0].split(':')[0])

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

        return reduced_packages, ShellScript(
            f'dpkg-query --show {" ".join(escape_installables(*reduced_packages))}')

    def check_presence(self, *installables: Installable) -> dict[Installable, bool]:
        reduced_packages, presence_script = self._construct_presence_script(*installables)

        try:
            output = self.guest.execute(presence_script)
            stdout, stderr = output.stdout, output.stderr

        except RunError as exc:
            stdout, stderr = exc.stdout, exc.stderr

        if stdout is None or stderr is None:
            raise GeneralError("apt presence check provided no output")

        results: dict[Installable, bool] = {}

        for installable, package in zip(installables, reduced_packages):
            match = re.search(
                rf'dpkg-query: no packages found matching {re.escape(str(package))}', stderr)

            if match is not None:
                results[installable] = False
                continue

            match = re.search(rf'^{re.escape(str(package))}\s', stdout)

            if match is not None:
                results[installable] = True
                continue

        return results

    def _extra_options(self, options: Options) -> Command:
        extra_options = Command()

        if options.skip_missing:
            extra_options += Command('--ignore-missing')

        return extra_options

    def install(
            self,
            *installables: Installable,
            options: Optional[Options] = None) -> CommandOutput:
        options = options or Options()

        extra_options = self._extra_options(options)
        packages = self._reduce_to_packages(*installables)

        script = ShellScript(
            f'{self.command.to_script()} install '
            f'{self.options.to_script()} {extra_options} '
            f'{" ".join(escape_installables(*packages))}')

        if options.check_first:
            script = self._construct_presence_script(*packages)[1] | script

        # TODO: find a better way to handle `skip_missing`, this may hide other
        # kinds of errors. But `--ignore-missing` does not turn exit code into
        # zero :/
        if options.skip_missing:
            script = script | ShellScript('/bin/true')

        return self.guest.execute(script, env=Environment({
            'DEBIAN_FRONTEND': EnvVarValue('noninteractive')
            }))

    def reinstall(
            self,
            *installables: Installable,
            options: Optional[Options] = None) -> CommandOutput:
        options = options or Options()

        extra_options = self._extra_options(options)
        packages = self._reduce_to_packages(*installables)

        script = ShellScript(
            f'{self.command.to_script()} reinstall '
            f'{self.options.to_script()} {extra_options} '
            f'{" ".join(escape_installables(*packages))}')

        if options.check_first:
            script = self._construct_presence_script(*packages)[1] & script

        if options.skip_missing:
            script = script | ShellScript('/bin/true')

        return self.guest.execute(script, env=Environment({
            'DEBIAN_FRONTEND': EnvVarValue('noninteractive')
            }))

    def install_debuginfo(
            self,
            *installables: Installable,
            options: Optional[Options] = None) -> CommandOutput:
        raise tmt.utils.GeneralError("There is no support for debuginfo packages in apt.")
