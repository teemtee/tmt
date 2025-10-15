"""
Abstract base class for artifact providers.
"""

import configparser
from abc import ABC, abstractmethod
from collections.abc import Iterator, Sequence
from functools import cached_property
from re import Pattern
from shlex import quote
from typing import TYPE_CHECKING, Any, Generic, Optional, TypeVar

import tmt.log
import tmt.utils
from tmt._compat.typing import TypeAlias
from tmt.container import container
from tmt.plugins import PluginRegistry
from tmt.steps.provision import Guest
from tmt.utils import GeneralError, Path, ShellScript, retry

# This avoids a circular import with koji.py, which needs ArtifactInfo.
# We only need the type for hinting, not for runtime logic in this file's top level.
if TYPE_CHECKING:
    from tmt.steps.prepare.artifact.providers.koji import RpmArtifactInfo


class DownloadError(tmt.utils.GeneralError):
    """
    Raised when download fails.
    """


@container
class ArtifactInfo(ABC):
    """
    Information about a single artifact, e.g. a package.
    """

    _raw_artifact: Any

    @property
    @abstractmethod
    def id(self) -> str:
        """
        A unique identifier of the artifact.
        """

        raise NotImplementedError

    @property
    @abstractmethod
    def location(self) -> str:
        raise NotImplementedError

    def __str__(self) -> str:
        return self.id


#: A type of an artifact provider identifier.
ArtifactProviderId: TypeAlias = str

#: A type variable representing subclasses of :py:class:`ArtifactInfo`
#: containers.
ArtifactInfoT = TypeVar('ArtifactInfoT', bound=ArtifactInfo)


class ArtifactProvider(ABC, Generic[ArtifactInfoT]):
    """
    Base class for artifact providers.

    Each provider must implement:

    * parsing and validating the artifact ID,
    * listing available artifacts,
    * downloading a single given artifact.
    """

    #: Identifier of this artifact provider. It is valid and unique
    #: in the domain of this provider. ``koji.build:12345``. URL for a
    #: repository, and so on.
    id: ArtifactProviderId

    def __init__(self, raw_provider_id: str, logger: tmt.log.Logger):
        self.logger = logger

        self.id = self._extract_provider_id(raw_provider_id)

    @classmethod
    @abstractmethod
    def _extract_provider_id(cls, raw_provider_id: str) -> ArtifactProviderId:
        """
        Parse and validate the artifact provider identifier.

        :param raw_provider_id: artifact provider identifier to parse and validate.
        :returns: parsed identifier specific to this provider class.
        :raises ValueError: when the artifact provider identifier is invalid.
        """

        raise NotImplementedError

    @cached_property
    @abstractmethod
    def artifacts(self) -> Sequence[ArtifactInfoT]:
        """
        Collect all artifacts available from this provider.

        The method is left for derived classes to implement with respect
        to the actual artifact provider they implement. The list of
        artifacts will be cached, and is treated as read-only.

        :returns: a list of provided artifacts.
        """

        raise NotImplementedError

    @abstractmethod
    def _download_artifact(
        self, artifact: ArtifactInfoT, guest: Guest, destination: tmt.utils.Path
    ) -> None:
        """
        Download a single artifact to the specified destination on a given guest.

        :param guest: the guest on which the artifact should be downloaded.
        :param destination: path into which the artifact should be downloaded.
        """

        raise NotImplementedError

    def fetch_contents(
        self,
        guest: Guest,
        download_path: tmt.utils.Path,
        exclude_patterns: Optional[list[Pattern[str]]] = None,
    ) -> list[tmt.utils.Path]:
        """
        Fetch all artifacts to the specified destination.

        :param guest: the guest on which the artifact should be
            downloaded.
        :param download_path: path into which the artifact should be
            downloaded.
        :param exclude_patterns: if set, artifacts whose names match any
            of the given regular expressions would not be downloaded.
        :returns: a list of paths to the downloaded artifacts.
        :raises GeneralError: Unexpected errors outside the download process.
        :note: Errors during individual artifact downloads are
            caught, logged as warnings, and ignored.
        """

        self.logger.info(f"Downloading artifacts to '{download_path!s}'.")

        exclude_patterns = exclude_patterns or []

        # Ensure download directory exists on guest (create only if missing)
        guest.execute(
            tmt.utils.ShellScript(
                f"[ -d {quote(str(download_path))} ] || "
                f"{guest.facts.sudo_prefix} mkdir -p {quote(str(download_path))}"
            ),
            silent=True,
        )

        downloaded_paths: list[tmt.utils.Path] = []

        for artifact in self._filter_artifacts(exclude_patterns):
            local_path = download_path / str(artifact)
            self.logger.debug(f"Downloading '{artifact}' to '{local_path}'.")

            try:
                self._download_artifact(artifact, guest, local_path)
                downloaded_paths.append(local_path)
                self.logger.info(f"Downloaded '{artifact}' to '{local_path}'.")

            except DownloadError as error:
                # Warn about the failed download and move on
                tmt.utils.show_exception_as_warning(
                    exception=error,
                    message=f"Failed to download '{artifact}'.",
                    include_logfiles=True,
                    logger=self.logger,
                )

            except Exception as error:
                raise tmt.utils.GeneralError(
                    f"Unexpected error downloading '{artifact}'."
                ) from error

        self.logger.info(f"Successfully downloaded '{len(downloaded_paths)}' artifacts.")
        return downloaded_paths

    def _filter_artifacts(self, exclude_patterns: list[Pattern[str]]) -> Iterator[ArtifactInfoT]:
        """
        Filter artifacts based on exclude patterns.

        :param exclude_patterns: artifact whose name matches any of
            these patterns would be skipped.
        :yields: artifacts that satisfy the filtering.
        """

        for artifact in self.artifacts:
            if not any(pattern.search(artifact.id) for pattern in exclude_patterns):
                yield artifact


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
                raise GeneralError(
                    f"Repository file '{self.filepath}' is empty or not readable on guest."
                )

            logger.info("", f"Guest .repo file content:\n{content}")

        except GeneralError as error:
            logger.warning(
                f"Could not read the repo file '{self.filepath}' from the guest: {error!s}"
            )
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
            raise GeneralError(f"No repository sections found in .repo file '{self.filepath}'.")

    @property
    def rpms(self) -> list['RpmArtifactInfo']:
        """
        List all packages available in the repositories.

        Queries all repositories defined in the .repo file (by their IDs) using
        the dnf or yum package manager to discover available packages.
        :return: A list of RpmArtifactInfo objects for each found package.
        :raises GeneralError: If no repositories have been installed or if the package query fails.
        """
        # Moved from top-level to here to prevent circular import
        from tmt.steps.prepare.artifact.providers.koji import RpmArtifactInfo

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
                    f"repoquery --disablerepo='*' --enablerepo={repo_ids} --queryformat {qf}"
                )
            else:
                raise GeneralError(
                    f"Unsupported package manager: '{self.guest.facts.package_manager}'"
                )
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
            self.logger.info("rpmi ", r)
        return self._rpms


_PROVIDER_REGISTRY: PluginRegistry[type[ArtifactProvider[ArtifactInfo]]] = PluginRegistry(
    'prepare.artifact.providers'
)


def _register_hints(
    plugin_id: str,
    plugin_class: type[ArtifactProvider[ArtifactInfoT]],
    hints: Optional[dict[str, str]] = None,
) -> None:
    for hint_id, hint in (hints or {}).items():
        tmt.utils.hints.register_hint(f'artifact-provider/{plugin_id}/{hint_id}', hint)


provides_artifact_provider = _PROVIDER_REGISTRY.create_decorator(on_register=_register_hints)
