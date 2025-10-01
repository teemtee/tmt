"""
Artifact provider for repository files.
"""

import re
from collections.abc import Iterator
from re import Pattern
from shlex import quote
from typing import Optional
from urllib.parse import unquote, urlparse

import tmt.log
from tmt.container import container
from tmt.steps.prepare.artifact.providers import (
    ArtifactProvider,
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
        try:
            self._parsed_url = urlparse(self.url)
            if not self._parsed_url.scheme or not self._parsed_url.netloc:
                raise ValueError
        except ValueError:
            raise GeneralError(f"Invalid URL format for .repo file: '{self.url}'.")

    @property
    def filename(self) -> str:
        """A suitable filename extracted from the URL path."""
        path = self._parsed_url.path
        return unquote(Path(path).name)

    def __str__(self) -> str:
        return f"{self.filename}"


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
        return artifact_id

    def _fetch_rpms(self, guest: Guest, repo_filepath: Path) -> None:
        """
        Query the guest to find all packages available in the new repository.
        """

        # Get the repository ID
        cmd = f"""
            grep '^\\[' {quote(str(repo_filepath))} | head -n 1 | sed 's/^\\[\\(.*\\)\\]$/\\1/'
            """
        result = guest.execute(ShellScript(cmd), silent=True)
        if result.stdout is None:
            raise GeneralError("No output from repository ID query.")
        repo_id = result.stdout.strip()
        if not repo_id:
            raise GeneralError(f"No repository ID found in {repo_filepath}.")

        # List available packages
        cmd = f"""
            dnf repoquery --refresh --disablerepo='*' --enablerepo={quote(repo_id)} --available
            """
        result = guest.execute(ShellScript(cmd), silent=True)
        if result.stdout is None:
            raise GeneralError("No output from package list query.")
        output = result.stdout

        # Parse the output
        self._rpm_list = []
        with_epoch = re.compile(r'^(.+)-(\d+):(.+)-(.+)\.(.+)$')
        without_epoch = re.compile(r'^(.+)-(.+)-(.+)\.(.+)$')

        for line in output.splitlines():
            line = line.strip()
            if not line:
                continue

            match = with_epoch.match(line)
            if match:
                name, epoch_str, version, release, arch = match.groups()
                epoch = int(epoch_str)
            else:
                match = without_epoch.match(line)
                if match:
                    name, version, release, arch = match.groups()
                    epoch = None
                else:
                    self.logger.warning(f"Failed to parse RPM: {line}")
                    continue

            nvr = (
                f"{name}-{version}-{release}"
                if epoch is None
                else f"{name}-{epoch}:{version}-{release}"
            )
            self._rpm_list.append(
                RpmArtifactInfo(
                    _raw_artifact={
                        'name': name,
                        'version': version,
                        'release': release,
                        'arch': arch,
                        'nvr': nvr,
                    }
                )
            )

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
