"""
Brew Artifact Provider
"""

from tmt.steps.prepare.brand_new_allmighty_install.providers.koji_provider import KojiProvider


class BrewProvider(KojiProvider):
    """
    Brew builds are just a special case of Koji builds
    """
