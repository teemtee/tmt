"""
Artifact provider for repository files.
"""

from collections.abc import Iterator, Sequence
from re import Pattern
from shlex import quote
from typing import Optional
from urllib.parse import unquote, urlparse

import tmt.log
from tmt.container import container
from tmt.steps.prepare.artifact.providers import (
    ArtifactProvider,
    ArtifactProviderId,
    DownloadError,
)
from tmt.steps.prepare.artifact.providers.koji import RpmArtifactInfo
from tmt.steps.provision import Guest
from tmt.utils import GeneralError, Path, ShellScript


@container
class RepositoryFile:
    """
    A helper class representing a repository .repo file from a URL.
    """

    url: str

    def __post_init__(self) -> None:
        """
        Validates the URL format upon object creation.
        """
        try:
            self._parsed_url = urlparse(self.url)
            if not self._parsed_url.scheme or not self._parsed_url.netloc:
                raise ValueError
        except ValueError as exc:
            raise GeneralError(f"Invalid URL format for .repo file: '{self.url}'.") from exc

    @property
    def filename(self) -> str:
        """A suitable filename extracted from the URL path."""
        return unquote(Path(self._parsed_url.path).name)

    def __str__(self) -> str:
        return self.filename


class RepositoryFileProvider(ArtifactProvider[RpmArtifactInfo]):
    """
    Sets up a repository on the guest and lists the RPMs it provides.

    The artifact_id is a URL to a .repo file. This provider's main
    purpose is to download this file and place it in '/etc/yum.repos.d/'.

    It then lists all RPMs made available by the new repository but does
    not download any of them.
    """

    def __init__(self, raw_provider_id: str, logger: tmt.log.Logger):
        super().__init__(raw_provider_id, logger)
        self.repo_file = RepositoryFile(url=self.id)
        # Cache for the list of RPMs discovered in the repository
        self._rpm_list: list[RpmArtifactInfo] = []

    @classmethod
    def _extract_provider_id(cls, raw_provider_id: str) -> ArtifactProviderId:
        return raw_provider_id

    def _fetch_rpms(self, guest: Guest, repo_filepath: Path) -> None:
        """
        Query the guest to find all packages available in the new repository.
        """
        # TODO: This method needs to be implemented to populate self._rpm_list with RPMs
        # from the repository. Currently using an empty list as a temporary solution.
        self._rpm_list = []

    @property
    def artifacts(self) -> Sequence[RpmArtifactInfo]:
        raise NotImplementedError

    def _download_artifact(
        self, artifact: RpmArtifactInfo, guest: Guest, destination: Path
    ) -> None:
        """This provider only sets up the repo, it does not download RPMs."""

    def fetch_contents(
        self,
        guest: Guest,
        download_path: tmt.utils.Path,
        exclude_patterns: Optional[list[Pattern[str]]] = None,
    ) -> list[tmt.utils.Path]:
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
