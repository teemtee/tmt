"""
Brew Artifact Provider
"""

from collections.abc import Sequence
from functools import cached_property
from typing import TYPE_CHECKING, ClassVar, Optional

import tmt.log
import tmt.utils
from tmt.steps.prepare.artifact.providers import provides_artifact_provider
from tmt.steps.prepare.artifact.providers.koji import (
    KojiArtifactProvider,
    KojiBuild,
    KojiNvr,
    KojiTask,
    RpmArtifactInfo,
    import_koji,
)

if TYPE_CHECKING:
    from koji import ClientSession


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

    SUPPORTED_PREFIXES: ClassVar[tuple[str, ...]] = ("brew.build:", "brew.task:", "brew.nvr:")

    def __new__(cls, raw_provider_id: str, logger: tmt.log.Logger) -> 'BrewArtifactProvider':
        """
        Create a specific Brew provider based on the ``raw_provider_id`` prefix.

        The supported providers are:
        :py:class:`BrewBuild`,
        :py:class:`BrewTask`,
        :py:class:`BrewNvr`.

        :raises ValueError: If the prefix is not supported
        """
        if raw_provider_id.startswith("brew.build:"):
            return object.__new__(BrewBuild)
        if raw_provider_id.startswith("brew.task:"):
            return object.__new__(BrewTask)
        if raw_provider_id.startswith("brew.nvr:"):
            return object.__new__(BrewNvr)
        # If we get here, the prefix is not supported
        raise ValueError(
            f"Unsupported artifact ID format: '{raw_provider_id}'. "
            f"Supported formats are: {', '.join(cls.SUPPORTED_PREFIXES)}"
        )

    def _initialize_session(self) -> 'ClientSession':
        """
        Initialize a Brew session using Brew-specific configuration.

        Brew uses a different configuration profile than standard Koji.
        This method reads the 'brew' profile from the Koji configuration.

        :returns: Initialized ClientSession for Brew
        :raises GeneralError: If session initialization fails
        """
        import_koji(self.logger)
        from tmt.steps.prepare.artifact.providers.koji import ClientSession

        try:
            # config = koji.read_config("brew")  # This does not work!
            self._api_url = "https://brewhub.engineering.redhat.com/brewhub"
            self._top_url = "https://download.eng.bos.redhat.com/brew"
            return ClientSession(self._api_url)
        except Exception as error:
            raise tmt.utils.GeneralError(
                "Failed to initialize Brew API session. Ensure Brew configuration is available."
            ) from error


@provides_artifact_provider("brew.build")  # type: ignore[arg-type]
class BrewBuild(BrewArtifactProvider, KojiBuild):
    pass


@provides_artifact_provider("brew.task")  # type: ignore[arg-type]
class BrewTask(BrewArtifactProvider, KojiTask):
    pass


@provides_artifact_provider("brew.nvr")  # type: ignore[arg-type]
class BrewNvr(BrewArtifactProvider, KojiNvr):
    pass
