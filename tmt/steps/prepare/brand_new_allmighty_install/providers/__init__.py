"""
Abstract base class for artifact providers.
"""

import enum
from abc import ABC, abstractmethod
from collections.abc import Iterator
from re import Pattern
from shlex import quote
from typing import Any, Generic, TypeVar

import tmt.log
from tmt.container import container
from tmt.steps.provision import Guest
from tmt.utils import GeneralError, Path, ShellScript


class ArtifactType(enum.Enum):
    RPM = 'rpm'
    CONTAINER = 'container'
    UNKNOWN = 'unknown'


class DownloadError(GeneralError):
    """
    Raised when download fails.
    """


@container
class ArtifactInfo(ABC):
    _raw_artifact: dict[str, Any]
    id: int

    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def location(self) -> str:
        raise NotImplementedError

    def __str__(self) -> str:
        return self.name


ArtifactInfoT = TypeVar('ArtifactInfoT', bound=ArtifactInfo)


class ArtifactProvider(ABC, Generic[ArtifactInfoT]):
    def __init__(self, logger: tmt.log.Logger, artifact_id: str):
        self.logger = logger
        self.artifact_id = self._parse_artifact_id(artifact_id)

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
    def list_artifacts(self) -> Iterator[ArtifactInfoT]:
        """
        List all available artifacts for a given build
        """
        raise NotImplementedError

    @abstractmethod
    def _download_artifact(self, artifact: ArtifactInfoT, guest: Guest, destination: Path) -> None:
        """
        Action: Download a single artifact to the specified destination.

        :param guest: The guest where the artifact should be downloaded
        :param destination: Path where the artifact should be downloaded
        """
        raise NotImplementedError

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

        # Ensure download directory exists on guest (create only if missing)
        guest.execute(
            ShellScript(
                f"[ -d {quote(str(download_path))} ] || "
                f'{"sudo " if not guest.facts.is_superuser else ""}'
                f"mkdir -p {quote(str(download_path))}"
            ).to_shell_command(),
            silent=True,
        )

        downloaded_paths: list[Path] = []
        artifact_count = 0

        for artifact in self._filter_artifacts(exclude_patterns):
            local_path = download_path / str(artifact)
            self.logger.debug(f"Downloading {artifact} to {local_path}")

            try:
                self._download_artifact(artifact, guest, local_path)
                downloaded_paths.append(local_path)
                artifact_count += 1
                self.logger.info(f"Downloaded {artifact} to {local_path}")

            except DownloadError as err:
                # Warn about the failed download and move on
                self.logger.warning(f"Failed to download {artifact}: {err}")

            except Exception as err:
                raise GeneralError(f"Unexpected error downloading {artifact}") from err

        self.logger.info(f"Successfully downloaded {artifact_count} artifacts")
        return downloaded_paths

    def _filter_artifacts(self, exclude_patterns: list[Pattern[str]]) -> Iterator[ArtifactInfoT]:
        """
        Filter artifacts based on exclude patterns.

        :param exclude_patterns: The patterns to exclude.
        :yields: Artifacts that do not match any of the exclude patterns.
        """

        for artifact in self.list_artifacts():
            if not any(pattern.search(artifact.name) for pattern in exclude_patterns):
                yield artifact
