"""
Brew Artifact Provider
"""

from tmt.steps.prepare.artifact.providers import provides_artifact_provider
from tmt.steps.prepare.artifact.providers.koji import KojiArtifactProvider


# ignore[type-arg]: TypeVar in provider registry annotations is
# puzzling for type checkers. And not a good idea in general, probably.
@provides_artifact_provider('brew')  # type: ignore[arg-type]
class BrewProvider(KojiArtifactProvider):
    """
    Brew builds are just a special case of Koji builds
    """
