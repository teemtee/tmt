import re
from typing import Any, Optional

import tmt.log
import tmt.utils
from tmt.container import container, field
from tmt.guest import Guest
from tmt.package_managers import Options, Package, PackageUrl
from tmt.steps.prepare.feature import PrepareFeatureData, ToggleableFeature, provides_feature
from tmt.utils import ShellScript

SUPPORTED_DISTRO_PATTERNS = tuple(
    re.compile(pattern)
    for pattern in (
        r'Red Hat Enterprise Linux ([6-9]|[1-9][0-9]+)',
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

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

    @classmethod
    def _is_supported(cls, guest: Guest) -> bool:
        return bool(
            guest.facts.distro
            and any(pattern.match(guest.facts.distro) for pattern in SUPPORTED_DISTRO_PATTERNS)
        )

    @classmethod
    def _assert_distro_facts(cls, guest: Guest) -> tuple[str, int]:
        """Assert and return distro id and major version from guest facts."""
        distro = guest.facts.distro_id
        version = guest.facts.distro_major_version

        if distro is None:
            raise tmt.utils.GeneralError('Cannot determine distro id from guest facts.')

        if version is None:
            raise tmt.utils.GeneralError('Cannot determine distro major version from guest facts.')

        return distro, version

    @classmethod
    def enable(cls, guest: Guest, logger: tmt.log.Logger) -> None:
        if not cls._is_supported(guest):
            logger.warning('EPEL prepare feature is supported on RHEL/CentOS-Stream 8+.')
            return

        distro, version = cls._assert_distro_facts(guest)

        if distro == 'rhel':
            guest.package_manager.install(
                PackageUrl(
                    f"https://dl.fedoraproject.org/pub/epel/"
                    f"epel-release-latest-{version}.noarch.rpm"
                ),
                options=Options(allow_untrusted=True),
            )

        elif distro == 'centos':
            guest.package_manager.install(Package("epel-release"))
            # EPEL Next is available for CentOS Stream 9 only
            if version == 9:
                guest.package_manager.install(Package("epel-next-release"))

        logger.verbose('Enable EPEL')
        guest.package_manager.enable_repo('epel', 'epel-debuginfo', 'epel-source')

        # EPEL Next is only available for CentOS Stream 9
        if distro == 'centos' and version == 9:
            guest.package_manager.enable_repo(
                'epel-next', 'epel-next-debuginfo', 'epel-next-source'
            )

        # Enable CRB repository (needed for EPEL dependencies).
        # FORCE_DNF=1 skips subscription-manager, not configured in test environments.
        logger.info('Enable CRB (EPEL dependency)')
        guest.execute(
            ShellScript(f"FORCE_DNF=1 {guest.facts.sudo_prefix} crb enable"), immediately=False
        )

    @classmethod
    def disable(cls, guest: Guest, logger: tmt.log.Logger) -> None:
        if not cls._is_supported(guest):
            logger.warning('EPEL prepare feature is supported on RHEL/CentOS-Stream 8+.')
            return

        distro, version = cls._assert_distro_facts(guest)

        logger.verbose('Disable EPEL')
        epel_package = Package("epel-release")
        if guest.package_manager.check_presence(epel_package).get(epel_package):
            guest.package_manager.disable_repo('epel', 'epel-debuginfo', 'epel-source')

        # EPEL Next is only available for CentOS Stream 9
        if distro == 'centos' and version == 9:
            epel_next_package = Package("epel-next-release")
            if guest.package_manager.check_presence(epel_next_package).get(epel_next_package):
                guest.package_manager.disable_repo(
                    'epel-next', 'epel-next-debuginfo', 'epel-next-source'
                )
