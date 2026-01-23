"""
Artifact provider for creating DNF repositories from baseurl.
"""

from collections.abc import Sequence
from re import Pattern
from typing import Optional

import tmt.log
import tmt.utils
from tmt.steps.prepare.artifact import RpmArtifactInfo
from tmt.steps.prepare.artifact.providers import (
    ArtifactProvider,
    ArtifactProviderId,
    Repository,
    provides_artifact_provider,
)
from tmt.steps.prepare.artifact.providers.repository import _REPO_NAME_GENERATOR
from tmt.steps.provision import Guest


# ignore[type-arg]: TypeVar in provider registry annotations is
# puzzling for type checkers. And not a good idea in general, probably.
@provides_artifact_provider('repository-url')  # type: ignore[arg-type]
class RepositoryUrlProvider(ArtifactProvider[RpmArtifactInfo]):
    """
    Provider for making RPM artifacts from a repository discoverable without downloading them.

    The provider identifier should start with 'repository-url:' followed by a baseurl
    to a DNF repository, e.g., "repository-url:https://example.com/repo/".

    The provider generates a .repo file with the given baseurl, which will be installed to the
    guest's ``/etc/yum.repos.d/`` directory, and lists RPMs available in the repository
    without downloading them, acting as a discovery-only provider. Artifacts are all available
    RPM packages listed in the repository.

    :param raw_provider_id: The full provider identifier, starting with 'repository-url:'.
    :param logger: Logger instance for outputting messages.
    :raises ValueError: If the provider identifier format is invalid or the baseurl is missing.
    """

    # FIXME: This docstring will need refactoring when the documentation of PrepareArtifact
    #        is made dynamic.

    repository: Repository

    def __init__(self, raw_provider_id: str, repository_priority: int, logger: tmt.log.Logger):
        super().__init__(raw_provider_id, repository_priority, logger)

    @classmethod
    def _extract_provider_id(cls, raw_provider_id: str) -> ArtifactProviderId:
        prefix = 'repository-url:'
        if not raw_provider_id.startswith(prefix):
            raise ValueError(f"Invalid repository-url provider format: '{raw_provider_id}'.")
        value = raw_provider_id[len(prefix) :]
        if not value:
            raise ValueError("Missing repository baseurl.")
        return value

    @property
    def artifacts(self) -> Sequence[RpmArtifactInfo]:
        # Repository provider does not enumerate individual artifacts.
        # The repository is installed and packages are available through the package manager.
        # There is no need to download individual artifact files.
        return []

    def _download_artifact(
        self, artifact: RpmArtifactInfo, guest: Guest, destination: tmt.utils.Path
    ) -> None:
        """This provider only discovers repos; it does not download individual RPMs."""
        # FIXME: Change this to UnsupportedOperationError once its available
        raise AssertionError("RepositoryUrlProvider does not support downloading individual RPMs.")

    def fetch_contents(
        self,
        guest: Guest,
        download_path: tmt.utils.Path,
        exclude_patterns: Optional[list[Pattern[str]]] = None,
    ) -> list[tmt.utils.Path]:
        # Fetches and initializes the repository from the baseurl.
        # Repository provider does not download individual artifacts. Instead, it creates
        # a .repo file which will be installed via get_repositories(). Packages are
        # then available through the package manager.
        # It returns an empty list, as no individual artifact files are downloaded.

        baseurl = self.id
        repo_name = f"tmt-repo-{_REPO_NAME_GENERATOR.get()}"

        self.logger.info(f"Setting up repository from baseurl: {baseurl} (name: {repo_name})")

        # Generate .repo file content
        repo_content = f"""[{tmt.utils.sanitize_name(repo_name)}]
name={repo_name}
baseurl={baseurl}
enabled=1
gpgcheck=0
priority={self.repository_priority}"""

        self.logger.debug(f"Generated .repo file content:\n{repo_content}")

        # Create Repository object
        self.repository = Repository.from_content(
            content=repo_content, name=repo_name, logger=self.logger
        )

        self.logger.info(f"Repository initialized: {self.repository.name} (baseurl: {baseurl})")
        return []

    def get_repositories(self) -> list[Repository]:
        self.logger.info(f"Providing repository '{self.repository.name}' for installation")
        return [self.repository]
