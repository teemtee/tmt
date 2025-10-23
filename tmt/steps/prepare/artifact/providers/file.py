import glob
import urllib.parse
from collections.abc import Sequence
from functools import cached_property
from typing import Optional, TypedDict

import tmt.log
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


class SourceInfo(TypedDict):
    raw: str
    is_url: bool
    is_glob: bool
    path: Optional[Path]


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

    SUPPORTED_PREFIX = "file"

    def __init__(self, raw_provider_id: str, logger: tmt.log.Logger):
        super().__init__(raw_provider_id, logger)
        self._source_info = self._parse_source(raw_provider_id)

    @classmethod
    def _extract_provider_id(cls, raw_provider_id: str) -> ArtifactProviderId:
        if not raw_provider_id.startswith(f"{cls.SUPPORTED_PREFIX}:"):
            raise ValueError(f"Unsupported provider id: {raw_provider_id}")
        return ArtifactProviderId(raw_provider_id)

    def _parse_source(self, raw_provider_id: str) -> SourceInfo:
        """
        Parse and classify a provider source string into its components.

        This extracts the actual artifact source from a raw provider ID by
        removing the provider prefix (e.g. ``file:``). It determines whether the source
        represents a URL, a glob pattern, or a local file/directory, and constructs a
        :py:class:`SourceInfo` object describing these properties.

        :param raw_provider_id: artifact provider identifier to parse.
        :returns: a :py:class:`SourceInfo` instance describing the parsed source.
        :raises ValueError: if the provider ID does not start with the expected prefix.
        """
        source = raw_provider_id[len(f"{self.SUPPORTED_PREFIX}:") :]
        parsed = urllib.parse.urlparse(source)

        return SourceInfo(
            raw=source,
            is_url=parsed.scheme in ("http", "https"),
            is_glob='*' in source,
            path=Path(source) if not parsed.scheme else None,
        )

    @cached_property
    def artifacts(self) -> Sequence[PackageAsFileArtifactInfo]:
        artifacts: list[PackageAsFileArtifactInfo] = []
        seen_ids: set[str] = set()

        def add(info: PackageAsFileArtifactInfo) -> None:
            if info.id not in seen_ids:
                artifacts.append(info)
                seen_ids.add(info.id)

        src = self._source_info

        if src['is_url']:
            add(PackageAsFileArtifactInfo(_raw_artifact=src['raw']))

        elif src['is_glob']:
            if matched_files := glob.glob(src['raw']):
                for matched_file in sorted(matched_files):
                    f = Path(matched_file)
                    if f.is_file():
                        add(PackageAsFileArtifactInfo(_raw_artifact=str(f)))
            else:
                self.logger.warning(f"No files matched the glob pattern: {src['raw']}.")

        elif src["path"] and src['path'].is_file():
            add(PackageAsFileArtifactInfo(_raw_artifact=str(src['path'])))

        elif src["path"] and src['path'].is_dir():
            for f in sorted(src['path'].glob("*.rpm")):
                add(PackageAsFileArtifactInfo(_raw_artifact=str(f)))

        if not artifacts:
            self.logger.warning(f"No artifacts found for source: {src['raw']}")

        return artifacts

    def _download_artifact(
        self, artifact: PackageAsFileArtifactInfo, guest: Guest, destination: Path
    ) -> None:
        raise NotImplementedError
