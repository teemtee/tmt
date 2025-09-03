"""
Brew Artifact Provider
"""

import tmt.log
from tmt.steps.prepare.brand_new_allmighty_install.providers.koji import KojiProvider


class BrewProvider(KojiProvider):
    """
    Brew builds are just a special case of Koji builds
    """

    def __init__(self, logger: tmt.log.Logger, artifact_id: str):
        super().__init__(logger, artifact_id)
