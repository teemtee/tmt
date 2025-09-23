"""
Brew Artifact Provider
"""

from tmt.steps.prepare.artifact.providers.koji_provider import KojiArtifactProvider


class BrewProvider(KojiArtifactProvider):
    """
    Brew builds are just a special case of Koji builds
    """
