"""
Abstract base class for artifact providers.
"""

from abc import ABC, abstractmethod
from collections.abc import Iterator
from re import Pattern
from shlex import quote
from typing import Generic, TypeVar

import tmt.log
import tmt.utils
from tmt.steps.prepare.artifact.providers.info import ArtifactInfo
from tmt.steps.provision import Guest


class DownloadError(tmt.utils.GeneralError):
    """
    Raised when download fails.
    """


ArtifactInfoT = TypeVar('ArtifactInfoT', bound=ArtifactInfo)


class ArtifactProvider(ABC, Generic[ArtifactInfoT]):
    """
    Abstract provider of artifacts
    e.g. KojiArtifactProvider, BrewArtifactProvider, RepoFileArtifactProvider.

    Each provider must implement:
        - Parsing and validating the artifact ID
        - Listing available artifacts
        - Downloading a single artifact
    The base class provides:
        - Downloading all artifacts with filtering

    """

    def __init__(self, logger: tmt.log.Logger, artifact_id: str):
        self.logger = logger
        self.artifact_id = self._parse_artifact_id(
            artifact_id
        )  # Identifier for the source, e.g. 'koji.build:12345', URL for repository

    @abstractmethod
    def _parse_artifact_id(self, artifact_id: str) -> str:
        """
        Parse and validate the artifact identifier.

        :param id: Identifier for the source
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
    def _download_artifact(
        self, artifact: ArtifactInfoT, guest: Guest, destination: tmt.utils.Path
    ) -> None:
        """
        Action: Download a single artifact to the specified destination.

        :param guest: The guest where the artifact should be downloaded
        :param destination: Path where the artifact should be downloaded
        """
        raise NotImplementedError

    def download_artifacts(
        self,
        guest: Guest,
        download_path: tmt.utils.Path,
        exclude_patterns: list[Pattern[str]],
    ) -> list[tmt.utils.Path]:
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
        self.logger.info(f"Downloading artifacts to '{download_path!s}'.")

        # Ensure download directory exists on guest (create only if missing)
        guest.execute(
            tmt.utils.ShellScript(
                f"[ -d {quote(str(download_path))} ] || "
                f'{"sudo " if not guest.facts.is_superuser else ""}'
                f"mkdir -p {quote(str(download_path))}"
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

        :param exclude_patterns: The patterns to exclude.
        :yields: Artifacts that do not match any of the exclude patterns.
        """

        for artifact in self.list_artifacts():
            if not any(pattern.search(artifact.id) for pattern in exclude_patterns):
                yield artifact
