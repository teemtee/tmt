"""
Koji Artifact Provider
"""

from collections.abc import Iterator
from typing import Any

from koji import ClientSession

import tmt.log
from tmt.steps.prepare.brand_new_allmighty_install.providers import (
    ArtifactInfo,
    ArtifactProvider,
    ArtifactType,
)
from tmt.steps.provision import Guest
from tmt.utils import GeneralError, Path


class KojiProvider(ArtifactProvider):
    API_URL = "https://koji.fedoraproject.org/kojihub"

    def __init__(self, logger: tmt.log.Logger, artifact_id: str):
        super().__init__(logger, artifact_id)
        self._session = self._initialize_session()

    def _initialize_session(self) -> ClientSession:
        """
        A koji session initialized via the koji.ClientSession function.
        api_url being the base URL for the koji instance
        """
        try:
            return ClientSession(self.API_URL)
        except Exception as error:
            raise GeneralError(f"Failed to initialize API session: {error}")

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
                yield ArtifactInfo(
                    id=int(self.artifact_id),
                    name=rpm.get('name'),
                    type=ArtifactType.RPM,
                    arch=rpm.get('arch'),
                    version=rpm.get('version'),
                    release=rpm.get('release'),
                    epoch=rpm.get('epoch'),
                    draft=rpm.get('draft'),
                    payloadhash=rpm.get('payloadhash'),
                    size=rpm.get('size'),
                    buildtime=rpm.get('buildtime'),
                    build_id=rpm.get('build_id'),
                    buildroot_id=rpm.get('buildroot_id'),
                )

    def _download_artifact(self, artifact: ArtifactInfo, guest: Guest, destination: Path) -> Path:
        # TODO: Implement actual download logic
        return destination
