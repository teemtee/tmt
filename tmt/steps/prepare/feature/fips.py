import re
from typing import Any, Optional

import tmt.log
import tmt.utils
from tmt.container import container, field
from tmt.steps.prepare.feature import PrepareFeatureData, ToggleableFeature, provides_feature
from tmt.steps.provision import Guest

SUPPORTED_DISTRO_PATTERNS = (
    re.compile(pattern)
    for pattern in (r'Red Hat Enterprise Linux (8|9|10)', r'CentOS Stream (8|9|10)')
)


@container
class FipsStepData(PrepareFeatureData):
    fips: Optional[str] = field(
        default=None,
        option='--fips',
        metavar='enabled',
        help='Whether FIPS mode should be enabled',
    )


@provides_feature('fips')
class Fips(ToggleableFeature):
    _data_class = FipsStepData

    PLAYBOOKS = {'fips-enable.yaml'}

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

    @classmethod
    def disable(cls, guest: Guest, logger: tmt.log.Logger) -> None:
        raise tmt.utils.GeneralError('FIPS prepare feature does not support \'disabled\'.')

    @classmethod
    def enable(cls, guest: Guest, logger: tmt.log.Logger) -> None:
        if guest.facts.is_ostree or guest.facts.is_container:
            raise tmt.utils.GeneralError(
                'FIPS prepare feature is not supported on ostree or container systems.'
            )
        if not (
            guest.facts.distro
            and any(pattern.match(guest.facts.distro) for pattern in SUPPORTED_DISTRO_PATTERNS)
        ):
            raise tmt.utils.GeneralError(
                'FIPS prepare feature is supported on RHEL/CentOS-Stream 8, 9 or 10.'
            )
        cls._run_playbook('enable', 'fips-enable.yaml', guest, logger)
