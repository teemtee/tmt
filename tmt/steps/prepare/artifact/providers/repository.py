"""
Artifact provider for discovering RPMs from repository files.
"""

import re
from collections.abc import Sequence
from re import Pattern
from typing import Optional

import tmt.log
from tmt.steps import DefaultNameGenerator
from tmt.steps.prepare.artifact.providers import (
    ArtifactInfo,
    ArtifactProvider,
    ArtifactProviderId,
    Repository,
    provides_artifact_provider,
)
from tmt.steps.provision import Guest
from tmt.utils import GeneralError, Path, PrepareError, RunError

# Counter for generating unique repository names in the format ``tmt-repo-default-{n}``.
_REPO_NAME_GENERATOR = DefaultNameGenerator(known_names=[])


@provides_artifact_provider('repository-file')
class RepositoryFileProvider(ArtifactProvider):
    """
    Provider for making RPM artifacts from a repository discoverable without downloading them.

    The provider identifier should start with 'repository-file:' followed by a URL to a .repo file,
    e.g., "repository-file:https://download.docker.com/linux/centos/docker-ce.repo".

    The provider downloads the .repo file to the guest's ``/etc/yum.repos.d/`` directory,
    and lists RPMs available in the defined repositories without downloading them, acting as a
    discovery-only provider. Artifacts are all available RPM packages listed in the repository.

    :param raw_provider_id: The full provider identifier, starting with 'repository-file:'.
    :param logger: Logger instance for outputting messages.
    :raises GeneralError: If the .repo file URL is invalid.
    """

    repository: Repository

    def __init__(self, raw_provider_id: str, repository_priority: int, logger: tmt.log.Logger):
        super().__init__(raw_provider_id, repository_priority, logger)

    @classmethod
    def _extract_provider_id(cls, raw_provider_id: str) -> ArtifactProviderId:
        prefix = 'repository-file:'
        if not raw_provider_id.startswith(prefix):
            raise ValueError(f"Invalid repository provider format: '{raw_provider_id}'.")
        value = raw_provider_id[len(prefix) :]
        if not value:
            raise ValueError("Missing repository URL.")
        return value

    def get_installable_artifacts(self) -> Sequence[ArtifactInfo]:
        # Repository provider does not enumerate individual artifacts.
        # The repository is installed and packages are available through the package manager.
        # There is no need to download individual artifact files.
        return []

    def _download_artifact(self, artifact: ArtifactInfo, guest: Guest, destination: Path) -> None:
        """This provider only discovers repos; it does not download individual RPMs."""
        raise AssertionError(
            "RepositoryFileProvider does not support downloading individual RPMs."
        )

    def fetch_contents(
        self,
        guest: Guest,
        download_path: tmt.utils.Path,
        exclude_patterns: Optional[list[Pattern[str]]] = None,
    ) -> list[tmt.utils.Path]:
        # Fetches and initializes the repository from the URL.
        # Repository provider does not download individual artifacts. Instead, it fetches
        # the repository file which will be installed via get_repositories(). Packages are
        # then available through the package manager.
        # It returns an Empty list, as no individual artifact files are downloaded.

        self.logger.info(f"Initializing repository provider with URL: {self.id}")
        # TODO: This should not be using Repository.from_url
        self.repository = Repository.from_url(url=self.id, logger=self.logger)
        self.logger.info(
            f"Repository initialized: {self.repository.name} "
            f"(repo IDs: {', '.join(self.repository.repo_ids)})"
        )
        return []

    def get_repositories(self) -> list[Repository]:
        self.logger.info(f"Providing repository '{self.repository.name}' for installation ")
        return [self.repository]


def create_repository(
    artifact_dir: Path,
    guest: Guest,
    logger: tmt.log.Logger,
    priority: int,
    repo_name: Optional[str] = None,
) -> Repository:
    """
    Create a local RPM repository from a directory on the guest.

    Creates repository metadata and prepares a Repository object. Does not install
    the repository on the guest system. Use install_repository() to make it visible
    to the package manager.

    :param artifact_dir: Path to the directory on the guest containing RPM files.
    :param guest: Guest instance where the repository metadata will be created.
    :param logger: Logger instance for outputting debug and error messages.
    :param repo_name: Name for the repository. If not provided, generates a unique
        name using the format ``tmt-repo-default-{n}``.
    :param priority: Repository priority. Lower values have higher priority.
    :returns: Repository object representing the newly created repository.
    :raises PrepareError: If the package manager does not support creating repositories
        or if metadata creation fails.
    """
    repo_name = repo_name or f"tmt-repo-{_REPO_NAME_GENERATOR.get()}"

    logger.info(f"Creating repository '{repo_name}' from directory '{artifact_dir}'")

    # Ensure the artifact directory exists
    guest.execute(
        tmt.utils.Command('mkdir', '-p', artifact_dir),
        silent=True,
    )

    # Create Repository Metadata
    logger.info(f"Creating repository metadata for '{artifact_dir}'.")
    try:
        guest.package_manager.create_repository(artifact_dir)
    except RunError as error:
        raise PrepareError(f"Failed to create repository metadata in '{artifact_dir}'") from error

    # Generate .repo File Content
    repo_string = f"""[{tmt.utils.sanitize_name(repo_name)}]
name={repo_name}
baseurl=file://{artifact_dir}
enabled=1
gpgcheck=0
priority={priority}"""

    logger.debug(f"Generated .repo file content:\n{repo_string}")

    # Create Repository Object
    created_repository = Repository.from_content(
        content=repo_string, name=repo_name, logger=logger
    )

    logger.info(f"Successfully created repository '{created_repository.name}' ")

    return created_repository
