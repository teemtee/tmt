from typing import Optional

import tmt.base
import tmt.steps
import tmt.utils
from tmt.container import container, field
from tmt.log import Logger
from tmt.steps import PluginOutcome
from tmt.steps.prepare import PreparePlugin, PrepareStepData
from tmt.steps.prepare.artifact.providers import (
    _PROVIDER_REGISTRY,
    ArtifactInfo,
    ArtifactProvider,
    Repository,
)
from tmt.steps.prepare.artifact.providers.repository import create_repository
from tmt.steps.provision import Guest
from tmt.utils import Environment


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


@container
class RpmArtifactInfo(ArtifactInfo):
    """
    Represents a single RPM package.
    """

    _raw_artifact: dict[str, str]

    @property
    def id(self) -> str:
        """RPM identifier"""
        return f"{self._raw_artifact['nvr']}.{self._raw_artifact['arch']}.rpm"

    @property
    def location(self) -> str:
        return self._raw_artifact['url']


def get_artifact_provider(provider_id: str) -> type[ArtifactProvider[ArtifactInfo]]:
    provider_type = provider_id.split(':')[0]
    provider_class = _PROVIDER_REGISTRY.get_plugin(provider_type)
    if not provider_class:
        raise tmt.utils.PrepareError(f"Unknown provider type '{provider_type}'")
    return provider_class


@tmt.steps.provides_method('artifact')
class PrepareArtifact(PreparePlugin[PrepareArtifactData]):
    """
    Prepare artifacts on the guest.

    .. note::

       This is a draft plugin to be implemented
    """

    _data_class = PrepareArtifactData

    def go(
        self,
        *,
        guest: Guest,
        environment: Optional[Environment] = None,
        logger: Logger,
    ) -> PluginOutcome:
        outcome = super().go(guest=guest, environment=environment, logger=logger)

        # Prepare a shared directory on the guest for aggregating artifacts.
        shared_repo_dir = self.plan_workdir / 'artifact-shared-repo'

        # Ensure the shared repository directory exists on the guest.
        shared_repository = create_repository(
            artifact_dir=shared_repo_dir,
            guest=guest,
            logger=logger,
            repo_name="tmt-artifact-shared",
        )

        # Initialize all providers and have them contribute to the shared repo
        providers: list[ArtifactProvider[ArtifactInfo]] = []
        for raw_provider_id in self.data.provide:
            try:
                provider_class = get_artifact_provider(raw_provider_id)

                # Sanitize the provider ID to use as a directory name
                provider_id_sanitized = tmt.utils.sanitize_name(raw_provider_id, allow_slash=False)
                provider_logger = self._logger.descend(raw_provider_id)
                provider = provider_class(raw_provider_id, logger=provider_logger)
                providers.append(provider)

                # Define a unique download path for this provider's artifacts
                download_path = self.plan_workdir / "artifacts" / provider_id_sanitized

                # For providers that manage repositories, skip download/contribution here.
                # They will discover packages after repository installation.
                if not provider.get_repositories():
                    # First, fetch the contents (download artifacts)
                    provider.fetch_contents(guest, download_path)

                    # Then, have the provider contribute to the shared repository
                    provider.contribute_to_shared_repo(
                        guest=guest,
                        download_path=download_path,
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

        # Now that repositories are installed, discover packages from repository providers
        for provider in providers:
            # Only call fetch_contents for repository-based providers that need package discovery
            if provider.get_repositories():
                provider.fetch_contents(guest, tmt.utils.Path(''))

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
