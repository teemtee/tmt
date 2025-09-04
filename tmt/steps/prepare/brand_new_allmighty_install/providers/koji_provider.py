"""
Koji Artifact Provider
"""

from collections.abc import Iterator

from koji import ClientSession

from tmt.steps.prepare.brand_new_allmighty_install.providers import (
    ArtifactInfo,
    ArtifactProvider,
    ArtifactType,
)
from tmt.steps.provision import Guest
from tmt.utils import GeneralError, Path


class KojiProvider(ArtifactProvider):
    def _initialize_session(self) -> ClientSession:
        """
        A koji session initialized via the koji.ClientSession function.
        api_url being the base URL for the koji instance
        """
        try:
            return ClientSession(self.api_url)
        except Exception as error:
            raise GeneralError(f"Failed to initialize API session: {error}")

    def _parse_artifact_id(self, artifact_id: str) -> str:
        # Eg: 'koji.build:123456'
        if not artifact_id.startswith("koji.build:"):
            raise ValueError(f"Invalid artifact ID format: {artifact_id}")
        return artifact_id[len("koji.build:") :]

    def list_artifacts(self) -> Iterator[ArtifactInfo]:
        """
        TODO: Currently only lists rpms, extend to other types.
        See testing farm code for reference: listArtifacts, listTaskOutput etc.
        """
        if rpm_list := self._call_api('listBuildRPMs', int(self.artifact_id)):
            for rpm in rpm_list:
                self.logger.debug(f"Found RPM: {rpm['nvr']} ({rpm['arch']})")
                yield ArtifactInfo(name=rpm['nvr'], type=ArtifactType.RPM, arch=rpm['arch'])

    def _download_artifact(self, artifact: ArtifactInfo, guest: Guest, destination: Path) -> Path:
        # TODO: Implement actual download logic
        return destination
