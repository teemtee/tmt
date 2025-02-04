import dataclasses
from typing import Any, Optional

import tmt.log
import tmt.steps.prepare
import tmt.utils
from tmt.steps.prepare.feature import Feature, PrepareFeatureData, provides_feature
from tmt.steps.provision import Guest
from tmt.utils import field


@dataclasses.dataclass
class EpelStepData(PrepareFeatureData):
    epel: Optional[str] = field(
        default=None,
        option='--epel',
        metavar='enabled|disabled',
        help='Whether EPEL repository should be installed & enabled or disabled.')


@provides_feature('epel')
class Epel(Feature):
    NAME = "epel"

    _data_class = EpelStepData

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

    @classmethod
    def enable(cls, guest: Guest, logger: tmt.log.Logger) -> None:
        cls._run_playbook('enable', "epel-enable.yaml", guest, logger)

    @classmethod
    def disable(cls, guest: Guest, logger: tmt.log.Logger) -> None:
        cls._run_playbook('disable', "epel-disable.yaml", guest, logger)
