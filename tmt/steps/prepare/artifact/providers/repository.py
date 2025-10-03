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


class RepositoryManager:
    """
    This class contains static helper methods for managing repositories.
    """

    # TODO : Add more methods like enable / disable / change_priority

    @staticmethod
    def enable_repository(guest: Guest, url: str, logger: tmt.log.Logger) -> Path:
        """
        Download a .repo file to the guest, making the repository available.

        :param guest: The guest to operate on.
        :param url: The URL of the .repo file.
        :param logger: The logger for outputting messages.
        :return: The path to the newly created repository file on the guest.
        """
        repo_file = RepositoryFile(url=url)
        filename = repo_file.filename
        repo_dest = Path("/etc/yum.repos.d") / filename

        sudo = "sudo " if not guest.facts.is_superuser else ""
        logger.info(f"Installing repository from '{url}' to '{repo_dest}'.")

        try:
            # Using -L to follow redirects and --fail to error out on HTTP errors.
            guest.execute(
                ShellScript(f"{sudo}curl -L --fail -o {quote(str(repo_dest))} {quote(url)}"),
                silent=True,
            )
        except GeneralError as error:
            raise DownloadError(f"Failed to download repository file to '{repo_dest}'.") from error

        return repo_dest

    @staticmethod
    def fetch_rpms(
        guest: Guest, logger: tmt.log.Logger, repo_filepath: Path
    ) -> list[RpmArtifactInfo]:
        """
        Query the guest to find all packages available in a specific repository.

        :param guest: The guest to query.
        :param logger: The logger for outputting messages.
        :param repo_filepath: The path to the .repo file on the guest.
        :return: A list of RpmArtifactInfo objects for each found package.
        """
        # 1. Get the repository ID from the .repo file
        cmd = (
            f"grep '^\\[' {quote(str(repo_filepath))} | head -n 1 | sed 's/^\\[\\(.*\\)\\]$/\\1/'"
        )
        result = guest.execute(ShellScript(cmd), silent=True)

        if result.stdout is None:
            raise GeneralError("No output from repository ID query.")
        repo_id = result.stdout.strip()
        if not repo_id:
            raise GeneralError(f"No repository ID found in '{repo_filepath}'.")

        # 2. List all available packages from that repository
        cmd = (
            f"dnf repoquery --refresh --disablerepo='*' --enablerepo={quote(repo_id)} --available"
        )
        result = guest.execute(ShellScript(cmd), silent=True)
        if result.stdout is None:
            raise GeneralError("No output from package list query.")

        # 3. Parse the dnf repoquery output into RpmArtifactInfo objects
        rpm_list: list[RpmArtifactInfo] = []
        with_epoch = re.compile(r'^(.+)-(\d+):(.+)-(.+)\.(.+)$')
        without_epoch = re.compile(r'^(.+)-(.+)-(.+)\.(.+)$')

        for line in result.stdout.splitlines():
            line = line.strip()
            if not line:
                continue

            epoch: str = ""
            match = with_epoch.match(line)
            if match:
                name, epoch_str, version, release, arch = match.groups()
                epoch = epoch_str  # Use epoch_str directly (it's already a string)
            else:
                match = without_epoch.match(line)
                if match:
                    name, version, release, arch = match.groups()
                else:
                    logger.warning(f"Failed to parse RPM from repoquery output: '{line}'")
                    continue

            nvr = (
                f"{name}-{version}-{release}"
                if epoch == ""
                else f"{name}-{epoch}:{version}-{release}"
            )
            rpm_list.append(
                RpmArtifactInfo(
                    _raw_artifact={
                        'name': name,
                        'version': version,
                        'release': release,
                        'arch': arch,
                        'nvr': nvr,
                        'epoch': epoch,
                    }
                )
            )
        return rpm_list


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
        # The constructor of RepositoryFile handles URL validation
        self.repo_file = RepositoryFile(url=self.artifact_id)
        # Cache for the list of RPMs discovered in the repository
        self._rpm_list: Optional[list[RpmArtifactInfo]] = None

    def _parse_artifact_id(self, artifact_id: str) -> str:
        """The artifact_id is the URL itself, validated by RepositoryFile."""
        return artifact_id

    def list_artifacts(self) -> Iterator[RpmArtifactInfo]:
        """
        List all RPMs available from the repository.

        Note: This requires the repository to be installed and queried first,
        which is handled by the `download_artifacts` method.
        """
        if self._rpm_list is None:
            raise GeneralError(
                "RPM list not available. "
                "The 'fetch' method must be called before 'list_artifacts'."
            )
        return iter(self._rpm_list)

    def _download_artifact(
        self, artifact: RpmArtifactInfo, guest: Guest, destination: Path
    ) -> None:
        """This provider only sets up the repo; it does not download individual RPMs."""
        raise NotImplementedError(
            "RepositoryFileProvider does not support downloading individual RPMs."
        )

    def download_artifacts(
        self,
        guest: Guest,
        download_path: Path,
        exclude_patterns: Optional[list[Pattern[str]]] = None,
    ) -> list[Path]:
        raise NotImplementedError

    def fetch(
        self,
        guest: Guest,
        download_path: Path,
        exclude_patterns: Optional[list[Pattern[str]]] = None,
    ) -> None:
        """
        Download the .repo file to the guest, making the repository available.

        This method installs the repository, queries it to discover available
        packages, and caches them for the `list_artifacts` method.
        It does not download any RPMs itself.
        """
        # 1. Install the repository file on the guest.
        repo_dest = RepositoryManager.enable_repository(
            guest=guest, url=self.repo_file.url, logger=self.logger
        )

        # 2. Populate the RPM list for discovery purposes by querying the new repo.
        self._rpm_list = RepositoryManager.fetch_rpms(
            guest=guest, logger=self.logger, repo_filepath=repo_dest
        )
