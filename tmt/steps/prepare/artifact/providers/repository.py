"""
Artifact provider for discovering RPMs from repository files.
"""

import configparser
import tempfile
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
from tmt.utils import GeneralError, Path, RetryError, ShellScript, retry


class Repository:
    """
    Represents a DNF or Yum repository on a guest.

    :param url: The URL of the .repo file.
    :param filename: The target filename for the .repo file on the guest.
    """

    def __init__(self, url: str, filename: str):
        self.url = url
        self.filename = filename
        self.names: list[str] = []
        self.filepath: Optional[Path] = None
        self._rpms: Optional[list[RpmArtifactInfo]] = None
        self.guest: Optional[Guest] = None
        self.logger: Optional[tmt.log.Logger] = None

    def install(self, guest: Guest, logger: tmt.log.Logger) -> None:
        """
        Install the .repo file on the guest and extract its repository IDs.

        This method downloads the .repo file from the specified URL and places it in
        ``/etc/yum.repos.d/`` on the guest, making all repositories defined in the
        file available to DNF or Yum. The download is retried up to 3 times with a
        5-second delay between attempts to handle transient network failures (e.g.,
        timeouts or server errors). Command output and errors are logged via the
        provided logger for debugging. The repository IDs are extracted by pulling
        the file to the local system and parsing it as an INI file, taking all
        section names.

        :param guest: The guest to operate on.
        :param logger: The logger for outputting messages.
        :raises DownloadError: If the download fails after all retries.
        :raises GeneralError: If no repository IDs can be extracted or the file is
                             not a valid INI file.
        """
        self.logger = logger
        self.guest = guest
        self.filepath = Path("/etc/yum.repos.d") / self.filename
        script = ShellScript(
            f"{guest.facts.sudo_prefix} curl -L --fail -o {quote(str(self.filepath))} "
            f"{quote(self.url)}"
        )
        # Retry the curl command up to 3 times if it fails (e.g., due to network issues).
        # The retry function catches any Exception, logs failures with logger.fail,
        # waits 5 seconds between attempts, and raises RetryError if all attempts fail.
        # Use silent=False (default) to ensure full error details are included in
        # exceptions for proper retry handling and debugging.
        try:
            retry(
                func=lambda: guest.execute(script),
                attempts=3,
                interval=5,
                label=f"download .repo file from '{self.url}'",
                logger=logger,
            )
        except RetryError as error:
            # Use the last exception for the DownloadError message
            last_error = error.causes[-1] if error.causes else Exception("Unknown error")
            raise DownloadError(
                f"Failed to download repository file from '{self.url}' to "
                f"'{self.filepath}': {last_error!s}"
            ) from last_error

        # Pull the .repo file to a local temporary file and parse it
        with tempfile.NamedTemporaryFile(mode='w+', suffix='.repo') as temp_file:
            try:
                guest.pull(source=self.filepath, destination=Path(temp_file.name))
            except GeneralError as error:
                raise GeneralError(
                    f"Failed to pull .repo file from '{self.filepath}' on guest: {error!s}"
                ) from error

            # Parse the .repo file as INI
            parser = configparser.ConfigParser()
            try:
                parser.read(temp_file.name)
            except configparser.Error as error:
                raise GeneralError(
                    f"Failed to parse .repo file '{self.filepath}' as INI: {error!s}"
                ) from error

            # Get all section names as repository IDs
            self.names = parser.sections()
            if not self.names:
                raise GeneralError(
                    f"No repository sections found in .repo file '{self.filepath}'."
                )

    @property
    def rpms(self) -> list[RpmArtifactInfo]:
        """
        List all packages available in the repositories.

        Queries all repositories defined in the .repo file (by their IDs) using
        the dnf package manager to discover available packages. Currently supports
        only dnf-based systems (e.g., RHEL 8+, Fedora).
        :return: A list of RpmArtifactInfo objects for each found package.
        :raises GeneralError: If no repositories have been installed or if the package query fails.
        """
        if self._rpms is not None:
            return self._rpms

        if not self.names or self.filepath is None:
            raise GeneralError("Repositories must be installed before accessing RPMs.")

        if self.guest is None or self.logger is None:
            raise GeneralError("Must call install() first to set guest and logger.")

        # List all available packages from the repositories using a robust query format.
        qf = "'%{name} %{epoch} %{version} %{release} %{arch}'"
        # Join all repository IDs for --enablerepo
        repo_ids = ','.join(quote(name) for name in self.names)
        # FIXME: Using direct 'dnf repoquery' command breaks compatibility with yum
        # (RHEL 6, RHEL 7). Should create and extend guest.package_manager.repoquery to
        # support both dnf and yum package managers.
        try:
            script = ShellScript(
                f"dnf repoquery --refresh --disablerepo='*' --enablerepo={repo_ids} "
                f"--queryformat {qf}"
            )
            result = self.guest.execute(script, silent=True)
            output = result.stdout or ""
        except GeneralError as error:
            raise GeneralError(
                f"Failed to query packages from repos '{', '.join(self.names)}': {error!s}"
            ) from error

        # Parse the structured output into RpmArtifactInfo objects.
        self._rpms = []
        for line in output.strip().splitlines():
            try:
                name, epoch, version, release, arch = line.split()
                # dnf uses '(none)' for a missing epoch
                if epoch == "(none)":
                    epoch = ""
                    nvr = f"{name}-{version}-{release}"
                else:
                    nvr = f"{name}-{epoch}:{version}-{release}"

                self._rpms.append(
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
                self.logger.warning(f"Failed to parse RPM from repoquery output: '{line}'")
                continue

        return self._rpms


# ignore[type-arg]: TypeVar in provider registry annotations is
# puzzling for type checkers. And not a good idea in general, probably.
@provides_artifact_provider('repository')  # type: ignore[arg-type]
class RepositoryFileProvider(ArtifactProvider[RpmArtifactInfo]):
    """
    Sets up repositories from a .repo file and discovers available RPMs.

    The artifact ID is a URL to a .repo file. This provider's main purpose
    is to download this file to '/etc/yum.repos.d/' on the guest.

    It then lists all RPMs made available by all repositories defined in
    the .repo file but does not download them, serving as a "discovery-only"
    provider.
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

        # Cache for the list of RPMs discovered in the repositories.
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
        List all RPMs discovered from the repositories.

        .. note::

            The :py:meth:`fetch_contents` method must be called first to populate
            the artifact list from the guest.
        """
        if self._rpm_list is None:
            raise GeneralError(
                "RPM list not available. The 'fetch_contents' method must be "
                "called before accessing the artifacts property."
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
        Install the repositories on the guest and discover their packages.

        This method installs all repositories defined in the .repo file by
        downloading it and queries them to discover available packages.
        It does not download any RPMs itself and will return an empty list.
        """
        # 1. Create and install the repositories on the guest.
        repo = Repository(url=self.id, filename=self.repo_filename)
        repo.install(guest=guest, logger=self.logger)

        # 2. Populate the RPM list for discovery purposes by querying the repositories.
        self._rpm_list = repo.rpms

        # This provider does not download any artifacts, so return an empty list.
        return []
