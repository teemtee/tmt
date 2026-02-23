from typing import ClassVar, Optional

import tmt.base
import tmt.steps
import tmt.utils
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
    SHARED_REPO_NAME: ClassVar[str] = 'tmt-artifact-shared'
    ARTIFACTS_METADATA_FILENAME: ClassVar[str] = 'artifacts.yaml'

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
        for raw_provider_id in self.data.provide:
            try:
                provider_class = get_artifact_provider(raw_provider_id)

                # Sanitize the provider ID to use as a directory name
                provider_id_sanitized = tmt.utils.sanitize_name(raw_provider_id, allow_slash=False)
                provider_logger = self._logger.descend(raw_provider_id)
                provider = provider_class(
                    raw_provider_id,
                    repository_priority=self.data.default_repository_priority,
                    logger=provider_logger,
                )
                providers.append(provider)

                # Define a unique download path for this provider's artifacts
                download_path = self.plan_workdir / "artifacts" / provider_id_sanitized

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
                    f"Failed to initialize or use artifact provider '{raw_provider_id}'."
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

        return outcome

    def essential_requires(self) -> list[tmt.base.Dependency]:
        # createrepo is needed to create repository metadata from downloaded artifacts
        return [
            tmt.base.DependencySimple('/usr/bin/createrepo'),
        ]

    def _save_artifacts_metadata(self, providers: list[ArtifactProvider]) -> None:
        """
        Persist the metadata of artifacts to a YAML file.

        Groups artifacts by provider.
        """
        providers_data = [
            {
                'id': provider.raw_provider_id,
                'artifacts': provider.get_artifact_metadata(),
            }
            for provider in providers
        ]

        metadata_file = self.plan_workdir / self.ARTIFACTS_METADATA_FILENAME

        try:
            metadata_file.write_text(tmt.utils.to_yaml({'providers': providers_data}, start=True))
        except OSError as error:
            raise tmt.utils.FileError(f"Failed to write into '{metadata_file}' file.") from error
