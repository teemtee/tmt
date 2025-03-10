import re
from typing import Any, Optional

import tmt.log
import tmt.steps.prepare
import tmt.utils
from tmt.container import container, field
from tmt.steps.prepare.feature import PrepareFeatureData, ToggleableFeature, provides_feature
from tmt.steps.provision import Guest


@container
class FipsStepData(PrepareFeatureData):
    fips: Optional[str] = field(
        default=None,
        option='--fips',
        metavar='enabled',
        help='Whether FIPS mode should be enabled',
    )


@provides_feature('fips')
class Epel(ToggleableFeature):
    NAME = "fips"

    _data_class = FipsStepData

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

    @classmethod
    def disable(cls, guest: Guest, logger: tmt.log.Logger) -> None:
        raise tmt.utils.GeneralError('FIPS prepare feature does not support \'disabled\'.')

    @classmethod
    def enable(cls, guest: Guest, logger: tmt.log.Logger) -> None:
        if guest.facts.is_ostree:
            raise tmt.utils.GeneralError(
                'FIPS prepare feature is not supported on ostree systems.'
            )
        if guest.facts.container:
            raise tmt.utils.GeneralError(
                'FIPS prepare feature is not supported on container systems.'
            )
        if not guest.facts.distro or (
            not re.compile('Red Hat Enterprise Linux (8|9|10)\\.').match(guest.facts.distro)
            and not re.compile('Centos Stream (8|9|10)').match(guest.facts.distro)
        ):
            raise tmt.utils.GeneralError(
                'FIPS prepare feature is supported on systems with RHEL/Centos-Stream 8, 9 or 10.'
            )
        cls._run_playbook('enable', 'fips-enable.yaml', guest, logger)
