import dataclasses
import re
import shutil
from typing import Literal, Optional, cast

import fmf
import fmf.utils

import tmt
import tmt.base
import tmt.log
import tmt.options
import tmt.steps
import tmt.steps.prepare
import tmt.utils
from tmt.steps.provision import Guest, GuestPackageManager
from tmt.utils import Command, Path, ShellScript, field

COPR_URL = 'https://copr.fedorainfracloud.org/coprs'


class InstallBase(tmt.utils.Common):
    """ Base class for installation implementations """

    # Each installer knows its package manager and copr plugin
    package_manager: str
    copr_plugin: str

    # Save a prepared command and options for package operations
    command: Command
    options: Command

    skip_missing: bool = False

    packages: list[str]
    directories: list[Path]
    exclude: list[str]

    local_packages: list[Path]
    remote_packages: list[str]
    debuginfo_packages: list[str]
    repository_packages: list[str]

    rpms_directory: Path

    def __init__(
            self,
            *,
            parent: 'PrepareInstall',
            guest: Guest,
            logger: tmt.log.Logger) -> None:
        """ Initialize installation data """
        super().__init__(logger=logger, parent=parent, relative_indent=0)
        self.guest = guest

        # Get package related data from the plugin
        self.packages = parent.get("package", [])
        self.directories = cast(list[Path], parent.get("directory", []))
        self.exclude = parent.get("exclude", [])

        if not self.packages and not self.directories:
            self.debug("No packages for installation found.", level=3)

        self.skip_missing = bool(parent.get('missing') == 'skip')

        # Prepare package lists and installation command
        self.prepare_packages()

        self.command, self.options = self.prepare_command()

        self.debug(f"Using '{self.command}' for all package operations.")
        self.debug(f"Options for package operations are '{self.options}'.")

    def prepare_packages(self) -> None:
        """ Process package names and directories """
        self.local_packages = []
        self.remote_packages = []
        self.debuginfo_packages = []
        self.repository_packages = []

        # Detect local, debuginfo and repository packages
        for package in self.packages:
            if re.match(r"^http(s)?://", package):
                self.remote_packages.append(package)
            elif package.endswith(".rpm"):
                self.local_packages.append(Path(package))
            elif re.search(r"-debug(info|source)(\.|$)", package):
                # Strip the '-debuginfo' string from package name
                # (installing with it doesn't work on RHEL7)
                package = re.sub(r"-debuginfo((?=\.)|$)", "", package)
                self.debuginfo_packages.append(package)
            else:
                self.repository_packages.append(package)

        # Check rpm packages in local directories
        for directory in self.directories:
            self.info('directory', directory, 'green')
            if not directory.is_dir():
                raise tmt.utils.PrepareError(f"Packages directory '{directory}' not found.")
            for filepath in directory.iterdir():
                if filepath.suffix == '.rpm':
                    self.debug(f"Found rpm '{filepath}'.", level=3)
                    self.local_packages.append(filepath)

    def prepare_command(self) -> tuple[Command, Command]:
        """ Prepare installation command and subcommand options """
        raise NotImplementedError

    def prepare_repository(self) -> None:
        """ Configure additional repository """
        raise NotImplementedError

    def operation_script(self, subcommand: Command, args: Command) -> ShellScript:
        """
        Render a shell script to perform the requested package operation.

        .. warning::

           Each and every argument from ``args`` **will be** sanitized by
           escaping. This is not compatible with operations that wish to use
           shell wildcards. Such operations need to be constructed manually.

        :param subcommand: package manager subcommand, e.g. ``install`` or ``erase``.
        :param args: arguments for the subcommand, e.g. package names.
        """

        return ShellScript(
            f"{self.command.to_script()} {subcommand.to_script()} "
            f"{self.options.to_script()} {args.to_script()}")

    def perform_operation(self, subcommand: Command, args: Command) -> tmt.utils.CommandOutput:
        """
        Perform the requested package operation.

        .. warning::

           Each and every argument from ``args`` **will be** sanitized by
           escaping. This is not compatible with operations that wish to use
           shell wildcards. Such operations need to be constructed manually.

        :param subcommand: package manager subcommand, e.g. ``install`` or ``erase``.
        :param args: arguments for the subcommand, e.g. package names.
        :returns: command output.
        """

        return self.guest.execute(self.operation_script(subcommand, args))

    def list_packages(self, packages: list[str], title: str) -> Command:
        """ Show package info and return package names """

        # Show a brief summary by default
        if not self.verbosity_level:
            summary = fmf.utils.listed(packages, max=3)
            self.info(title, summary, 'green')
        # Provide a full list of packages in verbose mode
        else:
            summary = fmf.utils.listed(packages, 'package')
            self.info(title, summary + ' requested', 'green')
            for package in sorted(packages):
                self.verbose(package, shift=1)

        return Command(*packages)

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

    def enable_copr(self) -> None:
        """ Enable requested copr repositories """
        # FIXME: cast() - https://github.com/teemtee/tmt/issues/1372
        coprs = cast(PrepareInstall, self.parent).get('copr')
        if not coprs:
            return
        # Try to install copr plugin
        self.debug('Make sure the copr plugin is available.')
        try:
            self.guest.execute(
                ShellScript(f'rpm -q {self.copr_plugin}')
                | self.operation_script(Command('install'), Command('-y', self.copr_plugin)),
                silent=True)
        # Enable repositories manually for epel6
        except tmt.utils.RunError:
            for copr in coprs:
                self.info('copr', copr, 'green')
                self.enable_copr_epel6(copr)
        # Enable repositories using copr plugin
        else:
            for copr in coprs:
                self.info('copr', copr, 'green')
                self.perform_operation(
                    Command('copr'),
                    Command('enable', '-y', copr)
                    )

    def prepare_install_local(self) -> None:
        """ Copy packages to the test system """
        assert self.parent is not None
        # FIXME: cast() - https://github.com/teemtee/tmt/issues/1372
        workdir = cast(PrepareInstall, self.parent).step.workdir
        if not workdir:
            raise tmt.utils.GeneralError('workdir should not be empty')
        self.rpms_directory = workdir / 'rpms'
        self.rpms_directory.mkdir(parents=True)

        # Copy local packages into workdir, push to guests
        for package in self.local_packages:
            self.verbose(package.name, shift=1)
            self.debug(f"Copy '{package}' to '{self.rpms_directory}'.", level=3)
            shutil.copy(package, self.rpms_directory)
        self.guest.push()

    def install_from_repository(self) -> None:
        """ Default base install method for packages from repositories """
        pass

    def install_local(self) -> None:
        """ Default base install method for local packages """
        pass

    def install_from_url(self) -> None:
        """ Default base install method for packages which are from URL """
        pass

    def install_debuginfo(self) -> None:
        """ Default base install method for debuginfo packages """
        pass

    def install(self) -> None:
        """ Perform the actual installation """
        if self.local_packages:
            self.prepare_install_local()
            self.install_local()
        if self.remote_packages:
            self.install_from_url()
        if self.repository_packages:
            self.install_from_repository()
        if self.debuginfo_packages:
            self.install_debuginfo()


class InstallDnf(InstallBase):
    """ Install packages using dnf """

    package_manager = "dnf"
    copr_plugin = "dnf-plugins-core"
    skip_missing_option = "--skip-broken"

    def prepare_command(self) -> tuple[Command, Command]:
        """ Prepare installation command """

        options = Command('-y')

        for package in self.exclude:
            options += Command('--exclude', package)

        command = Command()

        if self.guest.facts.is_superuser is False:
            command += Command('sudo')

        command += Command(self.package_manager)

        if self.skip_missing:
            options += Command(self.skip_missing_option)

        return (command, options)

    def install_local(self) -> None:
        """ Install copied local packages """
        # Use both dnf install/reinstall to get all packages refreshed
        # FIXME Simplify this once BZ#1831022 is fixed/implemeted.
        self.guest.execute(ShellScript(
            f"""
            {self.command.to_script()} install {self.options.to_script()} {self.rpms_directory}/*
            """
            ))
        self.guest.execute(ShellScript(
            f"""
            {self.command.to_script()} reinstall {self.options.to_script()} {self.rpms_directory}/*
            """
            ))

        summary = fmf.utils.listed([str(path) for path in self.local_packages], 'local package')
        self.info('total', f"{summary} installed", 'green')

    def install_from_url(self) -> None:
        """ Install packages directly from URL """
        self.perform_operation(
            Command('install'),
            self.list_packages(self.remote_packages, title="remote package")
            )

    def install_from_repository(self) -> None:
        """ Install packages from the repository """
        packages = self.list_packages(self.repository_packages, title="package")

        # Check and install
        self.guest.execute(
            ShellScript(f'rpm -q --whatprovides {packages.to_script()}')
            | self.operation_script(Command('install'), packages)
            )

    def install_debuginfo(self) -> None:
        """ Install debuginfo packages """
        packages = self.list_packages(self.debuginfo_packages, title="debuginfo")

        # Make sure debuginfo-install is present on the target system
        self.perform_operation(
            Command('install'),
            Command('-y', '/usr/bin/debuginfo-install')
            )

        command = Command('debuginfo-install', '-y')

        if self.skip_missing:
            command += Command('--skip-broken')

        command += packages

        self.guest.execute(command)

        # Check the packages are installed on the guest because 'debuginfo-install'
        # returns 0 even though it didn't manage to install the required packages
        if not self.skip_missing:
            packages_debuginfo = [f'{package}-debuginfo' for package in self.debuginfo_packages]
            command = Command('rpm', '-q', *packages_debuginfo)
            self.guest.execute(command)


class InstallDnf5(InstallDnf):
    """ Install packages using dnf5 """

    package_manager = "dnf5"
    copr_plugin = "dnf5-plugins"
    skip_missing_option = "--skip-unavailable"


class InstallYum(InstallDnf):
    """ Install packages using yum """

    package_manager = "yum"
    copr_plugin = "yum-plugin-copr"

    def install_from_repository(self) -> None:
        """ Install packages from the repository """
        packages = self.list_packages(self.repository_packages, title="package")

        # Extra ignore/check for yum to workaround BZ#1920176
        check = ShellScript(f'rpm -q --whatprovides {packages.to_script()}')
        script = check | self.operation_script(Command('install'), packages)

        if self.skip_missing:
            script |= ShellScript('true')
        else:
            script &= check

        # Check and install
        self.guest.execute(script)


class InstallRpmOstree(InstallBase):
    """ Install packages using rpm-ostree """

    package_manager = "rpm-ostree"
    copr_plugin = "dnf-plugins-core"

    def sort_packages(self) -> None:
        """ Identify required and recommended packages """
        self.recommended_packages = []
        self.required_packages = []
        for package in self.repository_packages:
            try:
                output = self.guest.execute(Command('rpm', '-q', package), silent=True)
                assert output.stdout
                self.debug(f"Package '{output.stdout.strip()}' already installed.")
            except tmt.utils.RunError:
                if self.skip_missing:
                    self.recommended_packages.append(package)
                else:
                    self.required_packages.append(package)

    def prepare_command(self) -> tuple[Command, Command]:
        """ Prepare installation command for rpm-ostree"""

        command = Command()

        if self.guest.facts.is_superuser is False:
            command += Command('sudo')

        command += Command('rpm-ostree')

        options = Command('--apply-live', '--idempotent', '--allow-inactive')

        for package in self.exclude:
            # exclude not supported in rpm-ostree
            self.warn(f"there is no support for rpm-ostree exclude. "
                      f"Package '{package}' may still be installed.")

        return (command, options)

    def install_debuginfo(self) -> None:
        """ Install debuginfo packages """
        self.warn("Installation of debuginfo packages not supported yet.")

    def install_local(self) -> None:
        """ Install copied local packages """
        local_packages_installed = []
        for package in self.local_packages:
            try:
                self.perform_operation(
                    Command('install'),
                    Command(f'{self.rpms_directory / package.name}')
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
            self.list_packages(self.recommended_packages, title="package")
            for package in self.recommended_packages:
                try:
                    self.perform_operation(
                        Command('install'),
                        Command(package)
                        )
                except tmt.utils.RunError as error:
                    self.debug(f"Package installation failed: {error}")
                    self.warn(f"Unable to install recommended package '{package}'.")
                    continue

        # Install required packages
        if self.required_packages:
            self.perform_operation(
                Command('install'),
                self.list_packages(self.required_packages, title="package")
                )


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
            environment: Optional[tmt.utils.EnvironmentType] = None,
            logger: tmt.log.Logger) -> None:
        """ Perform preparation for the guests """
        super().go(guest=guest, environment=environment, logger=logger)

        # Nothing to do in dry mode
        if self.is_dry_run:
            return

        # Pick the right implementation
        # TODO: it'd be nice to use a "plugin registry" and make the implementations
        # discovered as any other plugins.
        if guest.facts.package_manager == GuestPackageManager.RPM_OSTREE:
            installer: InstallBase = InstallRpmOstree(logger=logger, parent=self, guest=guest)

        elif guest.facts.package_manager == GuestPackageManager.DNF:
            installer = InstallDnf(logger=logger, parent=self, guest=guest)

        elif guest.facts.package_manager == GuestPackageManager.DNF5:
            installer = InstallDnf5(logger=logger, parent=self, guest=guest)

        elif guest.facts.package_manager == GuestPackageManager.YUM:
            installer = InstallYum(logger=logger, parent=self, guest=guest)

        else:
            raise tmt.utils.PrepareError(
                f'Package manager "{guest.facts.package_manager}" is not supported.')

        # Enable copr repositories and install packages
        installer.enable_copr()
        installer.install()
