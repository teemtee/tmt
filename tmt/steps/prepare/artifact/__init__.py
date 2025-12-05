from shlex import quote
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
)
from tmt.steps.prepare.artifact.providers.repository import create_repository
from tmt.steps.provision import Guest
from tmt.utils import Environment, ShellScript


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

        # 1. Prepare a shared directory on the guest for aggregating artifacts.
        # We will move all downloaded files here to create a single repository.
        shared_repo_dir = self.plan_workdir / 'artifact-shared-repo'

        # Create the shared repository directory
        guest.execute(ShellScript(f"mkdir -p {quote(str(shared_repo_dir))}"))

        has_local_artifacts = False

        # 2. Iterate over all requested providers
        for raw_provider_id in self.data.provide:
            provider_class = get_artifact_provider(raw_provider_id)

            # Sanitize the provider ID to use as a directory name
            provider_id_sanitized = tmt.utils.sanitize_name(raw_provider_id, allow_slash=False)
            provider_logger = self._logger.descend(raw_provider_id)
            provider = provider_class(raw_provider_id, logger=provider_logger)

            # Define a unique download path for this provider's artifacts
            # to avoid conflicts during the download phase.
            download_path = self.plan_workdir / "artifacts" / provider_id_sanitized

            # Fetch the contents.
            # - Providers like 'file', 'koji', 'brew' return a list of paths to downloaded files.
            # - Providers like 'repository-url' return an empty list because they install
            #   the repo file directly as a side effect.
            downloaded_paths = provider.fetch_contents(guest, download_path)

            # We assume all files in the download directory are valid (no corrupt files).
            # We proceed only if 'downloaded_paths' is not empty (handles 'repository-url' case).
            if downloaded_paths:
                has_local_artifacts = True

                # Copy all contents from the provider's download directory to the shared repo.
                guest.execute(
                    ShellScript(
                        f"cp -r {quote(str(download_path))}/. {quote(str(shared_repo_dir))}"
                    )
                )

        # 4. If we collected any local artifacts, create the repository metadata
        # and configure the guest to use this new local repository.
        if has_local_artifacts:
            # create_repository runs 'createrepo' on the guest and generates the .repo content
            repository = create_repository(
                artifact_dir=shared_repo_dir,
                guest=guest,
                logger=logger,
                repo_name="tmt-artifact-shared",
            )

            # Install the .repo file
            guest.package_manager.install_repository(repository)

            logger.info(
                f"Created and installed local repository with {len(self.data.provide)} sources."
            )

        return outcome

    def essential_requires(self) -> list[tmt.base.Dependency]:
        # createrepo is needed to create repository metadata from downloaded artifacts
        return [
            tmt.base.DependencySimple('/usr/bin/createrepo'),
        ]
