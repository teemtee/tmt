"""
Abstract base class for artifact providers.
"""

import configparser
import functools
import hashlib
from abc import ABC, abstractmethod
from collections.abc import Iterator, Sequence
from functools import cached_property
from re import Pattern
from shlex import quote
from typing import TYPE_CHECKING, Any, Generic, Optional, TypeVar
from urllib.parse import urlparse

import tmt
import tmt.log
import tmt.utils
from tmt._compat.typing import TypeAlias
from tmt.container import container
from tmt.plugins import PluginRegistry
from tmt.steps.provision import Guest
from tmt.utils import GeneralError, Path, ShellScript, retry


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
    """A class to represent a dnf/yum software repository."""

    def __init__(
        self,
        logger: tmt.log.Logger,
        name: Optional[str] = None,
        url: Optional[str] = None,
        file_path: Optional[Path] = None,
        content: Optional[str] = None,
    ):
        self.logger = logger
        self._provided_name = name
        self._provided_url = url
        self._provided_file_path = file_path
        self._provided_content = content

        if not self.content:
            raise tmt.utils.GeneralError(
                "Repository content could not be loaded. "
                "You must provide a 'url', 'file_path', or 'content'."
            )

        if not self.repo_ids:
            self.logger.warning(
                f"No repository sections (e.g., [my-repo]) found in the content for '{self.name}'."
            )

    @functools.cached_property
    def id(self) -> str:
        """A deterministic ID based on the repository's definition."""
        hasher = hashlib.sha256()
        source_data = ""

        # Use the first available source for the hash for true determinism
        if self._provided_url:
            source_data = self._provided_url
        elif self._provided_file_path:
            source_data = str(self._provided_file_path.resolve())
        elif self._provided_content:
            # Normalize whitespace to ensure content hash is consistent
            source_data = "\n".join(
                line.strip() for line in self._provided_content.strip().splitlines()
            )

        hasher.update(source_data.encode('utf-8'))
        return hasher.hexdigest()

    @functools.cached_property
    def name(self) -> str:
        """Determine the repository name, using a provided name or deriving it."""
        if self._provided_name:
            return self._provided_name
        if self._provided_url:
            # Use the last path segment from the URL
            parsed_path = urlparse(self._provided_url).path
            return parsed_path.rstrip('/').split('/')[-1].replace('.repo', '')
        if self._provided_file_path:
            # Derive from local filename
            return self._provided_file_path.name.replace('.repo', '')
        # Fallback to a name derived from the unique ID
        return f"repo-{self.id[:8]}"

    @functools.cached_property
    def content(self) -> Optional[str]:
        """Loads the repository content from the provided source."""
        if self._provided_content:
            return self._provided_content
        if self._provided_url:
            try:
                with tmt.utils.retry_session() as session:
                    response = session.get(self._provided_url)
                    response.raise_for_status()
                    return response.text
            except Exception as error:
                raise tmt.utils.GeneralError(
                    f"Failed to fetch repository content from '{self._provided_url}'."
                ) from error
        if self._provided_file_path:
            try:
                return self._provided_file_path.read_text()
            except OSError as error:
                raise tmt.utils.GeneralError(
                    f"Failed to read repository file '{self._provided_file_path}'."
                ) from error
        return None

    @functools.cached_property
    def repo_ids(self) -> list[str]:
        """Parses the .repo content to extract repository IDs using configparser."""
        if not self.content:
            return []
        config = configparser.ConfigParser()
        try:
            config.read_string(self.content)
            return config.sections()
        except configparser.Error as error:
            raise tmt.utils.GeneralError(
                f"Failed to parse the content of repository '{self.name}'. "
                "The .repo file may be malformed."
            ) from error

    @property
    def filename(self) -> str:
        """The filename for the repository file on the guest."""
        return f"{self.name}.repo"


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
