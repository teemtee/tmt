from typing import Any

import tmt.log
from tmt.steps.prepare.feature import Feature, provides_feature
from tmt.steps.provision import Guest


@provides_feature('epel')
class Epel(Feature):
    NAME = "epel"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

    @classmethod
    def enable(cls, guest: Guest, logger: tmt.log.Logger) -> None:
        cls._run_playbook('enable', "epel-enable.yaml", guest, logger)

    @classmethod
    def disable(cls, guest: Guest, logger: tmt.log.Logger) -> None:
        cls._run_playbook('disable', "epel-disable.yaml", guest, logger)
