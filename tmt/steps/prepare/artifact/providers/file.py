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
class PackageAsFileArtifactInfo(ArtifactInfo):
    """
    Represents a single local or remote package file or directory.
    """

    _raw_artifact: str  # full path or URL

    @property
    def id(self) -> str:
        return Path(self._raw_artifact).name

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
              - file:/path/to/packages/                # Directory
    """

    @classmethod
    def _extract_provider_id(cls, raw_provider_id: str) -> ArtifactProviderId:
        return ""

    @cached_property
    def artifacts(self) -> Sequence[PackageAsFileArtifactInfo]:
        return []

    def _download_artifact(
        self, artifact: PackageAsFileArtifactInfo, guest: Guest, destination: Path
    ) -> None:
        raise NotImplementedError
