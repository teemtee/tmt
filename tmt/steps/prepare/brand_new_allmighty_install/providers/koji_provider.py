"""
Koji Artifact Provider
"""

from collections.abc import Iterator
from shlex import quote
from typing import Any

from koji import ClientSession

import tmt.log
from tmt.steps.prepare.brand_new_allmighty_install.providers import (
    ArtifactInfo,
    ArtifactProvider,
)
from tmt.steps.provision import Guest
from tmt.utils import GeneralError, Path, ShellScript


class KojiProvider(ArtifactProvider):
    API_URL = "https://koji.fedoraproject.org/kojihub"  # For metadata
    PKG_URL = "https://kojipkgs.fedoraproject.org/packages/"  # For actual package downloads

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

    def _get_rpm_filename(self, rpm: dict[str, Any]) -> str:
        """
        Get the RPM filename for the given RPM metadata.

        :param rpm: The RPM metadata to get the filename for
        :return: The RPM filename
        """
        return f"{rpm['name']}-{rpm['version']}-{rpm['release']}.{rpm['arch']}.rpm"

    def _get_download_url(self, rpm: dict[str, Any]) -> str:
        """
        Get the download URL for the given RPM metadata.

        :param rpm: The RPM metadata to get the download URL for
        :return: The download URL
        """
        return (
            f"{self.PKG_URL}{rpm['name']}/"
            f"{rpm['version']}/"
            f"{rpm['release']}/"
            f"{rpm['arch']}/"
            f"{self._get_rpm_filename(rpm)}"
        )

    def list_artifacts(self) -> Iterator[ArtifactInfo]:
        """
        TODO: Currently only lists rpms, extend to other types.
        See testing farm code for reference: listArtifacts, listTaskOutput etc.
        """
        if rpm_list := self._call_api('listBuildRPMs', int(self.artifact_id)):
            for rpm in rpm_list:
                rpm_filename = self._get_rpm_filename(rpm)
                self.logger.debug(f"Found RPM: {rpm_filename}")
                yield ArtifactInfo(
                    id=int(self.artifact_id),
                    name=rpm_filename,
                    location=self._get_download_url(rpm),
                )

    def _download_artifact(self, artifact: ArtifactInfo, guest: Guest, destination: Path) -> Path:
        """
        Download the specified artifact to the given destination on the guest.

        :param artifact: The artifact to download
        :param guest: The guest where the artifact should be downloaded
        :param destination: The destination path on the guest
        :return: The path to the downloaded artifact on the guest
        :raises GeneralError: If download fails
        """

        dest_dir: Path = destination.parent

        # Create the destination directory if it doesn't exist and download the artifact
        guest.execute(
            ShellScript(
                f"[ -d {quote(str(dest_dir))} ] || "
                f'{"sudo " if not guest.facts.is_superuser else ""}'
                f"mkdir -p {quote(str(dest_dir))}; "
                f"cd {quote(str(dest_dir))} && "
                f"curl -LOf {quote(artifact.location)}"
            ).to_shell_command(),
            silent=True,
        )

        return destination / str(artifact)
