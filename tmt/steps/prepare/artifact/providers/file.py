import glob
import urllib.parse
from collections.abc import Sequence
from functools import cached_property
from shlex import quote
from typing import ClassVar, Optional

import tmt.log
import tmt.utils
from tmt.container import container
from tmt.steps.prepare.artifact.providers import (
    ArtifactInfo,
    ArtifactProvider,
    ArtifactProviderId,
    DownloadError,
    provides_artifact_provider,
)
from tmt.steps.provision import Guest


@container
class PackageAsFileArtifactInfo(ArtifactInfo):
    """
    Represents a single local or remote package file or directory.
    """

    _raw_artifact: str  # full path or URL

    @property
    def id(self) -> str:
        return tmt.utils.Path(self._raw_artifact).name

    @property
    def location(self) -> str:
        return self._raw_artifact


@provides_artifact_provider("file")  # type: ignore[arg-type]
class PackageAsFileArtifactProvider(ArtifactProvider[PackageAsFileArtifactInfo]):
    """
    Provider for preparing artifacts from local or remote package files.

    This provider can handle:
    - Glob patterns matching multiple package files.
    - Local package files specified by absolute or relative paths.
    - Remote package files accessible via URLs.
    - Directories containing package files (all packages in the directory are included).

    Example usage:

    .. code-block:: yaml

        prepare:
          - summary: package files
            how: artifact
            stage: prepare
            provide:
              - file:/tmp/*.rpm                    # Local glob
              - file:/build/specific.rpm           # Single file
              - file:https://example.com/pkg.rpm   # Remote URL
              - file:/path/to/packages/            # Directory
    """

    SUPPORTED_PREFIX: ClassVar[str] = "file"

    def __init__(self, raw_provider_id: str, logger: tmt.log.Logger):
        super().__init__(raw_provider_id, logger)
        source = raw_provider_id[len(f"{self.SUPPORTED_PREFIX}:") :]
        parsed = urllib.parse.urlparse(source)
        self._source = source
        self._is_url = parsed.scheme in ("http", "https")

    @classmethod
    def _extract_provider_id(cls, raw_provider_id: str) -> ArtifactProviderId:
        if not raw_provider_id.startswith(f"{cls.SUPPORTED_PREFIX}:"):
            raise ValueError(f"Unsupported provider id: '{raw_provider_id}'.")
        return ArtifactProviderId(raw_provider_id)

    @cached_property
    def artifacts(self) -> Sequence[PackageAsFileArtifactInfo]:
        artifacts: list[PackageAsFileArtifactInfo] = []
        seen_ids: set[str] = set()

        def add(info: PackageAsFileArtifactInfo) -> None:
            if info.id not in seen_ids:
                artifacts.append(info)
                seen_ids.add(info.id)
            else:
                self.logger.warning(
                    f"Duplicate artifact '{info.id}' found; ignoring duplicate entry."
                )

        if self._is_url:
            add(PackageAsFileArtifactInfo(_raw_artifact=self._source))
        # Everything else is treated as a glob pattern
        elif matched_files := glob.glob(self._source):
            for matched_file in sorted(matched_files):
                f = tmt.utils.Path(matched_file)
                if f.is_dir():  # find all .rpm files within it
                    for rpm_file in sorted(f.glob("*.rpm")):
                        add(PackageAsFileArtifactInfo(_raw_artifact=str(rpm_file)))
                elif f.is_file():
                    add(PackageAsFileArtifactInfo(_raw_artifact=str(f)))
        else:
            self.logger.warning(f"No files matched pattern: '{self._source}'.")

        if not artifacts:
            self.logger.warning(f"No artifacts found for source: '{self._source}'.")

        return artifacts

    def _download_artifact(
        self, artifact: PackageAsFileArtifactInfo, guest: Guest, destination: tmt.utils.Path
    ) -> None:
        try:
            if self._is_url:  # Remote file, download it
                guest.execute(
                    tmt.utils.ShellScript(
                        f"curl -L --fail -o {quote(str(destination))} {quote(artifact.location)}"
                    ),
                    silent=True,
                )
            else:  # Local file, push it to the guest
                guest.push(tmt.utils.Path(artifact.location), destination)
            self.logger.info(f"Successfully downloaded: '{artifact.id}'.")
        except Exception as error:
            raise DownloadError(f"Failed to download '{artifact}'.") from error
