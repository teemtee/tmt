"""
Brew Artifact Provider
"""

from functools import cached_property
from typing import Optional

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

    profile = "brew"

    @cached_property
    def build_provider(self) -> Optional['BrewBuild']:
        return self._make_build_provider(BrewBuild, "brew.build")


@provides_artifact_provider("brew.build")
class BrewBuild(BrewArtifactProvider, KojiBuild):
    pass


@provides_artifact_provider("brew.task")
class BrewTask(BrewArtifactProvider, KojiTask):
    pass


@provides_artifact_provider("brew.nvr")
class BrewNvr(BrewArtifactProvider, KojiNvr):
    pass
