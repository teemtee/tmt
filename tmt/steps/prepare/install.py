import itertools
import re
import shutil
from collections.abc import Iterator
from typing import Any, Literal, Optional, Union

import fmf.utils

import tmt.base.core
import tmt.log
import tmt.steps
import tmt.steps.prepare
import tmt.utils
from tmt.container import container, field
from tmt.guest import Guest, RebootMode
from tmt.package_managers import (
    FileSystemPath,
    Installable,
    Options,
    Package,
    PackagePath,
    PackageUrl,
)
from tmt.utils import Path
from tmt.utils.environment import Environment


@container
class PrepareInstallData(tmt.steps.prepare.PrepareStepData):
    package: list[tmt.base.core.DependencySimple] = field(
        default_factory=list,
        option=('-p', '--package'),
        metavar='PACKAGE',
        multiple=True,
        help='Package name or path to rpm to be installed.',
        # PrepareInstall supports *simple* requirements only
        normalize=lambda key_address, value, logger: tmt.base.core.assert_simple_dependencies(
            tmt.base.core.normalize_require(key_address, value, logger),
            "'install' plugin support simple packages only, no fmf links are allowed",
            logger,
        ),
        serialize=lambda packages: [package.to_spec() for package in packages],
        unserialize=lambda serialized: [
            tmt.base.core.DependencySimple.from_spec(package) for package in serialized
        ],
    )

    directory: list[Path] = field(
        default_factory=list,
        option=('-D', '--directory'),
        metavar='PATH',
        multiple=True,
        help='Path to a local directory with rpm packages.',
        normalize=tmt.utils.normalize_path_list,
    )

    copr: list[str] = field(
        default_factory=list,
        option=('-c', '--copr'),
        metavar='REPO',
        multiple=True,
        help='Copr repository to be enabled.',
        normalize=tmt.utils.normalize_string_list,
    )

    exclude: list[str] = field(
        default_factory=list,
        option=('-x', '--exclude'),
        metavar='PACKAGE',
        multiple=True,
        help='Packages to be skipped during installation.',
        normalize=tmt.utils.normalize_string_list,
    )

    # TODO: use enum
    missing: Literal['skip', 'fail'] = field(
        default='fail',
        option=('-m', '--missing'),
        metavar='ACTION',
        choices=['fail', 'skip'],
        help='Action on missing packages, fail (default) or skip.',
    )

    check_first: bool = field(
        default=True,
        option='--check-first / --no-check-first',
        is_flag=True,
        show_default=True,
        help='Check whether packages are already installed before attempting to install them.',
    )

    reboot: bool = field(
        default=False,
        option='--reboot / --no-reboot',
        is_flag=True,
        show_default=True,
        help='Reboot the guest after package installation if any package was installed.',
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

    Use ``copr`` for enabling a desired Copr repository and ``missing`` to choose
    whether missing packages should be silently ignored (``skip``) or a
    preparation error should be reported (``fail``), which is the default.

    One or more RPM packages can be specified under the
    ``package`` attribute. The packages will be installed
    on the guest. They can either be specified using their
    names, paths to local rpm files or urls to remote rpms.

    .. code-block:: yaml

        # Install local rpms using file path
        prepare:
            how: install
            package:
                - tmp/RPMS/noarch/tmt-0.15-1.fc31.noarch.rpm
                - tmp/RPMS/noarch/python3-tmt-0.15-1.fc31.noarch.rpm

    .. code-block:: yaml

        # Install remote packages using url
        prepare:
            how: install
            package:
              - https://dl.fedoraproject.org/pub/epel/epel-release-latest-8.noarch.rpm
              - https://dl.fedoraproject.org/pub/epel/epel-next-release-latest-8.noarch.rpm

    .. code-block:: yaml

        # Install the whole directory, exclude selected packages
        prepare:
            how: install
            directory:
              - tmp/RPMS/noarch
            exclude:
              - tmt+all
              - tmt+provision-virtual

    .. code-block:: yaml

        prepare:
            how: install
            # Repository with a group owner (@ prefixed) requires quotes, e.g.
            # copr: "@osci/rpminspect"
            copr: psss/tmt
            package: tmt-all
            missing: skip

    .. code-block:: yaml

        # Install a specific kernel build and reboot the guest
        prepare:
            how: install
            package: kernel-6.12.0-1.fc41.x86_64
            reboot: true

    Use ``reboot: true`` (or ``--reboot`` on the command line) to reboot
    the guest after the installation, e.g. to boot a newly installed
    kernel. The guest is rebooted only when the phase installed a
    package: at least one requested package which was not present on
    the guest before the installation is present after it. Local rpm
    files (paths or ``directory``) and remote package URLs cannot be
    checked by name, therefore requesting any of them always counts as
    an installation once the installation finishes. The reboot is
    skipped when:

    * all requested packages were already present on the guest. This
      applies with ``check-first: false`` as well, even if the package
      manager upgraded an already present package. Request the exact
      ``name-version-release.arch`` to install and boot a different
      build of an already present package such as ``kernel``.
    * none of the missing packages could be installed with
      ``missing: skip``.
    * the guest uses the ``bootc`` package manager, which reboots the
      guest into the newly built image on its own.

    The reboot is not supported on local, container and mock guests,
    the phase fails there before installing any packages. tmt does not
    change the boot loader configuration, the guest boots its default
    boot entry.

    .. note::

        When testing ostree booted deployments tmt will use
        ``rpm-ostree`` as the package manager to perform the installation of
        requested packages. The current limitations of the ``rpm-ostree``
        implementation are:

        * Cannot install new version of already installed local rpm.
        * No support for installing debuginfo packages at this time.
    """

    _data_class = PrepareInstallData
    #: A mapping of package installations to be replaced due to verified artifact
    #: prepare step. This needs to be unique for each guest.
    #:
    #: .. seealso:: :py:meth:`tmt.steps.prepare.artifact.PrepareArtifact._prepare_verify`
    artifact_override: dict[Guest, dict[Union[Package, FileSystemPath], Package]]

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.artifact_override = {}

    def _prepare_installables(
        self,
        dependencies: list[tmt.base.core.DependencySimple],
        directories: list[Path],
        logger: tmt.log.Logger,
    ) -> None:
        """
        Process package names and directories
        """

        self.packages: list[Union[Package, FileSystemPath]] = []
        self.local_packages: list[PackagePath] = []
        self.remote_packages: list[PackageUrl] = []
        self.debuginfo_packages: list[Package] = []

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
                    Package(re.sub(r"-debuginfo((?=\.)|$)", "", str(dependency)))
                )
            elif dependency.startswith('/'):
                self.packages.append(FileSystemPath(dependency))

            else:
                self.packages.append(Package(dependency))

        # Check rpm packages in local directories
        for directory in directories:
            self.info('directory', directory, color='green')
            if not directory.is_dir():
                raise tmt.utils.PrepareError(f"Packages directory '{directory}' not found.")
            for filepath in directory.iterdir():
                if filepath.suffix == '.rpm':
                    logger.debug(f"Found rpm '{filepath}'.", level=3)
                    self.local_packages.append(PackagePath(filepath))

    def _prepare_install_local(self, guest: 'Guest') -> None:
        """
        Copy packages to the test system
        """

        self.package_directory = self.step_workdir / guest.safe_name / 'packages'
        self.package_directory.mkdir(parents=True, exist_ok=True)

        for package in self.local_packages:
            self.verbose(package.name, shift=1)
            self.debug(f"Copy '{package}' to '{self.package_directory}'.", level=3)
            shutil.copy(package, self.package_directory)
        guest.push()

    def _list_installables(
        self,
        title: str,
        *installables: Installable,
    ) -> Iterator[Installable]:
        """
        Show package info and return package names.
        """

        # Show a brief summary by default
        if not self.verbosity_level:
            summary = fmf.utils.listed(installables, max=3)
            self.info(title, summary, color='green')
        # Provide a full list of packages in verbose mode
        else:
            summary = fmf.utils.listed(installables, 'package')
            self.info(title, summary + ' requested', color='green')
            for package in sorted(installables):
                self.verbose(str(package), shift=1)

        yield from installables

    def _resolve_packages(self, guest: 'Guest') -> list[Union[Package, FileSystemPath]]:
        """
        Return repository packages to install on the given guest.

        :param guest: guest the packages would be installed on.
        :returns: requested repository packages, with packages replaced
            by their verified artifact counterparts when the ``artifact``
            prepare plugin requested an override for the guest.
        """

        if artifact_override := self.artifact_override.get(guest):
            return [artifact_override.get(pkg, pkg) for pkg in self.packages]

        return self.packages

    def _debuginfo_presence_packages(self) -> list[Package]:
        """
        Return package names to check the presence of requested debuginfo packages.

        :returns: a ``<name>-debuginfo`` package for each requested
            debuginfo package.
        """

        return [Package(f"{name}-debuginfo") for name in self.debuginfo_packages]

    def _install(
        self,
        guest: 'Guest',
        options: Options,
    ) -> None:
        """
        Execute all installation steps and check for failures.
        """

        install_outputs: list[tmt.utils.CommandOutput] = []

        if self.local_packages:
            self._prepare_install_local(guest)
            local_packages = [
                PackagePath(self.package_directory / p.name) for p in self.local_packages
            ]
            install_outputs.append(
                guest.package_manager.install_local(
                    *self._list_installables('local package', *local_packages),
                    options=options,
                )
            )
            summary = fmf.utils.listed([str(p) for p in self.local_packages], 'local package')
            self.info('total', f"{summary} installed", color='green')

        if self.remote_packages:
            install_outputs.append(
                guest.package_manager.install(
                    *self._list_installables('remote package', *self.remote_packages),
                    options=options,
                )
            )

        if self.packages:
            install_outputs.append(
                guest.package_manager.install(
                    *self._list_installables('package', *self._resolve_packages(guest)),
                    options=options,
                )
            )

        if self.debuginfo_packages:
            install_outputs.append(
                guest.package_manager.install_debuginfo(
                    *self._list_installables('debuginfo', *self.debuginfo_packages),
                    options=options,
                )
            )

        install_outputs.append(guest.package_manager.finalize_installation())

        # For recommended packages (skip_missing=True), check output even if no exception
        # was raised, since --skip-broken makes the command succeed but packages still fail
        if options.skip_missing:
            failed_packages = self._extract_failed_packages_from_outputs(install_outputs, guest)
            # Output from yum is non-deterministic. It depends on order in which
            # the invalid debuginfo package is getting installed. If first, its error messages
            # are omitted. If after a valid package, the error messages are included.
            # So we're checking for presence on the system.
            if self.debuginfo_packages:
                presence = guest.package_manager.check_presence(
                    *self._debuginfo_presence_packages()
                )

                failed_packages.update(
                    str(package).removesuffix("-debuginfo")
                    for package, present in presence.items()
                    if not present
                )

            if failed_packages:
                self._show_failed_packages_with_tests(failed_packages)

    def _extract_failed_packages_from_outputs(
        self, outputs: list[tmt.utils.CommandOutput], guest: 'Guest'
    ) -> set[str]:
        """
        Extract package names from installation outputs.

        Returns a set of package names that failed to install.
        """

        def _extract_from_output(output: tmt.utils.CommandOutput) -> Iterator[str]:
            if output.stderr:
                yield from guest.package_manager.extract_package_name_from_package_manager_output(
                    output.stderr
                )

            if output.stdout:
                yield from guest.package_manager.extract_package_name_from_package_manager_output(
                    output.stdout
                )

        return set(
            itertools.chain.from_iterable(_extract_from_output(output) for output in outputs)
        )

    def _show_failed_packages_with_tests(self, failed_packages: set[str]) -> None:
        """
        Show failed packages and which tests require them.
        """
        # Get test dependencies from discover step
        required_dependencies_to_tests, recommended_dependencies_to_tests = (
            self.step.plan.discover.dependencies_to_tests
        )

        failed_required_packages: dict[str, list[str]] = {}
        failed_recommended_packages: dict[str, list[str]] = {}
        failed_unattributed_packages: set[str] = set()

        for failed_package in failed_packages:
            if tests := required_dependencies_to_tests.get(failed_package):
                failed_required_packages[failed_package] = sorted(tests)

            elif tests := recommended_dependencies_to_tests.get(failed_package):
                failed_recommended_packages[failed_package] = sorted(tests)

            else:
                failed_unattributed_packages.add(failed_package)

        self.info('')

        if failed_required_packages:
            self.info('Required packages failed to install, aborting:', color='red', shift=1)
            for pkg, tests in failed_required_packages.items():
                self.info(
                    pkg,
                    f'required by: {", ".join(tests)}',
                    color='red',
                    shift=2,
                )

        if failed_recommended_packages:
            self.info(
                'Recommended packages failed to install, continuing regardless:',
                color='yellow',
                shift=1,
            )
            for pkg, tests in failed_recommended_packages.items():
                self.info(
                    pkg,
                    f'recommended by: {", ".join(tests)}',
                    color='yellow',
                    shift=2,
                )

        if failed_unattributed_packages:
            self.info('Other failed packages:', color='red', shift=1)
            for pkg in sorted(failed_unattributed_packages):
                self.info(pkg, color='red', shift=2)

    def _validate_reboot(self, guest: 'Guest') -> None:
        """
        Validate that reboot after package installation is supported on the guest.

        :param guest: guest to reboot after package installation.
        :raises PrepareError: when the guest cannot be rebooted: a local
            guest, a container, or a mock chroot.
        """

        # Imported here to keep this prepare plugin from loading the mock
        # provision plugin module on import.
        from tmt.steps.provision.mock import GuestMock

        if guest.localhost:
            raise tmt.utils.PrepareError(
                "Reboot after package installation is not supported on local guest."
            )

        if guest.facts.is_container:
            raise tmt.utils.PrepareError(
                "Reboot after package installation is not supported on container guests."
            )

        if isinstance(guest, GuestMock):
            raise tmt.utils.PrepareError(
                "Reboot after package installation is not supported on mock guests."
            )

    def _has_unverifiable_installables(self) -> bool:
        """
        Check whether local rpm files or remote package URLs were requested.

        tmt knows only a path or a URL of these packages, not the names
        of packages they contain, and therefore cannot check their
        presence on the guest. Their installation always counts as
        a change of the guest.

        :returns: ``True`` if any local or remote package was requested.
        """

        return bool(self.local_packages or self.remote_packages)

    def _find_missing_installables(self, guest: 'Guest') -> list[Installable]:
        """
        Find requested packages which are not present on the guest.

        Repository packages and filesystem paths are checked, as well as
        debuginfo packages. Local rpm files and remote package URLs are
        not checked, see :py:meth:`_has_unverifiable_installables`.

        :param guest: guest to check.
        :returns: requested packages missing on the guest. Empty when
            local or remote packages were requested, because their
            installation counts as a change of the guest anyway.
        """

        if self._has_unverifiable_installables():
            return []

        installables: list[Installable] = [
            *self._resolve_packages(guest),
            *self._debuginfo_presence_packages(),
        ]

        if not installables:
            return []

        presence = guest.package_manager.check_presence(*installables)

        return [installable for installable, present in presence.items() if not present]

    def _were_packages_installed(
        self, guest: 'Guest', missing_installables: list[Installable]
    ) -> bool:
        """
        Decide whether the installation added any package to the guest.

        :param guest: guest the packages were installed on.
        :param missing_installables: requested packages which were not
            present on the guest before the installation, as reported by
            :py:meth:`_find_missing_installables`.
        :returns: ``True`` if local or remote packages were requested, or
            if any of ``missing_installables`` is now present on the
            guest. ``False`` otherwise.
        """

        if self._has_unverifiable_installables():
            self.debug('Local or remote packages requested, assuming they were installed.')
            return True

        if not missing_installables:
            return False

        presence = guest.package_manager.check_presence(*missing_installables)
        installed = sorted(
            str(installable) for installable, present in presence.items() if present
        )

        if not installed:
            return False

        self.debug(f"Packages installed: {fmf.utils.listed(installed)}.")
        return True

    def _reboot(self, guest: 'Guest', *, installed: bool) -> None:
        """
        Reboot the guest after package installation if needed.

        :param guest: guest to reboot.
        :param installed: whether the installation added any package to
            the guest. The reboot is skipped when not set.
        :raises PrepareError: when the reboot fails.
        """

        if not installed:
            self.debug("Skipping reboot as no packages were installed.")
            return

        # The `bootc` package manager switches the guest to a new image and
        # reboots it on its own, see `Bootc.build_container()`.
        if guest.facts.package_manager == 'bootc':
            self.debug("Reboot already handled by the 'bootc' package manager.")
            return

        self.info('reboot', 'Rebooting guest after package installation', color='green')

        try:
            rebooted = guest.reboot(mode=RebootMode.SOFT)

        # `RebootModeNotSupportedError` and provision plugin specific errors
        # are subclasses of `ProvisionError`, `RunError` is raised when the
        # reboot command fails. A timeout of the wait for the guest to come
        # back is reported via the return value.
        except (tmt.utils.ProvisionError, tmt.utils.RunError) as error:
            raise tmt.utils.PrepareError(
                f"Failed to reboot guest '{guest.multihost_name}' after package installation."
            ) from error

        if not rebooted:
            raise tmt.utils.PrepareError(
                f"Failed to reboot guest '{guest.multihost_name}' after package installation."
            )

        guest.facts.sync(guest, 'kernel_release')
        if guest.facts.kernel_release:
            self.verbose('kernel', guest.facts.kernel_release, color='green')

    def go(
        self,
        *,
        guest: 'Guest',
        environment: Optional[Environment] = None,
        logger: tmt.log.Logger,
    ) -> tmt.steps.PluginOutcome:
        """
        Perform preparation for the guests
        """

        outcome = super().go(guest=guest, environment=environment, logger=logger)

        # Nothing to do in dry mode
        if self.is_dry_run:
            return outcome

        if guest.facts.package_manager is None:
            raise tmt.utils.PrepareError('Unrecognized package manager.')

        if self.data.reboot:
            self._validate_reboot(guest)

        options = Options(
            excluded_packages=[Package(p) for p in self.data.exclude],
            skip_missing=self.data.missing == 'skip',
            check_first=self.data.check_first,
        )

        self._prepare_installables(self.data.package, self.data.directory, logger)

        # Enable copr repositories...
        guest.package_manager.enable_copr(*self.data.copr)

        if not self.data.package and not self.data.directory:
            self.debug("No packages for installation found.", level=3)
            return outcome

        # Packages missing before the first installation attempt. Collected
        # once, so that packages installed by a failed first attempt are
        # still recognized as installed after the retry below.
        missing_installables = self._find_missing_installables(guest) if self.data.reboot else []

        # ... and install packages.
        try:
            self._install(guest, options)
        except Exception as exc1:
            # We do not have any special handling for exceptions raised by the following code.
            # Wrapping them with try/except gives us a chance to attach the original exception
            # to whatever the code may raise, and therefore preserve the information attached
            # to the original exception.
            self.warn('Installation failed, trying again after metadata refresh.')

            try:
                # Refresh cache in case of recent but not updated change to repodata
                guest.package_manager.refresh_metadata()
                self._install(guest, options)
            except Exception as exc2:
                if isinstance(exc2, tmt.utils.RunError):
                    failed_packages = self._extract_failed_packages_from_outputs(
                        [exc2.output], guest
                    )
                    if failed_packages:
                        self._show_failed_packages_with_tests(failed_packages)
                raise exc2 from exc1

        if self.data.reboot:
            self._reboot(
                guest,
                installed=self._were_packages_installed(guest, missing_installables),
            )

        return outcome
