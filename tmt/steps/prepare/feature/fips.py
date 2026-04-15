import re
from typing import Any, Optional

import tmt.log
import tmt.utils
from tmt.container import container, field
from tmt.guest import Guest
from tmt.package_managers import Package
from tmt.steps.prepare.feature import PrepareFeatureData, ToggleableFeature, provides_feature

SUPPORTED_DISTRO_PATTERNS = tuple(
    re.compile(pattern)
    for pattern in (r'Red Hat Enterprise Linux .*(7|8|9|10)', r'CentOS Stream (8|9|10)')
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
    """
    Enable FIPS mode on the guest.

    Enable FIPS mode on RHEL 7, 8, 9 and 10 and CentOS Stream
    8, 9 and 10 systems.

    .. code-block:: yaml

        prepare:
            how: feature
            fips: enabled

    .. code-block:: shell

        prepare --how feature --fips enabled

    .. note::

       In order to prevent issues with installation of packages signed by
       non-FIPS-compliant algorithms we recommend enabling FIPS mode after
       package installation prepare steps. Use ``order:`` to enforce that.
    """

    _data_class = FipsStepData

    PLAYBOOKS = {'fips-enable.yaml'}

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

    @classmethod
    def disable(cls, guest: Guest, logger: tmt.log.Logger) -> None:
        raise tmt.utils.GeneralError('FIPS prepare feature does not support \'disabled\'.')

    @classmethod
    def enable(cls, guest: Guest, logger: tmt.log.Logger) -> None:
        if guest.facts.is_container or (guest.facts.is_ostree and not guest.facts.is_image_mode):
            raise tmt.utils.GeneralError(
                'FIPS prepare feature is not supported on ostree or container systems.'
            )
        if not (
            guest.facts.distro
            and any(pattern.match(guest.facts.distro) for pattern in SUPPORTED_DISTRO_PATTERNS)
        ):
            raise tmt.utils.GeneralError(
                'FIPS prepare feature is supported on RHEL 7 and RHEL/CentOS-Stream 8, 9 or 10.'
            )

        # Install packages via package_manager instead of Ansible playbook
        # to support image mode (bootc) guests with immutable /usr filesystem.
        # The playbook handles only /etc and /var mutations (bootloader config,
        # crypto policies, prelink, reboot and verification).
        #
        # RHEL 7: dracut-fips + grubby, then grubby sets fips=1 boot param
        # RHEL/CentOS 8-9: crypto-policies-scripts + dracut-fips + grubby,
        #   then fips-mode-setup --enable
        # RHEL/CentOS 10+: grubby only, then grubby sets fips=1 boot param
        #   (fips-mode-setup is no longer available on RHEL/CentOS 10)
        version = guest.facts.distro_major_version

        if version == 7:
            guest.package_manager.install(Package("dracut-fips"), Package("grubby"))
        elif version in (8, 9):
            guest.package_manager.install(
                Package("crypto-policies-scripts"), Package("dracut-fips"), Package("grubby")
            )
        elif version is not None and version >= 10:
            guest.package_manager.install(Package("grubby"))

        cls._run_playbook('enable', 'fips-enable.yaml', guest, logger)
