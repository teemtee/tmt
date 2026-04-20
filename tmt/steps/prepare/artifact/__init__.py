from typing import ClassVar, Optional

import fmf.utils

import tmt.base.core
import tmt.steps
import tmt.utils
from tmt.container import container, field
from tmt.guest import Guest
from tmt.log import Logger
from tmt.steps import PluginOutcome
from tmt.steps.prepare import PreparePlugin, PrepareStepData
from tmt.steps.prepare.artifact.providers import (
    _PROVIDER_REGISTRY,
    SHARED_REPO_NAME,
    ArtifactProvider,
    Repository,
)

# ``@provides_method`` causes pyright to lose the class type, which is the
# root cause of all ``pyright: ignore`` waivers referencing these two classes.
# This will be fixed by https://github.com/teemtee/tmt/issues/4766.
from tmt.steps.prepare.install import PrepareInstall  # pyright: ignore[reportUnknownVariableType]
from tmt.steps.prepare.verify_installation import (
    PrepareVerifyInstallation,  # pyright: ignore[reportUnknownVariableType]
    PrepareVerifyInstallationData,
)
from tmt.utils import Environment, Path


@container
class PrepareArtifactData(PrepareStepData):
    provide: list[str] = field(
        default_factory=list,
        option='--provide',
        metavar='ID',
        help='Artifact ID to provide. Format <type>:<id>.',
        multiple=True,
        normalize=tmt.utils.normalize_string_list,
    )

    default_repository_priority: int = field(
        default=50,
        option='--default-repository-priority',
        metavar='PRIORITY',
        help="""
            Default priority for created artifact repositories. Lower values mean
            higher priority in package managers.
            """,
    )

    verify: bool = field(
        default=True,
        option='--verify/--no-verify',
        is_flag=True,
        help="""
        Verify that packages from tmt-injected ``prepare/install`` phases
        (test ``require``/``recommend`` keys, their dist-git equivalents, and essential requires)
        were installed from the correct provider artifact repository.
        User-defined ``prepare/install`` phases are not covered.
        """,
    )


def get_artifact_provider(provider_id: str) -> type[ArtifactProvider]:
    provider_type = provider_id.split(':', maxsplit=1)[0]
    provider_class = _PROVIDER_REGISTRY.get_plugin(provider_type)
    if not provider_class:
        raise tmt.utils.PrepareError(f"Unknown provider type '{provider_type}'")
    return provider_class


@tmt.steps.provides_method('artifact')
class PrepareArtifact(PreparePlugin[PrepareArtifactData]):
    """
    Prepare artifacts on the guest.

    .. note::

       This is a tech preview feature.

    This plugin makes a given artifact available on the guest.
    This can consist of downloading the artifacts and creating
    a preferred repository on the guest.

    The goal is to make sure these exact artifacts are being used
    when requested via
    :tmt:story:`test require </spec/tests/require>` or
    :tmt:story:`test recommend </spec/tests/recommend>` keys. Exact NVR
    *should not* be used in those requests, instead this plugin
    will take care of disambiguating the requested package based
    on the provided artifacts.

    When ``verify`` is enabled (the default), the plugin injects a
    verification phase that checks packages installed from tmt-managed
    install phases (``require``, ``recommend``, ``essential-requires``,
    and their dist-git equivalents) actually came from the configured
    artifact repositories. User-defined ``prepare/install`` phases are
    not covered by this verification.

    Currently, the following artifact providers are supported:

    **Koji**

    Builds from the `Fedora Koji <https://koji.fedoraproject.org>`__ build system.

    * ``koji.build:<build-id>`` - Koji build by build ID
    * ``koji.task:<task-id>`` - Koji task (including scratch builds)
    * ``koji.nvr:<nvr>`` - Koji build by NVR (name-version-release)

    Example usage:

    .. code-block:: yaml

        prepare:
            how: artifact
            provide:
              - koji.build:123456
              - koji.task:654321
              - koji.nvr:openssl-3.2.6-2.fc42

    **Brew** (Red Hat internal)

    Builds from the Red Hat Brew build system.

    * ``brew.build:<build-id>`` - Brew build by build ID
    * ``brew.task:<task-id>`` - Brew task (including scratch builds)
    * ``brew.nvr:<nvr>`` - Brew build by NVR

    Example usage:

    .. code-block:: yaml

        prepare:
            how: artifact
            provide:
              - brew.build:123456
              - brew.task:654321
              - brew.nvr:openssl-3.2.6-2.el10

    **Copr**

    Builds from the `Fedora Copr <https://copr.fedorainfracloud.org>`__
    build system.

    * ``copr.build:<build-id>:<chroot>`` - Copr build by ID and chroot

    Example usage:

    .. code-block:: yaml

        prepare:
            how: artifact
            provide:
              - copr.build:1784470:fedora-43-x86_64

    **File**

    RPMs from local files or remote URLs.

    * ``file:<path>`` - Local RPM file(s) specified via path or a glob pattern
    * ``file:<directory>`` - All RPMs from a local directory
    * ``file:<url>`` - Remote RPM file URL (http/https)

    Example usage:

    .. code-block:: yaml

        prepare:
            how: artifact
            provide:
              - file:/tmp/my-package.rpm
              - file:/tmp/rpms/*.rpm
              - file:/tmp/rpms
              - file:https://example.com/my-package.rpm

    **Repository**

    Remote dnf repositories.

    * ``repository-file:<url>`` - URL to a ``.repo`` file

    .. note::

        The ``repository-file`` provider only adds the dnf repository to the
        guest system, and does not download the RPMs from the repository.

    Example usage:

    .. code-block:: yaml

        prepare:
            how: artifact
            provide:
              - repository-file:https://example.com/my-repo.repo
    """

    _data_class = PrepareArtifactData

    # Shared repository configuration
    SHARED_REPO_DIR_NAME: ClassVar[str] = 'artifact-shared-repo'
    ARTIFACTS_METADATA_FILENAME: ClassVar[str] = 'artifacts.yaml'

    #: Name of the auto-injected verify-installation phase.
    VERIFY_PHASE_NAME: ClassVar[str] = 'verify-artifact-packages'

    #: Summary of the auto-injected verify-installation phase.
    VERIFY_PHASE_SUMMARY: ClassVar[str] = (
        'Verify test requirement packages were installed from the correct artifact repositories'
    )

    def go(
        self,
        *,
        guest: Guest,
        environment: Optional[Environment] = None,
        logger: Logger,
    ) -> PluginOutcome:
        from tmt.steps.prepare.artifact.providers.repository import create_repository

        outcome = super().go(guest=guest, environment=environment, logger=logger)

        # Prepare a shared directory on the guest for aggregating artifacts.
        shared_repo_dir: Path = self.plan_workdir / self.SHARED_REPO_DIR_NAME

        # Ensure the shared repository directory exists on the guest.
        shared_repository = create_repository(
            artifact_dir=shared_repo_dir,
            guest=guest,
            logger=logger,
            repo_name=SHARED_REPO_NAME,
            priority=self.data.default_repository_priority,
        )

        # Initialize all providers and have them contribute to the shared repo
        providers: list[ArtifactProvider] = []
        seen_nvras: dict[str, str] = {}

        # --- Pass 1: Initialize all providers and validate for duplicate NVRAs ---
        for raw_id in self.data.provide:
            try:
                provider_class = get_artifact_provider(raw_id)

                provider_logger = self._logger.descend(raw_id)
                provider = provider_class(
                    raw_id,
                    repository_priority=self.data.default_repository_priority,
                    logger=provider_logger,
                )

                self._detect_duplicate_nvras(provider, seen_nvras)

                providers.append(provider)

            except tmt.utils.PrepareError:
                raise

            except Exception as error:
                raise tmt.utils.PrepareError(
                    f"Failed to initialize artifact provider '{raw_id}'."
                ) from error

        # --- Pass 2: Download and contribute (only reached if no duplicates) ---
        for provider in providers:
            try:
                # Define a unique download path for this provider's artifacts
                download_path = self.plan_workdir / "artifacts" / provider.sanitized_id

                # First, fetch the contents (download artifacts)
                provider.fetch_contents(guest, download_path)

                # Then, have the provider contribute to the shared repository
                provider.contribute_to_shared_repo(
                    guest=guest,
                    source_path=download_path,
                    shared_repo_dir=shared_repo_dir,
                )

            except tmt.utils.PrepareError:
                raise

            except Exception as error:
                raise tmt.utils.PrepareError(
                    f"Failed to use artifact provider '{provider.raw_id}'."
                ) from error

        # Create or update the shared repository.
        # This aggregates all local artifacts from file-based providers.
        # If this prepare step runs multiple times in the same plan, artifacts
        # accumulate in the same directory and createrepo updates the metadata.

        guest.package_manager.create_repository(shared_repo_dir)

        # Collect all repositories (shared repository + provider repositories)
        repositories: list[Repository] = [shared_repository]
        for provider in providers:
            repositories.extend(provider.get_repositories())

        # Install all repositories centrally
        # This ensures consistent handling across all providers
        for repo in repositories:
            guest.package_manager.install_repository(repo)
            logger.debug(f"Installed repository '{repo.name}'.")

        # Enumerate artifacts from installed repositories.
        for provider in providers:
            provider.enumerate_artifacts(guest)

        # Persist artifact metadata to YAML
        self._save_artifacts_metadata(providers)

        # Verify phase injection
        if self.data.verify:
            self._inject_verify_phase(providers, guest)

        # Report configuration summary
        logger.info(
            f"Configured artifact preparation with {len(self.data.provide)} provider(s) "
            f"and {len(repositories)} repository(ies)."
        )

        return outcome

    def _inject_verify_phase(self, providers: list[ArtifactProvider], guest: Guest) -> None:
        """
        Inject a verify-installation phase for packages from these providers.

        If a verify phase already exists for the same where= group, merge
        the packages into it. Otherwise, create and add a new phase.
        """
        # Collect packages from the install phases injected by tmt on behalf of
        # test/essential requirements. User-defined prepare/install phases are
        # intentionally excluded.
        #
        # Phase name sources:
        #   'essential-requires'    — Prepare._go() in tmt/steps/prepare/__init__.py
        #   'requires'              — Prepare._go() in tmt/steps/prepare/__init__.py
        #   'recommends'            — Prepare._go() in tmt/steps/prepare/__init__.py
        #   'requires (dist-git)'   — tmt/steps/prepare/distgit.py
        #   'recommends (dist-git)' — tmt/steps/prepare/distgit.py
        _tmt_install_phase_names = {
            'essential-requires',
            'requires',
            'recommends',
            'requires (dist-git)',
            'recommends (dist-git)',
        }
        pkg_names: set[str] = set()
        _install_phases = self.step.phases(classes=PrepareInstall)  # pyright: ignore[reportUnknownVariableType,reportUnknownArgumentType]
        for install_phase in _install_phases:  # pyright: ignore[reportUnknownVariableType]
            if install_phase.data.name not in _tmt_install_phase_names:  # pyright: ignore[reportUnknownMemberType]
                continue
            if not install_phase.enabled_on_guest(guest):  # pyright: ignore[reportUnknownMemberType]
                continue
            for pkg in install_phase.data.package:  # pyright: ignore[reportUnknownMemberType,reportUnknownVariableType]
                pkg_names.add(str(pkg))  # pyright: ignore[reportUnknownArgumentType]

        # Build package → set of valid repo_ids, filtering to only required packages.
        # TODO: Path-based or virtual-provide requirements (e.g. /usr/bin/createrepo,
        # /usr/bin/make) in pkg_names will NOT match artifact.version.name (e.g. 'createrepo',
        # 'make') because rpm --whatprovides cannot be used at this point — requirements are
        # not yet installed when _inject_verify_phase runs (only artifact repos are set up).
        # Consequently such artifacts are silently skipped from verification even when the
        # providing package IS one of the provided artifacts.
        #
        # The verify plugin's Pass 1 (resolve_capabilities) handles path → name resolution
        # correctly after installation, but only for entries that made it into pkgs_to_verify.
        pkgs_to_verify: dict[str, set[str]] = {}
        for provider in providers:
            for artifact in provider.artifacts:
                if artifact.version.name in pkg_names:
                    pkgs_to_verify.setdefault(artifact.version.name, set()).add(artifact.repo_id)

        if not pkgs_to_verify:
            self.verbose('No packages to be installed were found in the provided artifacts.')
            return

        self.debug(f"Verifying {fmf.utils.listed(sorted(pkgs_to_verify), 'package')}.")

        # Look for an existing verify phase for this where= group.
        existing_verify: Optional[PrepareVerifyInstallation] = next(  # pyright: ignore[reportUnknownVariableType]
            (
                phase
                for phase in self.step.phases(PrepareVerifyInstallation)  # pyright: ignore[reportUnknownArgumentType,reportUnknownVariableType]
                if phase.data.name == self.VERIFY_PHASE_NAME  # pyright: ignore[reportUnknownMemberType]
                and set(phase.data.where) == set(self.data.where)  # pyright: ignore[reportUnknownArgumentType,reportUnknownMemberType]
            ),
            None,
        )

        if existing_verify is not None:
            # Merge into existing verify phase, extending repo lists rather than replacing them.
            for verify_pkg, verify_repos in pkgs_to_verify.items():
                existing = existing_verify.data.verify.setdefault(verify_pkg, [])  # pyright: ignore[reportUnknownMemberType,reportUnknownVariableType]
                existing.extend(repo_id for repo_id in verify_repos if repo_id not in existing)  # pyright: ignore[reportUnknownMemberType]
        else:
            # Create and add a new verify phase.
            verify_data = PrepareVerifyInstallationData(
                name=self.VERIFY_PHASE_NAME,
                how='verify-installation',
                summary=self.VERIFY_PHASE_SUMMARY,
                order=tmt.steps.PHASE_ORDER_PREPARE_VERIFY_INSTALLATION,
                where=list(self.data.where),
                verify={pkg: sorted(repo_ids) for pkg, repo_ids in pkgs_to_verify.items()},
            )
            verify_phase = PreparePlugin.delegate(self.step, data=verify_data)  # pyright: ignore[reportUnknownVariableType]
            self.step.add_phase(verify_phase)  # pyright: ignore[reportUnknownArgumentType]

    def essential_requires(self) -> list[tmt.base.core.Dependency]:
        # createrepo is needed to create repository metadata from downloaded artifacts
        return [
            tmt.base.core.DependencySimple('/usr/bin/createrepo'),
        ]

    def _detect_duplicate_nvras(
        self, provider: ArtifactProvider, seen_nvras: dict[str, str]
    ) -> None:
        """
        Check for duplicate NVRAs across providers.
        """
        raw_id = provider.raw_id

        for artifact_info in provider.artifact_metadata:
            if (nvra := artifact_info["nvra"]) in seen_nvras:
                raise tmt.utils.PrepareError(
                    f"Artifact '{nvra}' provided by both '{seen_nvras[nvra]}' and '{raw_id}'."
                )

            seen_nvras[nvra] = raw_id

    def _save_artifacts_metadata(self, providers: list[ArtifactProvider]) -> None:
        """
        Persist the metadata of artifacts to a YAML file.

        Groups artifacts by provider.
        """

        metadata = {
            'providers': [
                {
                    'id': provider.raw_id,
                    'artifacts': provider.artifact_metadata,
                }
                for provider in providers
            ]
        }

        metadata_file = self.plan_workdir / self.ARTIFACTS_METADATA_FILENAME

        try:
            metadata_file.write_text(tmt.utils.to_yaml(metadata, start=True))
        except OSError as error:
            raise tmt.utils.FileError(f"Failed to write into '{metadata_file}' file.") from error
