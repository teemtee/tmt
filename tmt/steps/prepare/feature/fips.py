import dataclasses
from typing import Any, Optional

import tmt.log
import tmt.steps.prepare
import tmt.utils
from tmt.steps.prepare.feature import Feature, PrepareFeatureData, provides_feature
from tmt.steps.provision import Guest
from tmt.utils import field


@dataclasses.dataclass
class FipsStepData(PrepareFeatureData):
    fips: Optional[str] = field(
        default='enabled',
        option='--fips',
        metavar='enabled',
        help='Whether FIPS mode should be enabled')


@provides_feature('fips')
class Fips(Feature):
    NAME = "fips"

    _data_class = FipsStepData

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

    @classmethod
    def enable(cls, guest: Guest, logger: tmt.log.Logger) -> None:
        cls._run_playbook('enable', "fips-enable.yaml", guest, logger)
