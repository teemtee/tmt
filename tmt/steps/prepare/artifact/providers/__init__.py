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
from typing import TYPE_CHECKING, Any, Generic, Optional, TypeVar, cast, overload
from urllib.parse import urlparse

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

    def __init__(self, logger: tmt.log.Logger, name: str, content: str):
        self.logger = logger
        self.name = name
        self.content = content
        self._repo_ids = self._get_repo_ids()

    # The @overload decorator is used here to provide type hinting for multiple possible
    # call signatures of the 'create' class method. This helps static type checkers like
    # mypy understand that the method can be called in different ways (e.g., with 'url',
    # 'file_path', or 'content'), even though Python doesn't support true function overloading.
    # This specific overload defines the signature when creating a Repository from a URL.
    @overload
    @classmethod
    def create(
        cls,
        logger: tmt.log.Logger,
        *,
        name: Optional[str] = None,
        url: str,
        file_path: None = None,
        content: None = None,
    ) -> "Repository": ...

    # This @overload decorator defines the signature when creating a Repository from a file path.
    # It specifies the types for parameters when 'file_path' is provided,
    # and 'url' and 'content' are None.
    @overload
    @classmethod
    def create(
        cls,
        logger: tmt.log.Logger,
        *,
        name: Optional[str] = None,
        file_path: Path,
        url: None = None,
        content: None = None,
    ) -> "Repository": ...

    # This @overload decorator defines the signature when creating a Repository directly
    # from a content string. It specifies the types for parameters when 'content'
    # is provided, along with a required 'name' and 'url' and 'file_path' are None.
    @overload
    @classmethod
    def create(
        cls,
        logger: tmt.log.Logger,
        *,
        name: str,
        content: str,
        url: None = None,
        file_path: None = None,
    ) -> "Repository": ...

    @classmethod
    def create(
        cls,
        logger: tmt.log.Logger,
        *,
        name: Optional[str] = None,
        url: Optional[str] = None,
        file_path: Optional[Path] = None,
        content: Optional[str] = None,
    ) -> "Repository":
        """
        Create a Repository instance from one of the provided sources: URL, file path, or content.

        This method acts as a factory, delegating to specific from_* methods.
        Exactly one of 'url', 'file_path', or 'content' must be provided.

        :param logger: The logger instance to use.
        :param name: Optional name for the repository. It will be derived from the source.
        :param url: URL to fetch the repository content from.
        :param file_path: Local file path to read the repository content from.
        :param content: Direct string content of the repository.
        :returns: A Repository instance.
        :raises GeneralError: If invalid combination of arguments is provided.
        """
        provided = sum(x is not None for x in (url, file_path, content))
        if provided == 0:
            raise GeneralError(
                "At least one of 'url', 'file_path', or 'content' must be provided."
            )
        if provided > 1:
            raise GeneralError("Only one of 'url', 'file_path', or 'content' should be provided.")

        if url is not None:
            return cls.from_url(logger=logger, url=url, name=name)
        if file_path is not None:
            return cls.from_file_path(logger=logger, file_path=file_path, name=name)
        if content is not None:
            if name is None:
                raise GeneralError("Name must be provided when creating repository from content.")
            return cls.from_content(logger=logger, content=content, name=name)
        raise AssertionError("No source provided.")

    @classmethod
    def from_url(
        cls, logger: tmt.log.Logger, url: str, name: Optional[str] = None
    ) -> "Repository":
        """
        Create a Repository instance by fetching content from a URL.

        :param logger: The logger instance to use.
        :param url: The URL to fetch the repository content from.
        :param name: Optional name for the repository. If not provided, derived from the URL.
        :returns: A Repository instance.
        :raises GeneralError: If fetching or parsing fails.
        """
        try:
            with tmt.utils.retry_session() as session:
                response = session.get(url)
                response.raise_for_status()
                content = response.text
        except Exception as error:
            raise GeneralError(f"Failed to fetch repository content from '{url}'.") from error

        if name is None:
            parsed_url = urlparse(url)
            parsed_path = parsed_url.path.rstrip('/').split('/')[-1]
            name = parsed_path.replace('.repo', '')
            if not name:
                raise GeneralError(f"Could not derive repository name from URL '{url}'.")

        return cls(logger=logger, name=name, content=content)

    @classmethod
    def from_file_path(
        cls, logger: tmt.log.Logger, file_path: Path, name: Optional[str] = None
    ) -> "Repository":
        """
        Create a Repository instance by reading content from a local file path.

        :param logger: The logger instance to use.
        :param file_path: The local path to the repository file.
        :param name: Optional name for the repository. If not provided, derived from the file path.
        :returns: A Repository instance.
        :raises GeneralError: If reading the file fails.
        """
        try:
            content = file_path.read_text()
        except OSError as error:
            raise GeneralError(f"Failed to read repository file '{file_path}'.") from error

        if name is None:
            name = file_path.stem
            if not name:
                raise GeneralError(
                    f"Could not derive repository name from file path '{file_path}'."
                )

        return cls(logger=logger, name=name, content=content)

    @classmethod
    def from_content(cls, logger: tmt.log.Logger, content: str, name: str) -> "Repository":
        """
        Create a Repository instance directly from provided content string.

        :param logger: The logger instance to use.
        :param content: The string content of the repository.
        :param name: The name for the repository (required when using content).
        :returns: A Repository instance.
        """
        return cls(logger=logger, name=name, content=content)

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
