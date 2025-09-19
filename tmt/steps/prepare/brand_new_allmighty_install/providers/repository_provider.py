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

    url: str
    _name: str
    type: ArtifactType = ArtifactType.REPOSITORY_FILE

    def __init__(self, url: str, **kwargs: Any) -> None:
        # TODO: The base class requires an integer 'id', but a URL is the natural
        # identifier here. Using a dummy id=0 until the base class can accommodate
        # string-based identifiers.
        super().__init__(id=0, _raw_artifact={'url': url}, **kwargs)
        self.url = url

        # Validate URL and extract filename
        parsed_url = urlparse(url)
        if parsed_url.scheme not in ('http', 'https'):
            raise ValueError(f"Invalid repository URL: {url}. Only HTTP(S) is supported.")

        path = Path(parsed_url.path)
        if path.suffix != '.repo':
            raise ValueError(f"URL must point to a .repo file, got: {path.name}")

        self._name = path.name

    @property
    def name(self) -> str:
        """The filename of the .repo file."""
        return self._name

    @property
    def location(self) -> str:
        """The URL of the .repo file."""
        return self.url


class RepositoryProvider(ArtifactProvider[RepositoryArtifactInfo]):
    """
    Provider for downloading repository files from a URL and placing them in /etc/yum.repos.d.

    The artifact ID is a URL to a .repo file. The file is downloaded to a temporary
    location and then moved to /etc/yum.repos.d on the guest with appropriate
    permissions. No package installation is performed.
    """

    def _parse_artifact_id(self, artifact_id: str) -> str:
        """
        Validate the artifact identifier as a URL to a .repo file.

        :param artifact_id: The raw URL to the .repo file.
        :returns: The validated URL.
        :raises ValueError: If the URL is invalid or does not point to a .repo file.
        """
        # The constructor of RepositoryArtifactInfo handles the validation. This
        # will raise ValueError if the artifact_id is not a valid repo URL.
        RepositoryArtifactInfo(url=artifact_id)
        return artifact_id

    @cached_property
    def _repository_artifact_info(self) -> RepositoryArtifactInfo:
        """Cached artifact info to avoid re-validating the URL."""
        return RepositoryArtifactInfo(url=self.artifact_id)

    def list_artifacts(self) -> Iterator[RepositoryArtifactInfo]:
        yield self._repository_artifact_info

    def _download_artifact(
        self, artifact: RepositoryArtifactInfo, guest: Guest, destination: Path
    ) -> None:
        """
        Download the .repo file from the URL and place it in /etc/yum.repos.d on the guest.

        :param artifact: The RepositoryArtifactInfo containing the URL.
        :param guest: The guest where the file should be placed.
        :param destination: Temporary path for downloading the file.
        :raises DownloadError: If downloading or file placement fails.
        """
        url = artifact.url
        filename = artifact.name
        repo_destination = Path("/etc/yum.repos.d") / filename
        sudo_prefix = "sudo " if not guest.facts.is_superuser else ""

        self.logger.debug(f"Processing repository file from {url} to {repo_destination} on guest.")

        try:
            # Download the file to the temporary destination
            self.logger.debug(f"Downloading {filename} to temporary {destination}.")
            guest.execute(
                ShellScript(f"curl -L --fail -o {quote(str(destination))} {quote(url)}"),
                silent=True,
            )

            # Move the file to /etc/yum.repos.d and set permissions
            self.logger.debug(f"Moving {filename} to {repo_destination} with 644 permissions.")
            guest.execute(
                ShellScript(
                    f"""
                 set -e
                 {sudo_prefix}mv {quote(str(destination))} {quote(str(repo_destination))}
                 {sudo_prefix}chmod 644 {quote(str(repo_destination))}
                """
                ),
                silent=True,
            )

            self.logger.debug(f"Successfully placed {filename} in {repo_destination}.")

        except GeneralError as e:
            raise DownloadError(
                f"Failed to process repository file from {url} to {repo_destination}."
            ) from e
