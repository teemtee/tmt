"""
Abstract base class for artifact providers.
"""

import enum
from abc import ABC, abstractmethod
from collections.abc import Iterator
from re import Pattern
from typing import Any

from koji import ClientSession

import tmt.log
from tmt.container import container
from tmt.steps.provision import Guest
from tmt.utils import GeneralError, Path


class ArtifactType(enum.Enum):
    RPM = 'rpm'
    CONTAINER = 'container'
    UNKNOWN = 'unknown'


class DownloadError(GeneralError):
    """
    Raised when download fails.
    """


@container
class ArtifactInfo:  # TODO: Gather artifact metadata
    name: str
    type: ArtifactType
    arch: str

    def __str__(self) -> str:
        return self.name


class ArtifactProvider(ABC):
    def __init__(self, logger: tmt.log.Logger, artifact_id: str, api_url: str):
        self.logger = logger
        self.artifact_id = self._parse_artifact_id(artifact_id)
        self.api_url = api_url
        self._session: ClientSession = self._initialize_session()

    @abstractmethod
    def _initialize_session(self) -> ClientSession:
        """
        Initialize the API session.

        :return: The initialized API session
        :raises GeneralError: If session initialization fails
        """
        raise NotImplementedError

    @abstractmethod
    def _parse_artifact_id(self, artifact_id: str) -> str:
        """
        Parse and validate the artifact identifier.

        :param artifact_id: The raw artifact identifier
        :return: The parsed identifier specific to this provider
        :raises ValueError: If the artifact ID format is invalid
        """
        raise NotImplementedError

    @abstractmethod
    def list_artifacts(self) -> Iterator[ArtifactInfo]:
        """
        List all available artifacts for a given build

        :param build_id: The ID of the build to list artifacts for.
        """
        raise NotImplementedError

    @abstractmethod
    def _download_artifact(self, artifact: ArtifactInfo, guest: Guest, destination: Path) -> Path:
        """
        Download a single artifact to the specified destination.

        :param guest: The guest where the artifact should be downloaded
        :param destination: Path where the artifact should be downloaded
        :return: Path to the downloaded artifact
        """
        raise NotImplementedError

    def _call_api(self, method: str, *args: Any, **kwargs: Any) -> Any:
        """
        Generic API call method with error handling.

        :param method: API method name to call
        :param args: Positional arguments for the API call
        :param kwargs: Keyword arguments for the API call
        :return: API response
        :raises GeneralError: If API call fails
        """
        try:
            method_callable = getattr(self._session, method)
            return method_callable(*args, **kwargs)
        except Exception as error:
            raise GeneralError(f"API call {method} failed: {error}")

    def download_artifacts(
        self,
        guest: Guest,
        download_path: Path,
        exclude_patterns: list[Pattern[str]],
    ) -> list[Path]:
        """
        Download all artifacts to the specified destination.

        :param guest: The guest where the artifacts should be downloaded.
        :param download_path: The local path to save the downloaded artifact.
        :param exclude_patterns: Patterns to exclude certain files from being downloaded.
        :returns: A list of paths to the downloaded artifacts.
        :raises GeneralError: Unexpected errors outside the download process.
        :note: Errors during individual artifact downloads are
            caught, logged as warnings, and ignored.
        """
        self.logger.info(f"Downloading artifacts to {download_path!s}")
        downloaded_paths: list[Path] = []
        artifact_count = 0

        for artifact in self._filter_artifacts(exclude_patterns):
            local_path = download_path / str(artifact)
            self.logger.debug(f"Downloading {artifact} to {local_path}")

            try:
                downloaded_path = self._download_artifact(artifact, guest, local_path)
                downloaded_paths.append(downloaded_path)
                artifact_count += 1
                self.logger.info(f"Downloaded {artifact} to {downloaded_path}")

            except DownloadError as err:
                # Warn about the failed download and move on
                self.logger.warning(f"Failed to download {artifact}: {err}")

            except Exception as err:
                raise GeneralError(f"Unexpected error downloading {artifact}: {err}") from err

        self.logger.info(f"Successfully downloaded {artifact_count} artifacts")
        return downloaded_paths

    def _filter_artifacts(self, exclude_patterns: list[Pattern[str]]) -> Iterator[ArtifactInfo]:
        """
        Filter artifacts based on exclude patterns.

        :param build_id: The ID of the build to filter artifacts for.
        :param exclude_patterns: The patterns to exclude.
        :yields: Artifacts that do not match any of the exclude patterns.
        """

        for artifact in self.list_artifacts():
            if not any(pattern.search(artifact.name) for pattern in exclude_patterns):
                yield artifact
