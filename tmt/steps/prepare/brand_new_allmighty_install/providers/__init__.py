"""
Abstract base class for artifact providers.
"""

import enum
from abc import ABC, abstractmethod
from collections.abc import Iterator
from re import Pattern

import tmt.log
from tmt.container import container
from tmt.utils import Path


class ArtifactType(enum.Enum):
    RPM = 'rpm'
    CONTAINER = 'container'
    UNKNOWN = 'unknown'


@container
class BuildInfo:  # TODO: Gather build metadata
    id: int


@container
class ArtifactInfo:  # TODO: Gather artifact metadata
    name: str
    type: ArtifactType


class ArtifactProvider(ABC):
    def __init__(self, logger: tmt.log.Logger):
        self.logger = logger

    @abstractmethod
    def get_build(self, build_id: int) -> BuildInfo:
        """
        Retrieve build information by ID

        :param build_id: The ID of the build to retrieve information for.
        """
        pass

    @abstractmethod
    def list_artifacts(self, build_id: int) -> Iterator[ArtifactInfo]:
        """
        List all available artifacts for a given build

        :param build_id: The ID of the build to list artifacts for.
        """
        pass

    @abstractmethod
    def download_artifact(
        self,
        build_id: int,
        download_path: Path,
        exclude_patterns: list[Pattern[str]],
        skip_install: bool = True,
    ) -> list[Path]:
        """
        Download artifact from a build


        :param build_id: The ID of the build to download the artifact from.
        :param download_path: The local path to save the downloaded artifact.
        :param exclude_patterns: Patterns to exclude certain files from being downloaded.
        :param skip_install: Whether to skip installation of the artifact.
            Defaults to True.
        :returns: A list of paths to the downloaded artifacts.
        """
        pass

    @abstractmethod
    def install_artifact(self, artifact_path: Path) -> None:
        """
        Install the downloaded artifact.

        :param artifact_path: The path to the downloaded artifact to install.
        """
        pass

    def _filter_artifacts(
        self, build_id: int, exclude_patterns: list[Pattern[str]]
    ) -> Iterator[ArtifactInfo]:
        """
        Return the filtered list of artifacts for a given build.

        :param build_id: The ID of the build to filter artifacts for.
        :param exclude_patterns: The patterns to exclude.
        """

        return (
            artifact
            for artifact in self.list_artifacts(build_id)
            if not any(pattern.search(artifact.name) for pattern in exclude_patterns)
        )
