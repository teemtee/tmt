import re
from typing import Any, Optional

import tmt.log
from tmt.container import container, field
from tmt.steps.prepare.feature import PrepareFeatureData, ToggleableFeature, provides_feature
from tmt.steps.provision import Guest

SUPPORTED_DISTRO_PATTERNS = tuple(
    re.compile(pattern)
    for pattern in (
        r'Red Hat Enterprise Linux ([8-9]|[1-9][0-9]+)',
        r'CentOS Stream ([8-9]|[1-9][0-9]+)',
    )
)


@container
class EpelStepData(PrepareFeatureData):
    epel: Optional[str] = field(
        default=None,
        option='--epel',
        metavar='enabled|disabled',
        help='Whether EPEL repository should be installed & enabled or disabled.',
    )


@provides_feature('epel')
class Epel(ToggleableFeature):
    """
    Control Extra Packages for Enterprise Linux (EPEL) repository.

    `EPEL`__ is an initiative within the Fedora Project to provide high
    quality additional packages for CentOS Stream and Red Hat Enterprise
    Linux (RHEL).

    Enable or disable EPEL repository on the guest:

    .. code-block:: yaml

        prepare:
            how: feature
            epel: enabled

    .. code-block:: shell

        prepare --how feature --epel enabled

    __ https://docs.fedoraproject.org/en-US/epel/
    """

    _data_class = EpelStepData

    PLAYBOOKS = {'epel-enable.yaml', 'epel-disable.yaml'}

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

    @classmethod
    def enable(cls, guest: Guest, logger: tmt.log.Logger) -> None:
        if not (
            guest.facts.distro
            and any(pattern.match(guest.facts.distro) for pattern in SUPPORTED_DISTRO_PATTERNS)
        ):
            logger.warning('EPEL prepare feature is supported on RHEL/CentOS-Stream 8+.')
            return
        cls._run_playbook('enable', "epel-enable.yaml", guest, logger)

    @classmethod
    def disable(cls, guest: Guest, logger: tmt.log.Logger) -> None:
        cls._run_playbook('disable', "epel-disable.yaml", guest, logger)
