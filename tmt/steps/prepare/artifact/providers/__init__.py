"""
Abstract base class for artifact providers.
"""

import configparser
import functools
from abc import ABC, abstractmethod
from collections.abc import Iterator, Sequence
from functools import cached_property
from re import Pattern
from shlex import quote
from typing import TYPE_CHECKING, Any, Generic, Optional, TypeVar, cast
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


class Repository(ABC):
    """A class to represent a dnf/yum software repository."""

    def __init__(self, logger: tmt.log.Logger, name: Optional[str] = None):
        self.logger = logger
        self._name = name
        _ = self.name  # Force name derivation
        self._repo_ids = self._get_repo_ids()

    @classmethod
    def create(
        cls,
        logger: tmt.log.Logger,
        name: Optional[str] = None,
        url: Optional[str] = None,
        file_path: Optional[Path] = None,
        content: Optional[str] = None,
    ) -> "Repository":
        provided = sum(x is not None for x in (url, file_path, content))
        if provided == 0:
            raise GeneralError(
                "At least one of 'url', 'file_path', or 'content' must be provided."
            )
        if provided > 1:
            raise GeneralError("Only one of 'url', 'file_path', or 'content' should be provided.")

        if url is not None:
            return UrlRepository(logger=logger, url=url, name=name)
        if file_path is not None:
            return FileRepository(logger=logger, file_path=file_path, name=name)
        if content is not None:
            if name is None:
                raise GeneralError("Name must be provided when creating repository from content.")
            return ContentRepository(logger=logger, content=content, name=name)
        raise GeneralError("No source provided.")  # Unreachable

    @cached_property
    @abstractmethod
    def content(self) -> str:
        raise NotImplementedError

    @cached_property
    def name(self) -> str:
        if self._name:
            return self._name
        return self._derive_name()

    @abstractmethod
    def _derive_name(self) -> str:
        raise NotImplementedError

    def _get_repo_ids(self) -> list[str]:
        content = self.content
        config = configparser.ConfigParser()
        try:
            config.read_string(content)
            sections = config.sections()
            if not sections:
                raise GeneralError(
                    f"No repository sections found in the content for '{self.name}'."
                )
            return sections
        except configparser.MissingSectionHeaderError:
            raise GeneralError(f"No repository sections found in the content for '{self.name}'.")
        except configparser.Error as error:
            raise GeneralError(
                f"Failed to parse the content of repository '{self.name}'. "
                "The .repo file may be malformed."
            ) from error

    @property
    def repo_ids(self) -> list[str]:
        return self._repo_ids

    @property
    def filename(self) -> str:
        return f"{self.name}.repo"


class UrlRepository(Repository):
    def __init__(self, logger: tmt.log.Logger, url: str, name: Optional[str] = None):
        self.url = url
        super().__init__(logger, name)

    @cached_property
    def content(self) -> str:
        try:
            with tmt.utils.retry_session() as session:
                response = session.get(self.url)
                response.raise_for_status()
                return response.text
        except Exception as error:
            raise GeneralError(f"Failed to fetch repository content from '{self.url}'.") from error

    def _derive_name(self) -> str:
        parsed_url = urlparse(self.url)
        parsed_path = parsed_url.path.rstrip('/').split('/')[-1]
        name = parsed_path.replace('.repo', '')
        if not name:
            raise GeneralError(f"Could not derive repository name from URL '{self.url}'.")
        return name


class FileRepository(Repository):
    def __init__(self, logger: tmt.log.Logger, file_path: Path, name: Optional[str] = None):
        self._file_path = file_path
        super().__init__(logger, name)

    @cached_property
    def content(self) -> str:
        try:
            return self._file_path.read_text()
        except OSError as error:
            raise GeneralError(f"Failed to read repository file '{self._file_path}'.") from error

    def _derive_name(self) -> str:
        name = self._file_path.stem
        if not name:
            raise GeneralError(
                f"Could not derive repository name from file path '{self._file_path}'."
            )
        return name


class ContentRepository(Repository):
    def __init__(self, logger: tmt.log.Logger, content: str, name: str):
        self._content = content
        super().__init__(logger, name)

    @cached_property
    def content(self) -> str:
        return self._content

    def _derive_name(self) -> str:
        raise GeneralError("Name must be provided when creating repository from content.")


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
