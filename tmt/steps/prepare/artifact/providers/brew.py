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


# ignore[type-arg]: TypeVar in provider registry annotations is
# puzzling for type checkers. And not a good idea in general, probably.
@provides_artifact_provider('brew')  # type: ignore[arg-type]
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

    SUPPORTED_PREFIXES: ClassVar[tuple[str, ...]] = ()

    def __new__(cls, raw_provider_id: str, logger: tmt.log.Logger) -> Any:
        """
        Create a specific Brew provider based on the ``raw_provider_id`` prefix.

        The supported providers are:
        :py:class:`BrewBuild`,
        :py:class:`BrewTask`,
        :py:class:`BrewNvr`.

        :raises ValueError: If the prefix is not supported
        """
        return cls._dispatch_subclass(raw_provider_id, cls._REGISTRY)

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


BrewArtifactProvider._REGISTRY = {
    "brew.build": BrewBuild,
    "brew.task": BrewTask,
    "brew.nvr": BrewNvr,
}
BrewArtifactProvider.SUPPORTED_PREFIXES = tuple(BrewArtifactProvider._REGISTRY.keys())
