"""
Koji Artifact Provider
"""

import tmt.log
from tmt.steps.prepare.brand_new_allmighty_install.providers import (
    ArtifactInfo,
    ArtifactProvider,
    ArtifactType,
    BuildInfo,
)
from tmt.utils import GeneralError, Path


class KojiProvider(ArtifactProvider):
    def __init__(self, logger: tmt.log.Logger):
        super().__init__(logger)

    def get_build(self, build_id: int) -> BuildInfo:
        try:
            # build_info = KojiSession.getBuild(build_id) TODO: sort Koji session details
            return BuildInfo(build_id)
        except Exception as err:
            """
            TODO: Do a better job at handling different Exceptions
            => BuildError, BuildNotFoundError...
            """
            raise GeneralError(f"Failed to get build info for build ID {build_id}: {err}")

    def list_artifacts(self, build_id: int) -> list[ArtifactInfo]:
        try:
            # artifacts = KojiSession.listRPMs(build_id) TODO: sort Koji session details
            return [
                ArtifactInfo(name="example.rpm", type=ArtifactType.RPM),
                ArtifactInfo(name="example.container", type=ArtifactType.CONTAINER),
            ]
        except Exception as err:
            raise GeneralError(f"Failed to list artifacts for build ID {build_id}: {err}")

    def download_artifact(
        self,
        build_id: int,
        download_path: Path,
        exclude_patterns: list[str],
        skip_install: bool = True,
    ) -> list[Path]:
        self.logger.info(f"Downloading artifacts to {download_path!s}")
        artifacts = self.list_artifacts(build_id)
        downloaded_paths: list[Path] = []

        for artifact in artifacts:
            local_path = Path.joinpath(download_path, artifact.name)
            self.logger.debug(f"Downloading {artifact.name} to {local_path!s}")
            # TODO: Implement actual download logic
            downloaded_paths.append(local_path)
            self.logger.info(f"Downloaded {artifact.name}")

        self.logger.info(f"Successfully downloaded {len(downloaded_paths)} artifacts")
        return downloaded_paths

    def install_artifact(self, artifact_path: Path) -> None:
        raise NotImplementedError("Artifact installation is not supported.")
