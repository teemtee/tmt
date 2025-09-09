"""
Koji Artifact Provider
"""

from collections.abc import Iterator
from shlex import quote
from typing import Any

from koji import ClientSession

import tmt.log
from tmt.container import container
from tmt.steps.prepare.brand_new_allmighty_install.providers import (
    ArtifactInfo,
    ArtifactProvider,
)
from tmt.steps.provision import Guest
from tmt.utils import GeneralError, Path, ShellScript


@container
class KojiArtifactInfo(ArtifactInfo):
    PKG_URL = "https://kojipkgs.fedoraproject.org/packages/"  # For actual package downloads

    @property
    def name(self) -> str:
        """Get the RPM filename for the given RPM metadata."""
        return (
            f"{self._raw_artifact['name']}-"
            f"{self._raw_artifact['version']}-"
            f"{self._raw_artifact['release']}."
            f"{self._raw_artifact['arch']}.rpm"
        )

    @property
    def location(self) -> str:
        """Get the download URL for the given RPM metadata."""
        return (
            f"{self.PKG_URL}{self._raw_artifact['name']}/"
            f"{self._raw_artifact['version']}/"
            f"{self._raw_artifact['release']}/"
            f"{self._raw_artifact['arch']}/"
            f"{self.name}"
        )


class KojiProvider(ArtifactProvider[KojiArtifactInfo]):
    API_URL = "https://koji.fedoraproject.org/kojihub"  # For metadata

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
            raise GeneralError("Failed to initialize API session") from error

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
            raise GeneralError(f"API call {method} failed") from error

    def _parse_artifact_id(self, artifact_id: str) -> str:
        # Eg: 'koji.build:123456'
        prefix = "koji.build:"
        if not artifact_id.startswith(prefix):
            raise ValueError(f"Invalid artifact ID format: {artifact_id}")

        parsed = artifact_id[len(prefix) :]
        if not parsed.isdigit():
            raise ValueError(f"Invalid artifact ID format: {artifact_id}")
        return parsed

    def list_artifacts(self) -> Iterator[KojiArtifactInfo]:
        """
        TODO: Currently only lists rpms, extend to other types.
        See testing farm code for reference: listArtifacts, listTaskOutput etc.
        """
        if rpm_list := self._call_api('listBuildRPMs', int(self.artifact_id)):
            for rpm in rpm_list:
                yield KojiArtifactInfo(
                    _raw_artifact=rpm,
                    id=int(self.artifact_id),
                )

    def _download_artifact(
        self, artifact: KojiArtifactInfo, guest: Guest, destination: Path
    ) -> None:
        """
        Download the specified artifact to the given destination on the guest.

        :param artifact: The artifact to download
        :param guest: The guest where the artifact should be downloaded
        :param destination: The destination path on the guest
        """

        # Destination directory is guaranteed to exist, download the artifact
        guest.execute(
            ShellScript(
                f"curl -L -o {quote(str(destination))} {quote(artifact.location)}"
            ).to_shell_command(),
            silent=True,
        )
