"""
Abstract base class for artifact providers.
"""

from abc import ABC, abstractmethod
from collections.abc import Iterator
from re import Pattern
from shlex import quote
from typing import Any, Generic, Optional, TypeVar

import tmt.log
import tmt.utils
from tmt._compat.typing import TypeAlias
from tmt.container import container
from tmt.plugins import PluginRegistry
from tmt.steps.provision import Guest


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

    @abstractmethod
    def list_artifacts(self) -> Iterator[ArtifactInfoT]:
        """
        List all artifacts available from this provider.
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
    ) -> Iterator[tmt.utils.Path]:
        """
        Fetch all artifacts to the specified destination.

        :param guest: the guest on which the artifact should be
            downloaded.
        :param download_path: path into which the artifact should be
            downloaded.
        :param exclude_patterns: if set, artifacts whose names match any
            of the given regular expressions would not be downloaded.
        :yields: paths to the successfully downloaded artifacts.
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
                f'{"sudo " if not guest.facts.is_superuser else ""}'
                f"mkdir -p {quote(str(download_path))}"
            ),
            silent=True,
        )

        downloaded_count = 0

        for artifact in self._filter_artifacts(exclude_patterns):
            local_path = download_path / str(artifact)
            self.logger.debug(f"Downloading '{artifact}' to '{local_path}'.")

            try:
                self._download_artifact(artifact, guest, local_path)
                downloaded_count += 1
                self.logger.info(f"Downloaded '{artifact}' to '{local_path}'.")
                yield local_path
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

        self.logger.info(f"Successfully downloaded '{downloaded_count}' artifacts.")

    def _filter_artifacts(self, exclude_patterns: list[Pattern[str]]) -> Iterator[ArtifactInfoT]:
        """
        Filter artifacts based on exclude patterns.

        :param exclude_patterns: artifact whose name matches any of
            these patterns would be skipped.
        :yields: artifacts that satisfy the filtering.
        """

        for artifact in self.list_artifacts():
            if not any(pattern.search(artifact.id) for pattern in exclude_patterns):
                yield artifact


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
