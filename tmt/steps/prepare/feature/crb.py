import re
from typing import Any, Optional

import tmt.log
from tmt.container import container, field
from tmt.package_managers import Package
from tmt.steps.prepare.feature import PrepareFeatureData, ToggleableFeature, provides_feature
from tmt.steps.provision import Guest
from tmt.utils import ShellScript

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
    Enable or disable the CodeReady Builder (CRB) repository:

    .. code-block:: yaml

        prepare:
            how: feature
            crb: enabled

    .. code-block:: shell

        prepare --how feature --crb enabled

    .. versionadded:: 1.49
    """

    _data_class = CrbStepData

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

    @classmethod
    def _manage_repo(cls, guest: Guest, logger: tmt.log.Logger, action: str) -> None:
        """Enable or disable the repository"""

        # Check if we're running on supported distro
        if not (
            guest.facts.distro
            and any(pattern.match(guest.facts.distro) for pattern in SUPPORTED_DISTRO_PATTERNS)
        ):
            logger.warning('CRB prepare feature is supported on RHEL/CentOS-Stream 8, 9 or 10.')
            return

        guest.package_manager.install(Package("dnf-command(config-manager)"))

        logger.info(f"{action.capitalize()} CRB repository.")

        # Inspired by crb executable from https://src.fedoraproject.org/rpms/epel-release
        command_prefix = "sudo " if not guest.facts.is_superuser else ""
        script_content = rf"""
            {command_prefix}dnf config-manager --{action} $(dnf repolist --all | \
            grep -i -e crb -e powertools -e codeready | \
            grep -v -i -e debug -e source -e eus -e virt -e rhui | \
            sed 's/^\s*\([^ ]*\).*/\1/')
        """
        guest.execute(ShellScript(script_content))

    @classmethod
    def enable(cls, guest: Guest, logger: tmt.log.Logger) -> None:
        cls._manage_repo(guest, logger, action='enable')

    @classmethod
    def disable(cls, guest: Guest, logger: tmt.log.Logger) -> None:
        cls._manage_repo(guest, logger, action='disable')
