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
from tmt.utils import GeneralError, Path, ShellScript, retry


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
        """

        self.logger = logger
        self.guest = guest
        self.filepath = Path("/etc/yum.repos.d") / self.filename
        script = ShellScript(
            f"{guest.facts.sudo_prefix} curl -L --fail -o {quote(str(self.filepath))} "
            f"{quote(self.url)}"
        )
        logger.info("", f"Executing curl command: {script}")

        # Retry the curl command
        try:
            retry(
                func=lambda: guest.execute(script),
                attempts=3,
                interval=5,
                label=f"download .repo file from '{self.url}'",
                logger=logger,
            )
        except Exception as error:
            last_error = error.causes[-1] if hasattr(error, 'causes') and error.causes else error
            logger.info("", f"Download failed after retries: {last_error!s}")
            raise DownloadError(
                f"Failed to download repository file from '{self.url}' to "
                f"'{self.filepath}': {last_error!s}"
            ) from last_error

        # Get the repo file content directly from the guest's stdout
        try:
            result = guest.execute(ShellScript(f'cat {self.filepath}'))
            content = result.stdout

            if content is None:
                raise GeneralError("Command did not return any output.")
            
            content = content.strip()
            if not content:
                raise GeneralError(f"Repository file '{self.filepath}' is empty or not readable on guest.")

            logger.info("", f"Guest .repo file content:\n{content}")

        except GeneralError as error:
            logger.warning(
                f"Could not read the repo file '{self.filepath}' from the guest: {error!s}")
            raise

        # Parse the content directly from the string
        parser = configparser.ConfigParser(
            strict=False,
            allow_no_value=True,
            delimiters=('=', ':'),
        )
        try:
            parser.read_string(content)
            logger.info("", "Parsed .repo file successfully")
        except configparser.Error as error:
            logger.info("", f"Failed to parse .repo file content: {error!s}")
            raise GeneralError(
                f"Failed to parse .repo file from guest path '{self.filepath}' as INI: {error!s}"
            ) from error

        # Get all section names as repository IDs
        self.names = parser.sections()
        logger.info("", f"Repository IDs found: {self.names}")
        if not self.names:
            logger.info("", "No repository sections found in .repo file")
            raise GeneralError(
                f"No repository sections found in .repo file '{self.filepath}'."
            )

    @property
    def rpms(self) -> list[RpmArtifactInfo]:
        """
        List all packages available in the repositories.

        Queries all repositories defined in the .repo file (by their IDs) using
        the dnf or yum package manager to discover available packages.
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

        try:
            # --- MODIFICATION START ---
            # Choose the correct repoquery command based on the guest's package manager.
            # Note: For yum, the 'yum-utils' package must be installed on the guest.
            if self.guest.facts.package_manager == 'dnf':
                script = ShellScript(
                    f"dnf repoquery --refresh --disablerepo='*' --enablerepo={repo_ids} "
                    f"--queryformat {qf}"
                )
            elif self.guest.facts.package_manager == 'yum':
                # CentOS 7 uses the 'repoquery' command from the 'yum-utils' package.
                script = ShellScript(
                    f"repoquery --disablerepo='*' --enablerepo={repo_ids} "
                    f"--queryformat {qf}"
                )
            else:
                raise GeneralError(
                    f"Unsupported package manager: '{self.guest.facts.package_manager}'")
            # --- MODIFICATION END ---

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
                # --- MODIFICATION START ---
                # Handle different null epoch formats: dnf uses '(none)', yum uses '0'.
                if epoch == "(none)" or epoch == "0":
                    epoch = ""
                    nvr = f"{name}-{version}-{release}"
                else:
                    nvr = f"{name}-{epoch}:{version}-{release}"
                # --- MODIFICATION END ---

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
        for r in self._rpms:
            self.logger.info("rpmi ",r)
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