"""
Artifact provider for repository files.
"""

from collections.abc import Iterator
from re import Pattern
from shlex import quote
from urllib.parse import unquote, urlparse

import tmt.log
from tmt.steps.prepare.artifact.providers import (
    ArtifactProvider,
    DownloadError,
)
from tmt.steps.prepare.artifact.providers.info import RpmArtifactInfo
from tmt.steps.provision import Guest
from tmt.utils import GeneralError, Path, ShellScript


class RepositoryFile:
    """
    A helper class representing a repository .repo file from a URL.
    """

    def __init__(self, url: str) -> None:
        # The constructor also serves as a validator for the URL format
        try:
            result = urlparse(url)
            if not result.scheme or not result.netloc:
                raise ValueError
        except ValueError:
            raise GeneralError(f"Invalid URL format for .repo file: '{url}'.")
        self._url = url

    @property
    def url(self) -> str:
        """The URL of the .repo file."""
        return self._url

    @property
    def filename(self) -> str:
        """A suitable filename extracted from the URL path."""
        path = urlparse(self.url).path
        return unquote(Path(path).name)


class RepositoryFileProvider(ArtifactProvider[RpmArtifactInfo]):
    """
    Sets up a repository on the guest and lists the RPMs it provides.

    The artifact_id is a URL to a .repo file. This provider's main
    purpose is to download this file and place it in '/etc/yum.repos.d/'.

    It then lists all RPMs made available by the new repository but does
    not download any of them.
    """

    def __init__(self, logger: tmt.log.Logger, artifact_id: str):
        super().__init__(logger, artifact_id)
        self.repo_file = RepositoryFile(url=self.artifact_id)
        # Cache for the list of RPMs discovered in the repository
        self._rpm_list: list[RpmArtifactInfo] = []

    def _parse_artifact_id(self, artifact_id: str) -> str:
        """
        Validate the artifact identifier using the RepositoryFile class.
        """
        # The constructor of RepositoryFile handles URL validation
        RepositoryFile(url=artifact_id)
        return artifact_id

    def _fetch_rpms(self, guest: Guest, repo_filepath: Path) -> None:
        """
        Query the guest to find all packages available in the new repository.
        """
        # TODO: This method needs to be implemented to populate self._rpm_list with RPMs
        # from the repository. Currently using an empty list as a temporary solution.
        self._rpm_list = []

    def list_artifacts(self) -> Iterator[RpmArtifactInfo]:
        """
        List all RPMs available from the repository.

        Note: This requires the repository to be installed and queried first,
        which is handled by the ``download_artifacts`` method.
        """
        raise NotImplementedError

    def _download_artifact(
        self, artifact: RpmArtifactInfo, guest: Guest, destination: Path
    ) -> None:
        """This provider only sets up the repo, it does not download RPMs."""

    def download_artifacts(
        self,
        guest: Guest,
        download_path: Path,
        exclude_patterns: list[Pattern[str]],
    ) -> list[Path]:
        """
        Download the .repo file to the guest, making the repository available.

        This method overrides the default behavior to prevent downloading
        individual RPMs. It installs the repository, lists the available
        packages for discovery, and then returns.
        """

        # 1. Install the repository file on the guest using info from our helper object
        filename = self.repo_file.filename
        url = self.repo_file.url
        repo_dest = Path("/etc/yum.repos.d") / filename

        sudo = "sudo " if not guest.facts.is_superuser else ""
        self.logger.info(f"Installing repository '{url}' to '{repo_dest}'.")

        try:
            # TODO: Add retry Mechanism
            guest.execute(
                ShellScript(f"{sudo}curl -L --fail -o {quote(str(repo_dest))} {quote(url)}"),
                silent=True,
            )
        except GeneralError as error:
            raise DownloadError(f"Failed to download repository file to '{repo_dest}'.") from error

        # 2. Populate the RPM list for discovery purposes
        self._fetch_rpms(guest, repo_dest)

        self.logger.info("Repository setup is complete.")
        # 3. Return list of available Artifacts
        # TODO: Finalize contract of what needs to be returned from Artifact Repository
        return []
