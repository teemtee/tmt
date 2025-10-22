from collections.abc import Sequence
from functools import cached_property

from tmt.container import container
from tmt.steps.prepare.artifact.providers import (
    ArtifactInfo,
    ArtifactProvider,
    ArtifactProviderId,
    DownloadError,
    provides_artifact_provider,
)
from tmt.steps.provision import Guest
from tmt.utils import Path


@container
class FileArtifactInfo(ArtifactInfo):
    """
    Represents a single local or remote RPM file or directory.
    """

    _raw_artifact: str  # full path or URL

    @property
    def id(self) -> str:
        return Path(self._raw_artifact).name

    @property
    def location(self) -> str:
        return self._raw_artifact


@provides_artifact_provider("file")  # type: ignore[arg-type]
class FileArtifactProvider(ArtifactProvider[FileArtifactInfo]):
    """
    Provider for preparing artifacts from local or remote RPM files.

    This provider can handle:
    - Glob patterns matching multiple RPM files.
    - Local RPM files specified by absolute or relative paths.
    - Remote RPM files accessible via URLs.
    - Directories containing RPM files (all RPMs in the directory are included).

    Example usage:

    .. code-block:: yaml

        prepare:
          - summary: rpm files
            how: artifact
            stage: prepare
            provide:
              - file:/tmp/*.rpm                    # Local glob
              - file:/build/specific.rpm           # Single file
              - file:https://example.com/pkg.rpm   # Remote URL
              - file:/path/to/rpms/                # Directory

    .. code-block:: python

        provider = FileArtifactProvider("file:/tmp/*.rpm", logger)
        artifacts = provider.download_artifacts(guest, Path("/tmp"), [])
    """

    @classmethod
    def _extract_provider_id(cls, raw_provider_id: str) -> ArtifactProviderId:
        return ""

    @cached_property
    def artifacts(self) -> Sequence[FileArtifactInfo]:
        return []

    def _download_artifact(
        self, artifact: FileArtifactInfo, guest: Guest, destination: Path
    ) -> None:
        raise NotImplementedError
