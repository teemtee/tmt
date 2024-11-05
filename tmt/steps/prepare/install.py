import dataclasses
import re
import shutil
from collections.abc import Iterator
from typing import Any, Literal, Optional, TypeVar, Union, cast

import fmf
import fmf.utils

import tmt
import tmt.base
import tmt.log
import tmt.options
import tmt.package_managers
import tmt.steps
import tmt.steps.prepare
import tmt.utils
from tmt.package_managers import (
    FileSystemPath,
    Installable,
    Options,
    Package,
    PackagePath,
    PackageUrl,
    )
from tmt.result import PhaseResult
from tmt.steps.provision import Guest
from tmt.utils import Command, Path, ShellScript, field

COPR_URL = 'https://copr.fedorainfracloud.org/coprs'


T = TypeVar('T')


class InstallBase(tmt.utils.Common):
    """ Base class for installation implementations """

    guest: Guest

    skip_missing: bool = False
    exclude: list[Package]

    packages: list[Union[Package, FileSystemPath]]
    local_packages: list[PackagePath]
    remote_packages: list[PackageUrl]
    debuginfo_packages: list[Package]

    package_directory: Path

    def __init__(
            self,
            *,
            parent: 'PrepareInstall',
            guest: Guest,
            dependencies: list[tmt.base.DependencySimple],
            directories: list[Path],
            exclude: list[str],
            logger: tmt.log.Logger,
            **kwargs: Any) -> None:
        """ Initialize installation data """
        super().__init__(logger=logger, parent=parent, relative_indent=0, guest=guest, **kwargs)

        if not dependencies and not directories:
            self.debug("No packages for installation found.", level=3)

        self.guest = guest
        self.exclude = [Package(package) for package in exclude]

        self.skip_missing = bool(parent.get('missing') == 'skip')

        # Prepare package lists and installation command
        self.prepare_installables(dependencies, directories)

    def prepare_installables(
            self,
            dependencies: list[tmt.base.DependencySimple],
            directories: list[Path]) -> None:
        """ Process package names and directories """
        self.packages = []
        self.local_packages = []
        self.remote_packages = []
        self.debuginfo_packages = []

        # Detect local, debuginfo and repository packages
        for dependency in dependencies:
            if re.match(r"^http(s)?://", dependency):
                self.remote_packages.append(PackageUrl(dependency))
            elif dependency.endswith(".rpm"):
                self.local_packages.append(PackagePath(dependency))
            elif re.search(r"-debug(info|source)(\.|$)", dependency):
                # Strip the '-debuginfo' string from package name
                # (installing with it doesn't work on RHEL7)
                self.debuginfo_packages.append(
                    Package(
                        re.sub(
                            r"-debuginfo((?=\.)|$)",
                            "",
                            str(dependency))))

            elif dependency.startswith('/'):
                self.packages.append(FileSystemPath(dependency))

            else:
                self.packages.append(Package(dependency))

        # Check rpm packages in local directories
        for directory in directories:
            self.info('directory', directory, 'green')
            if not directory.is_dir():
                raise tmt.utils.PrepareError(f"Packages directory '{directory}' not found.")
            for filepath in directory.iterdir():
                if filepath.suffix == '.rpm':
                    self.debug(f"Found rpm '{filepath}'.", level=3)
                    self.local_packages.append(PackagePath(filepath))

    def prepare_repository(self) -> None:
        """ Configure additional repository """
        raise NotImplementedError

    def list_installables(self, title: str, *installables: Installable) -> Iterator[Installable]:
        """ Show package info and return package names """

        # Show a brief summary by default
        if not self.verbosity_level:
            summary = fmf.utils.listed(installables, max=3)
            self.info(title, summary, 'green')
        # Provide a full list of packages in verbose mode
        else:
            summary = fmf.utils.listed(installables, 'package')
            self.info(title, summary + ' requested', 'green')
            for package in sorted(installables):
                self.verbose(str(package), shift=1)

        yield from installables

    def prepare_install_local(self) -> None:
        """ Copy packages to the test system """
        assert self.parent is not None
        # FIXME: cast() - https://github.com/teemtee/tmt/issues/1372
        workdir = cast(PrepareInstall, self.parent).step.workdir
        if not workdir:
            raise tmt.utils.GeneralError('workdir should not be empty')
        self.package_directory = workdir / 'packages'
        self.package_directory.mkdir(parents=True)

        # Copy local packages into workdir, push to guests
        for package in self.local_packages:
            self.verbose(package.name, shift=1)
            self.debug(f"Copy '{package}' to '{self.package_directory}'.", level=3)
            shutil.copy(package, self.package_directory)
        self.guest.push()

    def install_from_repository(self) -> None:
        """ Default base install method for packages from repositories """

    def install_local(self) -> None:
        """ Default base install method for local packages """

    def install_from_url(self) -> None:
        """ Default base install method for packages which are from URL """

    def install_debuginfo(self) -> None:
        """ Default base install method for debuginfo packages """

    def install(self) -> None:
        """ Perform the actual installation """
        try:
            self._install()

        except Exception as exc1:
            # We do not have any special handling for exceptions raised by the following code.
            # Wrapping them with try/except gives us a chance to attach the original exception
            # to whatever the code may raise, and therefore preserve the information attached
            # to the original exception.
            try:
                # Refresh cache in case of recent but not updated change do repodata
                self.guest.package_manager.refresh_metadata()
                self._install()

            except Exception as exc2:
                raise exc2 from exc1

    def _install(self) -> None:
        """ Helper method to perform the actual installation steps """
        if self.local_packages:
            self.prepare_install_local()
            self.install_local()
        if self.remote_packages:
            self.install_from_url()
        if self.packages:
            self.install_from_repository()
        if self.debuginfo_packages:
            self.install_debuginfo()

    def rpm_check(self, package: str, mode: str = '-q') -> None:
        """
        Run rpm command to check package existence
        Throws tmt.utils.RunError
        """
        output = self.guest.execute(Command('rpm', mode, package), silent=True)
        assert output.stdout
        self.debug(f"Package '{output.stdout.strip()}' already installed.")


class Copr(tmt.utils.Common):
    copr_plugin: str

    guest: Guest

    # Keep this method around, to correctly support Python's method resolution order.
    def __init__(self, *args: Any, guest: Guest, **kwargs: Any) -> None:
        super().__init__(*args, guest=guest, **kwargs)

        self.guest = guest

    def enable_copr_epel6(self, copr: str) -> None:
        """ Manually enable copr repositories for epel6 """
        # Parse the copr repo name
        matched = re.match("^(@)?([^/]+)/([^/]+)$", copr)
        if not matched:
            raise tmt.utils.PrepareError(f"Invalid copr repository '{copr}'.")
        group, name, project = matched.groups()
        group = 'group_' if group else ''
        # Prepare the repo file url
        parts = [COPR_URL] + (['g'] if group else [])
        parts += [name, project, 'repo', 'epel-6']
        parts += [f"{group}{name}-{project}-epel-6.repo"]
        url = '/'.join(parts)
        # Download the repo file on guest
        try:
            self.guest.execute(Command('curl', '-LOf', url),
                               cwd=Path('/etc/yum.repos.d'), silent=True)
        except tmt.utils.RunError as error:
            if error.stderr and 'not found' in error.stderr.lower():
                raise tmt.utils.PrepareError(
                    f"Copr repository '{copr}' not found.")
            raise

    def enable_copr(self, repositories: list[str]) -> None:
        """ Enable requested copr repositories """

        if not repositories:
            return

        # Try to install copr plugin
        self.debug('Make sure the copr plugin is available.')
        try:
            self.guest.package_manager.install(Package(self.copr_plugin))

        # Enable repositories manually for epel6
        except tmt.utils.RunError:
            for repository in repositories:
                self.info('copr', repository, 'green')
                self.enable_copr_epel6(repository)

        # Enable repositories using copr plugin
        else:
            for repository in repositories:
                self.info('copr', repository, 'green')

                self.guest.execute(ShellScript(
                    f"{self.guest.package_manager.command.to_script()} copr "
                    f"{self.guest.package_manager.options.to_script()} enable -y {repository}"
                    ))


class InstallDnf(InstallBase, Copr):
    """ Install packages using dnf """

    copr_plugin = "dnf-plugins-core"

    def install_local(self) -> None:
        """ Install packages stored in a local directory """

        # Use both dnf install/reinstall to get all packages refreshed
        # FIXME Simplify this once BZ#1831022 is fixed/implemented.
        filelist = [PackagePath(self.package_directory / filename.name)
                    for filename in self.local_packages]

        self.guest.package_manager.install(
            *filelist,
            options=Options(
                excluded_packages=self.exclude,
                skip_missing=self.skip_missing,
                check_first=False
                )
            )

        self.guest.package_manager.reinstall(
            *filelist,
            options=Options(
                excluded_packages=self.exclude,
                skip_missing=self.skip_missing,
                check_first=False
                )
            )

        summary = fmf.utils.listed([str(path) for path in self.local_packages], 'local package')
        self.info('total', f"{summary} installed", 'green')

    def install_from_url(self) -> None:
        """ Install packages stored on a remote URL """

        self.guest.package_manager.install(
            *self.list_installables("remote package", *self.remote_packages),
            options=Options(
                excluded_packages=self.exclude,
                skip_missing=self.skip_missing
                )
            )

    def install_from_repository(self) -> None:
        """ Install packages from a repository """

        self.guest.package_manager.install(
            *self.list_installables("package", *self.packages),
            options=Options(
                excluded_packages=self.exclude,
                skip_missing=self.skip_missing
                )
            )

    def install_debuginfo(self) -> None:
        """ Install debuginfo packages """
        packages = self.list_installables("debuginfo", *self.debuginfo_packages)

        self.guest.package_manager.install_debuginfo(
            *packages,
            options=Options(
                excluded_packages=self.exclude,
                skip_missing=self.skip_missing
                )
            )

        # Check the packages are installed on the guest because 'debuginfo-install'
        # returns 0 even though it didn't manage to install the required packages
        if not self.skip_missing:
            self.guest.package_manager.check_presence(
                *[Package(f'{package}-debuginfo') for package in self.debuginfo_packages])


class InstallDnf5(InstallDnf):
    """ Install packages using dnf5 """

    copr_plugin = "dnf5-command(copr)"


class InstallYum(InstallDnf):
    """ Install packages using yum """

    copr_plugin = "yum-plugin-copr"


class InstallRpmOstree(InstallBase, Copr):
    """ Install packages using rpm-ostree """

    copr_plugin = "dnf-plugins-core"

    recommended_packages: list[Union[Package, FileSystemPath]]
    required_packages: list[Union[Package, FileSystemPath]]

    def enable_copr(self, repositories: list[str]) -> None:
        """ Enable requested copr repositories """

        # rpm-ostree can step outside of its zone of competence, and use
        # another package manager to enable copr. We just need to cheat
        # the `InstallDnf5` & swap guest's package manager for `dnf5`
        # for a moment.
        self.guest.facts.package_manager = 'dnf5'
        # TODO: wouldn't it be nice if we could just call copr method
        # without populating `dependencies` & co. with dummy values.
        InstallDnf5(
            parent=cast('PrepareInstall', self.parent),
            guest=self.guest,
            dependencies=[],
            directories=[],
            exclude=[],
            logger=self._logger).enable_copr(repositories)
        self.guest.facts.package_manager = 'rpm-ostree'

    def sort_packages(self) -> None:
        """ Identify required and recommended packages """
        self.recommended_packages = []
        self.required_packages = []
        for package in self.packages:
            presence = self.guest.package_manager.check_presence(package)

            if not all(presence.values()):
                if self.skip_missing:
                    self.recommended_packages.append(package)
                else:
                    self.required_packages.append(package)

    def install_debuginfo(self) -> None:
        """ Install debuginfo packages """
        self.warn("Installation of debuginfo packages not supported yet.")

    def install_local(self) -> None:
        """ Install copied local packages """
        local_packages_installed: list[PackagePath] = []
        for package in self.local_packages:
            try:
                self.guest.package_manager.install(
                    PackagePath(self.package_directory / package.name),
                    options=Options(
                        check_first=False
                        )
                    )
                local_packages_installed.append(package)
            except tmt.utils.RunError as error:
                self.warn(f"Local package '{package}' not installed: {error.stderr}")
        summary = fmf.utils.listed(local_packages_installed, 'local package')
        self.info('total', f"{summary} installed", 'green')

    def install_from_repository(self) -> None:
        """ Install packages from the repository """
        self.sort_packages()

        # Install recommended packages
        if self.recommended_packages:
            self.list_installables("package", *self.recommended_packages)
            for package in self.recommended_packages:
                try:
                    self.guest.package_manager.install(package)
                except tmt.utils.RunError as error:
                    self.debug(f"Package installation failed: {error}")
                    self.warn(f"Unable to install recommended package '{package}'.")
                    continue

        # Install required packages
        if self.required_packages:
            self.guest.package_manager.install(
                *self.list_installables("package", *self.required_packages))


class InstallApt(InstallBase):
    """ Install packages using apt """

    def install_local(self) -> None:
        """ Install packages stored in a local directory """

        filelist = [PackagePath(self.package_directory / filename)
                    for filename in self.local_packages]

        self.guest.package_manager.install(
            *self.list_installables('local packages', *filelist),
            options=Options(
                excluded_packages=self.exclude,
                skip_missing=self.skip_missing,
                check_first=False
                )
            )

        summary = fmf.utils.listed([str(path) for path in self.local_packages], 'local package')
        self.info('total', f"{summary} installed", 'green')

    def install_from_url(self) -> None:
        """ Install packages stored on a remote URL """

        self.guest.package_manager.install(
            *self.list_installables("remote package", *self.remote_packages),
            options=Options(
                excluded_packages=self.exclude,
                skip_missing=self.skip_missing
                )
            )

    def install_from_repository(self) -> None:
        """ Install packages from a repository """

        self.guest.package_manager.install(
            *self.list_installables("package", *self.packages),
            options=Options(
                excluded_packages=self.exclude,
                skip_missing=self.skip_missing
                )
            )

    def install_debuginfo(self) -> None:
        """ Install debuginfo packages """
        packages = self.list_installables("debuginfo", *self.debuginfo_packages)

        self.guest.package_manager.install_debuginfo(
            *packages,
            options=Options(
                excluded_packages=self.exclude,
                skip_missing=self.skip_missing
                )
            )

        # Check the packages are installed on the guest because 'debuginfo-install'
        # returns 0 even though it didn't manage to install the required packages
        if not self.skip_missing:
            self.guest.package_manager.check_presence(
                *[Package(f'{package}-debuginfo') for package in self.debuginfo_packages])


class InstallApk(InstallBase):
    """ Install packages using apk """

    def install_local(self) -> None:
        """ Install packages stored in a local directory """

        filelist = [PackagePath(self.package_directory / filename)
                    for filename in self.local_packages]

        self.guest.package_manager.install(
            *self.list_installables('local packages', *filelist),
            options=Options(
                excluded_packages=self.exclude,
                skip_missing=self.skip_missing,
                allow_untrusted=True,
                check_first=False
                )
            )

        summary = fmf.utils.listed([str(path) for path in self.local_packages], 'local package')
        self.info('total', f"{summary} installed", 'green')

    def install_from_url(self) -> None:
        """ Install packages stored on a remote URL """

        raise tmt.utils.PrepareError(
            f'Package manager "{self.guest.facts.package_manager}" '
            'does not support installing from a remote URL.')

    def install_from_repository(self) -> None:
        """ Install packages from a repository """

        self.guest.package_manager.install(
            *self.list_installables("package", *self.packages),
            options=Options(
                excluded_packages=self.exclude,
                skip_missing=self.skip_missing
                )
            )

    def install_debuginfo(self) -> None:
        """ Install debuginfo packages """

        raise tmt.utils.PrepareError(
            f'Package manager "{self.guest.facts.package_manager}" does not support '
            'installing debuginfo packages.')


@dataclasses.dataclass
class PrepareInstallData(tmt.steps.prepare.PrepareStepData):
    package: list[tmt.base.DependencySimple] = field(
        default_factory=list,
        option=('-p', '--package'),
        metavar='PACKAGE',
        multiple=True,
        help='Package name or path to rpm to be installed.',
        # PrepareInstall supports *simple* requirements only
        normalize=lambda key_address, value, logger: tmt.base.assert_simple_dependencies(
            tmt.base.normalize_require(key_address, value, logger),
            "'install' plugin support simple packages only, no fmf links are allowed",
            logger),
        serialize=lambda packages: [package.to_spec() for package in packages],
        unserialize=lambda serialized: [
            tmt.base.DependencySimple.from_spec(package)
            for package in serialized
            ]
        )

    directory: list[Path] = field(
        default_factory=list,
        option=('-D', '--directory'),
        metavar='PATH',
        multiple=True,
        help='Path to a local directory with rpm packages.',
        normalize=tmt.utils.normalize_path_list
        )

    copr: list[str] = field(
        default_factory=list,
        option=('-c', '--copr'),
        metavar='REPO',
        multiple=True,
        help='Copr repository to be enabled.',
        normalize=tmt.utils.normalize_string_list
        )

    exclude: list[str] = field(
        default_factory=list,
        option=('-x', '--exclude'),
        metavar='PACKAGE',
        multiple=True,
        help='Packages to be skipped during installation.',
        normalize=tmt.utils.normalize_string_list
        )

    # TODO: use enum
    missing: Literal['skip', 'fail'] = field(
        default='fail',
        option=('-m', '--missing'),
        metavar='ACTION',
        choices=['fail', 'skip'],
        help='Action on missing packages, fail (default) or skip.'
        )


@tmt.steps.provides_method('install')
class PrepareInstall(tmt.steps.prepare.PreparePlugin[PrepareInstallData]):
    """
    Install packages on the guest.

    Example config:

    .. code-block:: yaml

        prepare:
            how: install
            copr: psss/tmt
            package: tmt-all
            missing: fail

    Use ``copr`` for enabling desired Copr repository and ``missing`` to choose
    whether missing packages should be silently ignored (``skip``) or a
    preparation error should be reported (``fail``), which is the default.

    In addition to package name you can also use one or more paths to
    local rpm files to be installed:

    .. code-block:: yaml

        prepare:
            how: install
            package:
                - tmp/RPMS/noarch/tmt-0.15-1.fc31.noarch.rpm
                - tmp/RPMS/noarch/python3-tmt-0.15-1.fc31.noarch.rpm

    Use ``directory`` to install all packages from given folder and
    ``exclude`` to skip selected packages:

    .. code-block:: yaml

        prepare:
            how: install
            directory: tmp/RPMS/noarch
            exclude: tmt+provision-virtual

    .. note::

        When testing ostree booted deployments tmt will use
        ``rpm-ostree`` as the package manager to perform the installation of
        requested packages. The current limitations of the ``rpm-ostree``
        implementation are:

        * Cannot install new version of already installed local rpm.
        * No support for installing debuginfo packages at this time.
    """

    _data_class = PrepareInstallData

    def go(
            self,
            *,
            guest: 'Guest',
            environment: Optional[tmt.utils.Environment] = None,
            logger: tmt.log.Logger) -> list[PhaseResult]:
        """ Perform preparation for the guests """
        results = super().go(guest=guest, environment=environment, logger=logger)

        # Nothing to do in dry mode
        if self.is_dry_run:
            return results

        # Pick the right implementation
        # TODO: it'd be nice to use a "plugin registry" and make the
        # implementations discovered as any other plugins. Package managers are
        # shipped as plugins, but we still need a matching *installation* class.
        # But do we really need a class per package manager family? Maybe the
        # code could be integrated into package manager plugins directly.
        if guest.facts.package_manager == 'rpm-ostree':
            installer: InstallBase = InstallRpmOstree(
                logger=logger,
                parent=self,
                dependencies=self.data.package,
                directories=self.data.directory,
                exclude=self.data.exclude,
                guest=guest)

        elif guest.facts.package_manager == 'dnf5':
            installer = InstallDnf5(
                logger=logger,
                parent=self,
                dependencies=self.data.package,
                directories=self.data.directory,
                exclude=self.data.exclude,
                guest=guest)

        elif guest.facts.package_manager == 'dnf':
            installer = InstallDnf(
                logger=logger,
                parent=self,
                dependencies=self.data.package,
                directories=self.data.directory,
                exclude=self.data.exclude,
                guest=guest)

        elif guest.facts.package_manager == 'yum':
            installer = InstallYum(
                logger=logger,
                parent=self,
                dependencies=self.data.package,
                directories=self.data.directory,
                exclude=self.data.exclude,
                guest=guest)

        elif guest.facts.package_manager == 'apt':
            installer = InstallApt(
                logger=logger,
                parent=self,
                dependencies=self.data.package,
                directories=self.data.directory,
                exclude=self.data.exclude,
                guest=guest)

        elif guest.facts.package_manager == 'apk':
            installer = InstallApk(
                logger=logger,
                parent=self,
                dependencies=self.data.package,
                directories=self.data.directory,
                exclude=self.data.exclude,
                guest=guest)

        elif guest.facts.package_manager is None:
            raise tmt.utils.PrepareError('Unrecognized package manager.')

        else:
            raise tmt.utils.PrepareError(
                f"Package manager '{guest.facts.package_manager}' "
                "is not supported by 'prepare/install'.")

        # Enable copr repositories...
        if isinstance(installer, Copr):
            installer.enable_copr(self.data.copr)

        # ... and install packages.
        installer.install()

        return results
