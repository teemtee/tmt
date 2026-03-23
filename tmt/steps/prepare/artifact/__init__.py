from typing import TYPE_CHECKING, Any, ClassVar, Final, Optional

import fmf.utils

import tmt.base.core
import tmt.steps
import tmt.utils
from tmt.base.core import DependencySimple
from tmt.container import container, field
from tmt.guest import Guest
from tmt.log import Logger
from tmt.steps import PluginOutcome
from tmt.steps.prepare import PreparePlugin, PrepareStepData
from tmt.steps.prepare.artifact.providers import (
    _PROVIDER_REGISTRY,
    ArtifactProvider,
    Repository,
)
from tmt.utils import Environment, Path

if TYPE_CHECKING:
    import tmt.steps.prepare.verify_installation

#: Name of the shared repository created by the artifact plugin.
ARTIFACT_SHARED_REPO_NAME: Final[str] = 'tmt-artifact-shared'

#: Filename of the artifact metadata file written by the artifact plugin.
ARTIFACT_METADATA_FILENAME: Final[str] = 'artifacts.yaml'

#: Name of the auto-injected verify-installation phase.
VERIFY_PHASE_NAME: Final[str] = 'verify-artifact-packages'

#: Summary of the auto-injected verify-installation phase.
VERIFY_PHASE_SUMMARY: Final[str] = 'Verify packages were installed from artifact repositories'


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

    auto_verify: bool = field(
        default=True,
        option='--auto-verify/--no-auto-verify',
        is_flag=True,
        help="""
            Automatically verify that packages from require/recommend that are
            present in the artifact metadata were installed from the artifact
            repository. Enabled by default.
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
    when requested in one of the
    :tmt:story:`test require </spec/tests/require>`,
    :tmt:story:`test recommend </spec/tests/recommend>`, or
    :ref:`prepare install </plugins/prepare/install>`. Exact NVR
    *should not* be used in those requests, instead this plugin
    will take care of disambiguating the requested package based
    on the provided artifacts.

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
    SHARED_REPO_NAME: ClassVar[str] = ARTIFACT_SHARED_REPO_NAME
    ARTIFACTS_METADATA_FILENAME: ClassVar[str] = ARTIFACT_METADATA_FILENAME

    #: Pre-registered verify-installation phase, set by
    #: :py:func:`tmt.steps.prepare.Prepare._inject_artifact_verify_phase` before the
    #: queue is built.  Populated with the package→repo mapping during :py:meth:`go`.
    _future_verify: Optional['tmt.steps.prepare.verify_installation.PrepareVerifyInstallation']

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._future_verify = None

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
            repo_name=self.SHARED_REPO_NAME,
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

        # Persist artifact metadata to YAML
        self._save_artifacts_metadata(providers)

        # Report configuration summary
        logger.info(
            f"Configured artifact preparation with {len(self.data.provide)} provider(s) "
            f"and {len(repositories)} repository(ies)."
        )

        self._populate_verify_from_providers(providers, guest)

        return outcome

    def _populate_verify_from_providers(
        self, providers: list[ArtifactProvider], guest: Guest
    ) -> None:
        """
        Populate the pre-registered verify phase with the package→repo mapping.

        Computes the intersection of artifact package names and package names
        collected from test require/recommend (filtered to those enabled on *guest*)
        and explicit prepare install phases, then updates :py:attr:`_future_verify`
        with ``{package: ARTIFACT_SHARED_REPO_NAME}`` entries for each package in
        the intersection.

        Called from :py:meth:`go` after providers have been initialized and artifacts
        are known.  Each artifact phase contributes only its own providers' packages.
        Different artifact phases run sequentially in the queue so no cross-phase race
        is possible.
        """
        if self._future_verify is None:
            return

        from typing import cast

        # @provides_method erases PrepareInstall's type to PluginClass; the pyright
        # suppression covers the resulting reportUnknownVariableType on the import and
        # reportUnknownArgumentType on its use as a classes= argument.  The cast is
        # needed by Pyright but redundant for mypy (hence type: ignore[redundant-cast]).
        from tmt.steps.prepare.install import (
            PrepareInstall,  # pyright: ignore[reportUnknownVariableType]
        )

        pkg_names: set[str] = set()

        # Collect simple package names from test require/recommend, restricted to
        # tests that are actually enabled on this guest to avoid cross-guest pollution.
        for test_origin in self.step.plan.discover.tests(enabled=True):
            test = test_origin.test
            if not test.enabled_on_guest(guest):
                continue
            for dep in (*test.require, *test.recommend):
                if isinstance(dep, DependencySimple):
                    pkg_names.add(str(dep))

        # Collect packages explicitly listed in prepare install phases.
        _install_phases = cast(  # type: ignore[redundant-cast]
            list[Any],
            self.step.phases(
                classes=PrepareInstall,  # pyright: ignore[reportUnknownArgumentType]
            ),
        )
        for install_phase in _install_phases:
            for pkg in install_phase.data.package:
                pkg_names.add(str(pkg))

        # Artifact package names from providers in THIS phase only
        artifact_pkg_names: set[str] = {
            artifact.version.name for provider in providers for artifact in provider.artifacts
        }

        intersection = artifact_pkg_names & pkg_names
        if not intersection:
            self.debug('No overlap between artifact packages and test requirements.')
            return

        self.debug(
            f"Auto-verifying {fmf.utils.listed(sorted(intersection), 'package')} "
            f"against '{ARTIFACT_SHARED_REPO_NAME}'."
        )

        uncovered = pkg_names - artifact_pkg_names
        if uncovered:
            self.debug(
                f"{fmf.utils.listed(sorted(uncovered), 'package')} "
                f"from require/recommend/install not provided by this artifact phase."
            )

        self._future_verify.data.verify.update(
            dict.fromkeys(intersection, ARTIFACT_SHARED_REPO_NAME)
        )

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
                    'auto_verify': self.data.auto_verify,
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
