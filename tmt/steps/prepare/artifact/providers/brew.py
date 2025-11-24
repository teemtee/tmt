"""
Brew Artifact Provider
"""

from collections.abc import Sequence
from functools import cached_property
from typing import Any, ClassVar, Optional
from urllib.parse import urljoin

import tmt.log
from tmt.steps.prepare.artifact.providers import provides_artifact_provider
from tmt.steps.prepare.artifact.providers.koji import (
    KojiArtifactProvider,
    KojiBuild,
    KojiNvr,
    KojiTask,
)


class BrewArtifactProvider(KojiArtifactProvider):
    """
    Provider for downloading artifacts from Brew builds.

    Brew builds are just a special case of Koji builds

    .. note::

        Only RPMs are supported currently.

    .. code-block:: python

        provider = BrewArtifactProvider("brew.build:123456", logger)
        artifacts = provider.fetch_contents(guest, Path("/tmp"))
    """

    def __init__(self, raw_provider_id: str, logger: tmt.log.Logger):
        super().__init__(raw_provider_id, logger)
        self._session = self._initialize_session(
            api_url="https://brewhub.engineering.redhat.com/brewhub",
            top_url="https://download.eng.bos.redhat.com/brew",
        )

    @cached_property
    def build_provider(self) -> Optional['BrewBuild']:
        return self._make_build_provider(BrewBuild, "brew.build")

    def _rpm_url(self, rpm_meta: dict[str, str]) -> str:
        """Construct Brew RPM URL."""
        name = rpm_meta["name"]
        version = rpm_meta["version"]
        release = rpm_meta["release"]
        arch = rpm_meta["arch"]
        assert self.build_info is not None
        volume = self.build_info["volume_name"]
        draft_suffix = f",draft_{self.build_id}" if self.build_info["draft"] else ""

        path = (
            f"vol/{volume}/packages/{name}/{version}/"
            f"{release}{draft_suffix}/{arch}/"
            f"{name}-{version}-{release}.{arch}.rpm"
        )

        return urljoin(self._top_url, path)


@provides_artifact_provider("brew.build")  # type: ignore[arg-type]
class BrewBuild(BrewArtifactProvider, KojiBuild):
    pass


@provides_artifact_provider("brew.task")  # type: ignore[arg-type]
class BrewTask(BrewArtifactProvider, KojiTask):
    pass


@provides_artifact_provider("brew.nvr")  # type: ignore[arg-type]
class BrewNvr(BrewArtifactProvider, KojiNvr):
    pass
