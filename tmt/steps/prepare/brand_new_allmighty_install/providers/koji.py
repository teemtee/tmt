"""
Koji Artifact Provider
"""

from collections.abc import Iterator

import tmt.log
from tmt.steps.prepare.brand_new_allmighty_install.providers import (
    ArtifactInfo,
    ArtifactProvider,
    ArtifactType,
)
from tmt.steps.provision import Guest
from tmt.utils import GeneralError, Path


class KojiProvider(ArtifactProvider):
    def __init__(self, logger: tmt.log.Logger, artifact_id: str):
        super().__init__(logger, artifact_id)

    def _parse_artifact_id(self, artifact_id: str) -> str:
        # Eg: 'koji.build:123456'
        if not artifact_id.startswith("koji.build:"):
            raise ValueError(f"Invalid artifact ID format: {artifact_id}")
        return artifact_id[len("koji.build:") :]

    def list_artifacts(self) -> Iterator[ArtifactInfo]:
        try:
            # artifacts = KojiSession.listRPMs(build_id) TODO: sort Koji session details
            yield ArtifactInfo(name="example.rpm", type=ArtifactType.RPM)
            yield ArtifactInfo(name="example.container", type=ArtifactType.CONTAINER)
        except Exception as err:
            raise GeneralError(f"Failed to list artifacts for build {self.artifact_id}: {err}")

    def _download_artifact(self, guest: Guest, destination: Path) -> Path:
        # TODO: Implement actual download logic
        return destination
