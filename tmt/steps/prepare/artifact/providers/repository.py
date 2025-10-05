"""
Artifact provider for discovering RPMs from repository files.

"""

from collections.abc import Iterator, Sequence
from re import Pattern
from shlex import quote
from typing import Optional
from urllib.parse import unquote, urlparse

import tmt.log
from tmt.steps.prepare.artifact.providers import (
    ArtifactProvider,
    ArtifactProviderId,
    DownloadError,
    provides_artifact_provider,
)
from tmt.steps.prepare.artifact.providers.koji import RpmArtifactInfo
from tmt.steps.provision import Guest
from tmt.utils import GeneralError, Path, ShellScript


class RepositoryManager:
    """
    A utility class for managing DNF repositories on a guest.
    """

    @staticmethod
    def enable_repository(
        guest: Guest, url: str, repo_filename: str, logger: tmt.log.Logger
    ) -> Path:
        """
        Download a .repo file to the guest, making the repository available.

        :param guest: The guest to operate on.
        :param url: The URL of the .repo file to download.
        :param repo_filename: The target filename for the .repo file.
        :param logger: The logger for outputting messages.
        :return: The path to the newly created repository file on the guest.
        :raises DownloadError: If the download fails.
        """
        repo_dest = Path("/etc/yum.repos.d") / repo_filename
        sudo = "sudo " if not guest.facts.is_superuser else ""
        try:
            # Use -L to follow redirects and --fail to error out on HTTP errors.
            script = ShellScript(f"{sudo}curl -L --fail -o {quote(str(repo_dest))} {quote(url)}")
            guest.execute(script, silent=True)
        except GeneralError as error:
            raise DownloadError(f"Failed to download repository file to '{repo_dest}'.") from error

        return repo_dest

    @staticmethod
    def get_repository_id(guest: Guest, repo_filepath: Path, logger: tmt.log.Logger) -> str:
        """
        Get the repository ID from a .repo file on the guest.

        :param guest: The guest to query.
        :param repo_filepath: The path to the .repo file on the guest.
        :param logger: The logger for outputting messages.
        :return: The repository ID.
        :raises GeneralError: If the repo ID cannot be extracted.
        """
        script = ShellScript(
            f"grep '^\\[' {quote(str(repo_filepath))} | head -n 1 | sed 's/^\\[\\(.*\\)\\]$/\\1/'"
        )
        result = guest.execute(script, silent=True)

        repo_id = result.stdout.strip() if result.stdout else ""
        if not repo_id:
            raise GeneralError(f"Could not extract repository ID from '{repo_filepath}'.")

        return repo_id

    @staticmethod
    def fetch_rpms(
        guest: Guest, repo_filepath: Path, logger: tmt.log.Logger
    ) -> list[RpmArtifactInfo]:
        """
        Query the guest to find all packages available in a specific repository.

        :param guest: The guest to query.
        :param repo_filepath: The path to the .repo file on the guest.
        :param logger: The logger for outputting messages.
        :return: A list of RpmArtifactInfo objects for each found package.
        :raises GeneralError: If dnf query fails.
        """
        # 1. Get the repository ID.
        repo_id = RepositoryManager.get_repository_id(guest, repo_filepath, logger)

        # 2. List all available packages from that repository using a robust query format.
        # We query for name, epoch, version, release, and architecture.
        qf = "'%{name} %{epoch} %{version} %{release} %{arch}'"
        script = ShellScript(
            "dnf repoquery --refresh --disablerepo='*' "
            f"--enablerepo={quote(repo_id)} --available --queryformat {qf}"
        )
        result = guest.execute(script, silent=True)
        if result.stdout is None:
            raise GeneralError(
                f"Failed to list packages from repo '{repo_id}': no command output."
            )

        # 3. Parse the structured output into RpmArtifactInfo objects.
        rpm_list: list[RpmArtifactInfo] = []
        for line in result.stdout.strip().splitlines():
            try:
                name, epoch, version, release, arch = line.split()
                # dnf uses '(none)' for a missing epoch.
                if epoch == "(none)":
                    epoch = ""
                    nvr = f"{name}-{version}-{release}"
                else:
                    nvr = f"{name}-{epoch}:{version}-{release}"

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
            except ValueError:
                logger.warning(f"Failed to parse RPM from repoquery output: '{line}'")
                continue

        return rpm_list


# ignore[type-arg]: TypeVar in provider registry annotations is
# puzzling for type checkers. And not a good idea in general, probably.
@provides_artifact_provider('repository')  # type: ignore[arg-type]
class RepositoryFileProvider(ArtifactProvider[RpmArtifactInfo]):
    """
    Sets up a repository from a .repo file and discovers available RPMs.

    The artifact ID is a URL to a .repo file. This provider's main purpose
    is to download this file to '/etc/yum.repos.d/' on the guest.

    It then lists all RPMs made available by the new repository but does
    not download them, serving as a "discovery-only" provider.
    """

    def __init__(self, raw_provider_id: str, logger: tmt.log.Logger):
        """
        Initializes the provider and validates the .repo file URL.

        :param raw_provider_id: The URL of the .repo file.
        :param logger: The logger for outputting messages.
        :raises GeneralError: If the URL format is invalid.
        """
        super().__init__(raw_provider_id, logger)

        try:
            self._parsed_url = urlparse(self.id)
            if not self._parsed_url.scheme or not self._parsed_url.netloc:
                raise ValueError("URL must have a scheme and network location.")
        except ValueError as exc:
            raise GeneralError(f"Invalid URL format for .repo file: '{self.id}'.") from exc

        # Cache for the list of RPMs discovered in the repository.
        # It's populated by fetch_contents().
        self._rpm_list: Optional[list[RpmArtifactInfo]] = None

    @property
    def repo_filename(self) -> str:
        """A suitable filename extracted from the URL path."""
        return unquote(Path(self._parsed_url.path).name)

    @classmethod
    def _extract_provider_id(cls, raw_provider_id: str) -> ArtifactProviderId:
        """The provider ID is the raw URL."""
        return raw_provider_id

    @property
    def artifacts(self) -> Sequence[RpmArtifactInfo]:
        """
        List all RPMs discovered from the repository.

        Note: The `fetch_contents` method must be called first to populate
        the artifact list from the guest.
        """
        if self._rpm_list is None:
            raise GeneralError(
                "RPM list not available. The 'fetch_contents' method must be "
                "called before 'list_artifacts'."
            )
        return self._rpm_list

    def _download_artifact(
        self, artifact: RpmArtifactInfo, guest: Guest, destination: Path
    ) -> None:
        """This provider only discovers repos; it does not download individual RPMs."""
        raise NotImplementedError(
            "RepositoryFileProvider does not support downloading individual RPMs."
        )

    def fetch_contents(
        self,
        guest: Guest,
        download_path: Path,
        exclude_patterns: Optional[list[Pattern[str]]] = None,
    ) -> list[Path]:
        """
        Enable the repository on the guest and discover its packages.

        This method installs the repository and queries it to discover available
        packages. It does not download any RPMs itself and will return an
        empty list.
        """
        # 1. Install the repository file on the guest.
        repo_dest = RepositoryManager.enable_repository(
            guest=guest, url=self.id, repo_filename=self.repo_filename, logger=self.logger
        )

        # 2. Populate the RPM list for discovery purposes by querying the new repo.
        self._rpm_list = RepositoryManager.fetch_rpms(
            guest=guest, repo_filepath=repo_dest, logger=self.logger
        )

        # This provider does not download any artifacts, so return an empty list.
        return []
