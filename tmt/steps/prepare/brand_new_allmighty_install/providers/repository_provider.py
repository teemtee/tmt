"""
Repository file artifact provider for tmt's allmighty-install plugin.

Downloads a .repo file from a URL and places it in /etc/yum.repos.d on the guest.
No installation support is provided, as per requirements.
"""

from collections.abc import Iterator
from functools import cached_property
from shlex import quote
from typing import Any
from urllib.parse import urlparse

from tmt.container import container
from tmt.steps.prepare.brand_new_allmighty_install.providers import (
    ArtifactInfo,
    ArtifactProvider,
    ArtifactType,
    DownloadError,
)
from tmt.steps.provision import Guest
from tmt.utils import GeneralError, Path, ShellScript


@container
class RepositoryArtifactInfo(ArtifactInfo):
    """
    Artifact information for a repository file.
    The 'url' is the URL to the .repo file, replacing 'id' to avoid type conflict
    with the base class's id: int. Uses a dummy id=0 to satisfy the base class.
    """

    url: str  # Store the URL as the identifier, since id: int in base class
    type: ArtifactType = ArtifactType.REPOSITORY_FILE

    def __init__(self, url: str, **kwargs: Any) -> None:
        """
        Initialize with the URL to the .repo file.

        :param url: URL to the .repo file
        :param kwargs: Additional arguments for base class
        """
        # TODO: The base class requires an integer 'id', but a URL is the natural
        # identifier here. Using a dummy id=0 until the base class can accommodate
        # string-based identifiers.
        super().__init__(id=0, _raw_artifact={'url': url}, **kwargs)
        self.url = url

    @property
    def name(self) -> str:
        """
        Extract the filename from the URL path, ensuring it ends with .repo.

        :returns: The filename of the .repo file
        :raises ValueError: If the URL does not point to a .repo file or the
                            filename is invalid.
        """
        parsed_url = urlparse(self.url)
        filename = Path(parsed_url.path).name
        if not filename.endswith('.repo'):
            raise ValueError(f"URL must point to a .repo file, got: {filename}")
        if not filename:
            raise ValueError(f"Invalid filename extracted from URL: {self.url}")
        return filename

    @property
    def location(self) -> str:
        """
        Return the URL as the download location.

        :returns: The URL to the .repo file
        """
        return self.url


class RepositoryProvider(ArtifactProvider[RepositoryArtifactInfo]):
    """
    Provider for downloading repository files from a URL and placing them in /etc/yum.repos.d.
    The artifact ID is a URL to a .repo file. The file is downloaded to a temporary location
    and then moved to /etc/yum.repos.d on the guest with appropriate permissions.
    No package installation is performed.
    """

    def _parse_artifact_id(self, artifact_id: str) -> str:
        """
        Validate the artifact identifier as a URL to a .repo file.

        :param artifact_id: The raw URL to the .repo file
        :returns: The validated URL
        :raises ValueError: If the URL is invalid or does not point to a .repo file
        """
        if not artifact_id.startswith(('http://', 'https://')):
            raise ValueError(f"Invalid repository URL: {artifact_id}. Only HTTP(S) is supported.")
        parsed_url = urlparse(artifact_id)
        filename = Path(parsed_url.path).name
        if not filename.endswith('.repo'):
            raise ValueError(f"URL must point to a .repo file, got: {filename}")
        if not filename:
            raise ValueError(f"Invalid filename extracted from URL: {artifact_id}")

        self.logger.debug(f"Parsed repository artifact URL: {artifact_id}")
        return artifact_id

    @cached_property
    def _repository_artifact_info(self) -> RepositoryArtifactInfo:
        """Cached artifact info to avoid re-validating the URL."""
        return RepositoryArtifactInfo(url=self.artifact_id)

    def list_artifacts(self) -> Iterator[RepositoryArtifactInfo]:
        """
        Return a single artifact info for the repository file URL.

        :yields: A RepositoryArtifactInfo instance for the .repo file
        """
        self.logger.debug(f"Listing repository artifact for URL: {self.artifact_id}")
        yield self._repository_artifact_info

    def _download_artifact(
        self, artifact: RepositoryArtifactInfo, guest: Guest, destination: Path
    ) -> None:
        """
        Download the .repo file from the URL and place it in /etc/yum.repos.d on the guest.

        :param artifact: The RepositoryArtifactInfo containing the URL
        :param guest: The guest where the file should be placed
        :param destination: Temporary path for downloading the file
        :raises DownloadError: If downloading or file placement fails
        """
        url = artifact.url
        filename = artifact.name
        repo_destination = Path("/etc/yum.repos.d") / filename
        sudo_prefix = "sudo " if not guest.facts.is_superuser else ""

        self.logger.info(f"Processing repository file from {url} to {repo_destination} on guest")

        try:
            # Download the file to the temporary destination
            self.logger.debug(f"Downloading {filename} to temporary {destination}")
            guest.execute(
                ShellScript(f"curl -L --fail -o {quote(str(destination))} {quote(url)}"),
                silent=True,
            )

            # Warn if the destination file already exists
            try:
                guest.execute(ShellScript(f"test -f {quote(str(repo_destination))}"), silent=True)
                self.logger.warning(f"Overwriting existing repository file: {repo_destination}")
            except GeneralError:
                pass  # File does not exist, no need to warn

            # Move the file to /etc/yum.repos.d and set permissions
            self.logger.debug(f"Moving {filename} to {repo_destination} with 644 permissions")
            guest.execute(
                ShellScript(
                    f"{sudo_prefix}mv {quote(str(destination))} {quote(str(repo_destination))} && "
                    f"{sudo_prefix}chmod 644 {quote(str(repo_destination))}"
                ),
                silent=True,
            )

            self.logger.info(f"Successfully placed {filename} in {repo_destination}")

        except GeneralError as e:
            raise DownloadError(f"Failed to process {url} to {repo_destination}: {e!s}") from e
