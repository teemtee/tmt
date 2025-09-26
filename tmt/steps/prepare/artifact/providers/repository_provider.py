"""
Artifact providers for Repository and Repository Files.
"""

from collections.abc import Iterator
from shlex import quote
from urllib.parse import urlparse

import tmt.log
import tmt.utils
from tmt.container import container
from tmt.steps.prepare.artifact.providers import (
    ArtifactProvider,
    DownloadError,
)
from tmt.steps.prepare.artifact.providers.info import ArtifactInfo
from tmt.steps.provision import Guest
from tmt.utils import GeneralError, Path, ShellScript


@container
class RepositoryFileInfo(ArtifactInfo):
    """
    A single repository file channel.

    Encapsulates information about a repository file, including its URL and
    derived identifier (filename). It validates that the URL uses HTTP/HTTPS
    and points to a file with a ``.repo`` extension.
    """

    _raw_artifact: str

    def __post_init__(self) -> None:
        parsed_url = urlparse(self._raw_artifact)
        if parsed_url.scheme not in ('http', 'https'):
            raise ValueError(
                f"Invalid repository URL: {self._raw_artifact}. Only HTTP(S) is supported."
            )
        path = tmt.utils.Path(parsed_url.path)
        if path.suffix != '.repo':
            raise ValueError(f"URL must point to a .repo file, got: {path.name}")
        self._id = path.name

    @property
    def id(self) -> str:
        """The filename of the repository file"""
        return self._id

    @property
    def location(self) -> str:
        """The location (URL) of the repository file"""
        return self._raw_artifact


class RepositoryFileProvider(ArtifactProvider[RepositoryFileInfo]):
    """
    Provides repository files for download.

    The artifact_id is expected to be a URL to a repository file, which will be
    downloaded to a specified destination on a guest system. The provider
    ensures the URL points to a valid ``.repo`` file and handles downloading
    it to the guest.
    """

    # TODO: Change to RepositoryFileProvider(ArtifactProvider[RpmArtifactInfo])
    # because we will be listing RPM's

    def _parse_artifact_id(self, artifact_id: str) -> str:
        # Validate the artifact_id by creating a RepositoryFileInfo instance
        RepositoryFileInfo(_raw_artifact=artifact_id)
        return artifact_id

    def list_artifacts(self) -> Iterator[RepositoryFileInfo]:
        yield RepositoryFileInfo(_raw_artifact=self.artifact_id)

    def _download_artifact(
        self, artifact: RepositoryFileInfo, guest: Guest, destination: Path
    ) -> None:
        url = artifact.location
        filename = artifact.id
        repo_destination = Path("/etc/yum.repos.d") / filename
        sudo_prefix = "sudo " if not guest.facts.is_superuser else ""

        self.logger.debug(f"Processing repository file from {url} to {repo_destination} on guest.")

        try:
            # Download the file to the temporary destination
            guest.execute(
                ShellScript(f"curl -L --fail -o {quote(str(destination))} {quote(url)}"),
                silent=True,
            )

            # Move the file to /etc/yum.repos.d and set permissions
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

        except GeneralError as e:
            raise DownloadError(
                f"Failed to process repository file from {url} to {repo_destination}."
            ) from e
