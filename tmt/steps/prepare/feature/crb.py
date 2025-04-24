import re
from typing import Any, Optional

import tmt.log
import tmt.utils
from tmt.container import container, field
from tmt.package_managers import Package
from tmt.steps.prepare.feature import PrepareFeatureData, ToggleableFeature, provides_feature
from tmt.steps.provision import Guest
from tmt.utils import DEFAULT_SHELL, ShellScript

# URL of the upstream script
UPSTREAM_SCRIPT_URL = "https://src.fedoraproject.org/rpms/epel-release/raw/epel10/f/crb"

SUPPORTED_DISTRO_PATTERNS = (
    re.compile(pattern)
    for pattern in (r'Red Hat Enterprise Linux (8|9|10)', r'CentOS Stream (8|9|10)')
)


@container
class CrbStepData(PrepareFeatureData):
    crb: Optional[str] = field(
        default=None,
        option='--crb',
        metavar='enabled|disabled',
        help='Whether the CRB repository should be enabled or disabled.',
    )


@provides_feature('crb')
class Crb(ToggleableFeature):
    """
    Control CodeReady Builder (CRB) repository using the upstream script.

    Uses the `crb` script from https://src.fedoraproject.org/rpms/epel-release
    to enable or disable the CRB repository on RHEL 8+ and CentOS Stream 8+.

    Enable or disable the repository on the guest:

    .. code-block:: yaml

        prepare:
            how: feature
            crb: enabled

    .. code-block:: shell

        prepare --how feature --crb enabled
    """

    _data_class = CrbStepData

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

    @classmethod
    def _check_distro(cls, guest: Guest, logger: tmt.log.Logger) -> None:
        """Verify the guest distribution is supported and install config-manager if needed"""
        if not (
            guest.facts.distro
            and any(pattern.match(guest.facts.distro) for pattern in SUPPORTED_DISTRO_PATTERNS)
        ):
            raise tmt.utils.GeneralError(
                'CRB prepare feature is supported on RHEL/CentOS-Stream 8, 9 or 10.'
            )

        guest.package_manager.install(Package("dnf-command(config-manager)"))

    @classmethod
    def _manage_repo(cls, guest: Guest, logger: tmt.log.Logger, action: str) -> None:
        """Enable or disable the repository using the upstream script"""
        cls._check_distro(guest, logger)

        logger.info(f"{action.capitalize()} CRB repository using upstream script.")

        # Command to download and execute the script, passing the action (enable/disable)
        # sh -s -- action: passes 'action' as an argument ($1) to the script executed by sh
        guest.execute(
            ShellScript(
                f"curl -sS {UPSTREAM_SCRIPT_URL} | FORCE_DNF=1 {DEFAULT_SHELL} -s -- {action}"
            )
        )

    @classmethod
    def enable(cls, guest: Guest, logger: tmt.log.Logger) -> None:
        cls._manage_repo(guest, logger, action='enable')

    @classmethod
    def disable(cls, guest: Guest, logger: tmt.log.Logger) -> None:
        cls._manage_repo(guest, logger, action='disable')
