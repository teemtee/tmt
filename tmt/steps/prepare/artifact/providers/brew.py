"""
Brew Artifact Provider
"""

from tmt.steps.prepare.artifact.providers.koji import KojiArtifactProvider


class BrewProvider(KojiArtifactProvider):
    """
    Brew builds are just a special case of Koji builds
    """
