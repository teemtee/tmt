"""
Abstract base class for artifact providers.
"""

import enum
import re
from abc import ABC, abstractmethod

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

        Args:
            build_id (int): The ID of the build to retrieve information for.
        """
        pass

    @abstractmethod
    def list_artifacts(self, build_id: int) -> list[ArtifactInfo]:
        """
        List all available artifacts for a given build

        Args:
            build_id (int): The ID of the build to list artifacts for.
        """
        pass

    @abstractmethod
    def download_artifact(
        self,
        build_id: int,
        download_path: Path,
        exclude_patterns: list[str],
        skip_install: bool = True,
    ) -> list[Path]:
        """
        Download artifact from a build

        Args:
            build_id (int): The ID of the build to download the artifact from.
            download_path (str): The local path to save the downloaded artifact.
            exclude_patterns (list[str]): Patterns to exclude certain files from being downloaded.
            skip_install (bool, optional): Whether to skip installation of the artifact.
            Defaults to True.

        Returns:
            list[Path]: A list of paths to the downloaded artifacts.
        """
        pass

    @abstractmethod
    def install_artifact(self, artifact_path: Path) -> None:
        """
        Install the downloaded artifact.

        Args:
            artifact_path (Path): The path to the downloaded artifact to install.
        """
        pass

    def _filter_artifacts(self, build_id: int, exclude_patterns: list[str]) -> list[ArtifactInfo]:
        """
        Return the filtered list of artifacts for a given build.

        Args:
            build_id (int): The ID of the build to filter artifacts for.
            exclude_patterns (list[str]): The patterns to exclude.
        """

        if not exclude_patterns:
            return self.list_artifacts(build_id)

        compiled_patterns = [re.compile(pattern) for pattern in exclude_patterns]

        return [
            artifact
            for artifact in self.list_artifacts(build_id)
            if not any(pattern.search(artifact.name) for pattern in compiled_patterns)
        ]
