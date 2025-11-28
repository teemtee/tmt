from typing import Optional

import tmt.base
import tmt.steps
import tmt.steps.prepare.artifact.providers
import tmt.utils
from tmt.container import container, field
from tmt.log import Logger
from tmt.steps import PluginOutcome
from tmt.steps.prepare import PreparePlugin, PrepareStepData
from tmt.steps.prepare.artifact.providers import (
    _PROVIDER_REGISTRY,
    ArtifactInfo,
    ArtifactProvider,
)
from tmt.steps.prepare.artifact.providers.repository import create_repository
from tmt.steps.provision import Guest
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

        # Validate plan workdir exists
        if not self.plan_workdir:
            raise tmt.utils.PrepareError("Plan workdir is not available for artifact preparation.")

        # 1. Prepare a shared directory on the guest for aggregating artifacts.
        # This directory will be created by create_repository.
        shared_repo_dir = self.plan_workdir / 'artifact-shared-repo'

        # 2. Initialize all providers and have them contribute to the shared repo
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
                # to avoid conflicts during the download phase.
                download_path = self.plan_workdir / "artifacts" / provider_id_sanitized

                # Have the provider contribute to the shared repository.
                # File-based providers will download to download_path and copy to shared_repo_dir.
                # Repository-url providers will prepare their repository objects.
                provider.contribute_to_shared_repo(
                    guest=guest,
                    download_path=download_path,
                    shared_repo_dir=shared_repo_dir,
                )

            except tmt.utils.PrepareError:
                # Re-raise PrepareError as-is (already properly formatted)
                raise

            except Exception as error:
                raise tmt.utils.PrepareError(
                    f"Failed to initialize or use artifact provider '{raw_provider_id}'."
                ) from error

        # 3. Create or update the shared repository.
        # This aggregates all local artifacts from file-based providers.
        # If this prepare step runs multiple times in the same plan, artifacts
        # accumulate in the same directory and createrepo updates the metadata.
        # create_repository will create the directory, run createrepo, and generate .repo content
        shared_repository = create_repository(
            artifact_dir=shared_repo_dir,
            guest=guest,
            logger=logger,
            repo_name="tmt-artifact-shared",
        )

        # 4. Collect all repositories from providers
        provider_repositories: list[tmt.steps.prepare.artifact.providers.Repository] = []
        for provider in providers:
            provider_repositories.extend(provider.get_repositories())

        # 5. Install all repositories (shared + provider repositories)
        # Check if shared repository is already installed to avoid reinstalling
        shared_repo_file = Path("/etc/yum.repos.d") / shared_repository.filename
        shared_repo_exists = False
        try:
            guest.execute(
                tmt.utils.ShellScript(f"test -f {shared_repo_file}"),
                silent=True,
            )
            shared_repo_exists = True
        except tmt.utils.RunError:
            # File doesn't exist, proceed with installation
            shared_repo_exists = False
        except Exception as error:
            # If check fails for other reasons, assume it doesn't exist and proceed
            logger.debug(f"Could not check if shared repository exists: {error}")

        all_repositories = [shared_repository, *provider_repositories]
        for repository in all_repositories:
            # Skip reinstalling the shared repository if it already exists
            # (allows multiple prepare artifact steps to accumulate artifacts)
            if repository.name == "tmt-artifact-shared" and shared_repo_exists:
                logger.debug(
                    f"Repository '{repository.name}' already installed, "
                    "metadata updated with new artifacts."
                )
                continue

            guest.package_manager.install_repository(repository)
            logger.debug(f"Installed repository '{repository.name}'.")

        logger.info(
            f"Configured artifact preparation with {len(self.data.provide)} provider(s) "
            f"and {len(all_repositories)} repository(ies)."
        )

        return outcome

    def essential_requires(self) -> list[tmt.base.Dependency]:
        # createrepo is needed to create repository metadata from downloaded artifacts
        return [
            tmt.base.DependencySimple('/usr/bin/createrepo'),
        ]
