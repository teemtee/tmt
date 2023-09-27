import dataclasses
import enum
from typing import Optional, cast

import tmt
import tmt.base
import tmt.log
import tmt.options
import tmt.steps
import tmt.steps.prepare
import tmt.utils
from tmt.steps.provision import Guest
from tmt.utils import ShellScript, field


class Distro(enum.Enum):
    FEDORA = enum.auto()
    RHEL_7 = enum.auto()
    RHEL_8 = enum.auto()
    RHEL_9 = enum.auto()
    CENTOS_7 = enum.auto()
    CENTOS_STREAM_8 = enum.auto()
    CENTOS_STREAM_9 = enum.auto()


class Feature(tmt.utils.Common):
    """ Base class for feature implementations """

    KEY: str

    def __init__(
            self,
            *,
            parent: 'PrepareFeature',
            guest: Guest,
            logger: tmt.log.Logger) -> None:
        """ Initialize feature data """
        super().__init__(logger=logger, parent=parent, relative_indent=0)
        self.guest = guest
        self.logger = logger
        self.guest_sudo = self.get_guest_sudo()
        self.guest_distro = self.get_guest_distro()
        self.guest_distro_name = self.get_guest_distro_name()

    def get_guest_sudo(self) -> str:
        """ Return 'sudo' if guest is not superuser """
        if not self.guest.facts.is_superuser:
            return 'sudo'
        return ''

    def get_guest_distro(self) -> Optional[Distro]:
        """ Get guest distro by parsing the guest facts """
        os_release = self.guest.facts.os_release_content
        if os_release is None:
            return None

        if os_release.get('NAME', '') == 'Fedora Linux':
            return Distro.FEDORA

        if os_release.get('NAME', '').startswith('Red Hat Enterprise Linux'):
            if os_release.get('VERSION_ID', '').startswith('9.'):
                return Distro.RHEL_9
            if os_release.get('VERSION_ID', '').startswith('8.'):
                return Distro.RHEL_8
            if os_release.get('VERSION_ID', '').startswith('7.'):
                return Distro.RHEL_7

        if os_release.get('NAME', '').startswith('CentOS Linux') and os_release.get(
                'VERSION_ID', '').startswith('7.'):
            return Distro.CENTOS_7

        if os_release.get('NAME', '').startswith('CentOS Stream'):
            if os_release.get('VERSION_ID', '').startswith('8.'):
                return Distro.CENTOS_STREAM_8
            if os_release.get('VERSION_ID', '').startswith('9.'):
                return Distro.CENTOS_STREAM_9

        return None

    def get_guest_distro_name(self) -> Optional[str]:
        """ Get guest distro name by parsing the guest facts """
        os_release = self.guest.facts.os_release_content
        if os_release is None:
            return None
        return os_release.get('PRETTY_NAME', None)


class ToggleableFeature(Feature):
    def enable(self) -> None:
        raise NotImplementedError

    def disable(self) -> None:
        raise NotImplementedError


FEDORA_PACKAGES = ['epel-release', 'epel-next-release']
CENTOS_7_PACKAGES = ['epel-release']
RHEL_7_PACKAGES = ['https://dl.fedoraproject.org/pub/epel/epel-release-latest-7.noarch.rpm']
RHEL_8_PACKAGES = ['https://dl.fedoraproject.org/pub/epel/epel-release-latest-8.noarch.rpm']
RHEL_9_PACKAGES = ['https://dl.fedoraproject.org/pub/epel/epel-release-latest-9.noarch.rpm']

RHEL_EPEL_REPOS = ['epel', 'epel-debuginfo', 'epel-source']


class EPEL(ToggleableFeature):
    KEY = 'epel'

    def enable(self) -> None:
        distro = self.guest_distro
        sudo = self.guest_sudo

        key_name = self.KEY.upper()
        distro_name = cast(str, self.guest_distro_name)
        if distro == Distro.FEDORA:
            self.info(f"Nothing to do on {distro_name} for {key_name}")
        elif distro == Distro.CENTOS_7:
            # yum install epel-release
            self.info(f"Enable {key_name} on {distro_name}")
            self.guest.execute(
                ShellScript(f'{sudo} yum -y install {" ".join(CENTOS_7_PACKAGES)}'),
                silent=True)
        elif distro == Distro.CENTOS_STREAM_8 or distro == Distro.CENTOS_STREAM_9:
            # dnf -y install epel-release epel-next-release
            self.info(f"Enable {key_name} on {distro_name}")
            self.guest.execute(
                ShellScript(f'{sudo} dnf -y install {" ".join(FEDORA_PACKAGES)}'),
                silent=True)
        elif distro == Distro.RHEL_7:
            self.info(f"Enable {key_name} on {distro_name}")
            self.guest.execute(
                ShellScript(f"""
                            set -x;
                            rpm -q epel-release || \
                                {sudo} yum install -y {" ".join(RHEL_7_PACKAGES)};
                            rpm -q yum-utils || {sudo} yum install -y yum-utils;
                            {sudo} yum-config-manager --enable {" ".join(RHEL_EPEL_REPOS)}
                            """),
                silent=True)
        elif distro == Distro.RHEL_8:
            self.info(f"Enable {key_name} on {distro_name}")
            self.guest.execute(
                ShellScript(f"""
                            set -x;
                            rpm -q epel-release || \
                                {sudo} dnf install -y {" ".join(RHEL_8_PACKAGES)};
                            {sudo} dnf config-manager --enable {" ".join(RHEL_EPEL_REPOS)}
                            """),
                silent=True)
        elif distro == Distro.RHEL_9:
            self.info(f"Enable {key_name} on {distro_name}")
            self.guest.execute(
                ShellScript(f"""
                            set -x;
                            rpm -q epel-release || \
                                {sudo} dnf install -y {" ".join(RHEL_9_PACKAGES)};
                            {sudo} dnf config-manager --enable {" ".join(RHEL_EPEL_REPOS)}
                            """),
                silent=True)
        else:
            self.warn(f"Enable {key_name}: '{distro_name}' of the guest is unsupported.")

    def disable(self) -> None:
        """
        We just disable the repo because we don't know whether the epel-relase package was
        installed by user on purpose or not.
        """

        distro = self.guest_distro
        sudo = self.guest_sudo

        key_name = self.KEY.upper()
        distro_name = cast(str, self.guest_distro_name)
        if distro == Distro.FEDORA:
            self.info(f"Nothing to do on {distro_name} for {key_name}")
        elif distro == Distro.CENTOS_7:
            self.info(f"Disable {key_name} on {distro_name}")
            self.guest.execute(
                ShellScript(f'{sudo} yum -y remove {" ".join(CENTOS_7_PACKAGES)}'),
                silent=True)
        elif distro == Distro.CENTOS_STREAM_8 or distro == Distro.CENTOS_STREAM_9:
            self.info(f"Disable {key_name} on {distro_name}")
            self.guest.execute(
                ShellScript(f'{sudo} dnf -y remove {" ".join(FEDORA_PACKAGES)}'),
                silent=True)
        elif distro == Distro.RHEL_7:
            self.info(f"Disable {key_name} on {distro_name}")
            self.guest.execute(
                ShellScript(f"""
                            set -x;
                            rpm -q yum-utils || {sudo} yum install -y yum-utils;
                            {sudo} yum-config-manager --disable {" ".join(RHEL_EPEL_REPOS)}
                            """),
                silent=True)
        elif distro == Distro.RHEL_8 or distro == Distro.RHEL_9:
            self.info(f"Disable {key_name} on {distro_name}")
            self.guest.execute(
                ShellScript(f"""
                            set -x;
                            {sudo} dnf config-manager --disable {" ".join(RHEL_EPEL_REPOS)}
                            """),
                silent=True)
        else:
            self.warn(f"Disable {key_name}: '{distro_name}' of the guest is unsupported.")


class CRB(ToggleableFeature):
    KEY = 'crb'

    def enable(self) -> None:
        """
        Enable CRB on the guest. Note that RHEL8 and RHEL9 are supported.
        """
        distro = self.guest_distro
        sudo = self.guest_sudo

        key_name = self.KEY.upper()
        distro_name = cast(str, self.guest_distro_name)
        if distro == Distro.RHEL_8:
            self.info(f"Enable {key_name} on '{distro_name}'")
            # Note that command crb is from package epel-release
            self.guest.execute(
                ShellScript(f"""
                            set -x;
                            rpm -q epel-release || \
                                {sudo} dnf install -y {" ".join(RHEL_8_PACKAGES)};
                            /usr/bin/crb enable
                            """),
                silent=True)
        elif distro == Distro.RHEL_9:
            self.info(f"Enable {key_name} on '{distro_name}'")
            # Note that command crb is from package epel-release
            self.guest.execute(
                ShellScript(f"""
                            set -x;
                            rpm -q epel-release || \
                                {sudo} dnf install -y {" ".join(RHEL_9_PACKAGES)};
                            /usr/bin/crb enable
                            """),
                silent=True)
        else:
            self.warn(f"Enable {key_name}: '{distro_name}' of the guest is unsupported.")

    def disable(self) -> None:
        """
        Disable CRB on the guest. Note that RHEL8 and RHEL9 are supported.
        """
        distro = self.guest_distro
        sudo = self.guest_sudo

        key_name = self.KEY.upper()
        distro_name = cast(str, self.guest_distro_name)
        if distro == Distro.RHEL_8 or distro == Distro.RHEL_9:
            self.info(f"Disable {key_name} on '{distro_name}'")
            self.guest.execute(
                ShellScript("""
                            set -x;
                            /usr/bin/crb disable
                            """),
                silent=True)
        else:
            self.warn(f"Disable {key_name}: '{distro_name}' of the guest is unsupported.")


class FIPS(ToggleableFeature):
    KEY = 'fips'

    def enable(self) -> None:
        """
        There are two steps to enable FIPS mode:
        1. To switch the system to FIPS mode:
           $ sudo fips-mode-setup --enable
        2. Restart the system to allow the kernel to switch to FIPS mode:
           $ sudo reboot
        After the restart, user can check the current state of FIPS mode via:
           $ sudo fips-mode-setup --check
        """

        distro = self.guest_distro
        sudo = self.guest_sudo

        key_name = self.KEY.upper()
        distro_name = cast(str, self.guest_distro_name)
        if distro == Distro.FEDORA:
            self.info(f"Enable {key_name} on {distro_name}")
        elif distro in (Distro.RHEL_8, Distro.RHEL_9):
            self.info(f"Enable {key_name} on '{distro_name}'")
            self.guest.execute(ShellScript(f'{sudo} fips-mode-setup --enable'), silent=True)
            self.info('reboot', 'Rebooting guest', color='yellow')
            self.guest.reboot()
            self.info('reboot', 'Reboot finished', color='yellow')
        else:
            self.warn(f"Enable {key_name}: '{distro_name}' of the guest is unsupported.")

    def disable(self) -> None:
        distro = self.guest_distro
        sudo = self.guest_sudo

        key_name = self.KEY.upper()
        distro_name = cast(str, self.guest_distro_name)
        if distro == Distro.FEDORA:
            self.info(f"Disable {key_name} on Fedora")
        elif distro in (Distro.RHEL_8, Distro.RHEL_9):
            self.info(f"Disable {key_name} on '{distro_name}'")
            self.guest.execute(ShellScript(f'{sudo} fips-mode-setup --disable'), silent=True)
            self.info('reboot', 'Rebooting guest', color='yellow')
            self.guest.reboot()
            self.info('reboot', 'Reboot finished', color='yellow')
        else:
            self.warn(f"Disable {key_name}: '{distro_name}' of the guest is unsupported.")


_FEATURES = {
    EPEL.KEY: EPEL,
    CRB.KEY: CRB,
    FIPS.KEY: FIPS
    }


@dataclasses.dataclass
class PrepareFeatureData(tmt.steps.prepare.PrepareStepData):
    epel: Optional[str] = field(
        default=None,
        option=('-e', '--epel'),
        metavar='EPEL',
        help='epel to be enabled.'
        )

    crb: Optional[str] = field(
        default=None,
        option=('-c', '--crb'),
        metavar='CRB',
        help='crb to be enabled.'
        )

    fips: Optional[str] = field(
        default=None,
        option=('-f', '--fips'),
        metavar='FIPS',
        help='fips to be enabled.'
        )


@tmt.steps.provides_method('feature')
class PrepareFeature(tmt.steps.prepare.PreparePlugin):
    """
    Enable or disable common features such as epel, crb and fips on the guest

    Example config:

        prepare:
            how: feature
            epel: enabled
            crb: enabled
            fips: enabled

        Or

        prepare:
            how: feature
            epel: disabled
            crb: disabled
            fips: disabled
    """

    _data_class = PrepareFeatureData

    def go(
            self,
            *,
            guest: 'Guest',
            environment: Optional[tmt.utils.EnvironmentType] = None,
            logger: tmt.log.Logger) -> None:
        """ Prepare the guests """
        super().go(guest=guest, environment=environment, logger=logger)

        # Nothing to do in dry mode
        if self.opt('dry'):
            return

        # XXX: Currenly three provision methods are supported:
        #      1) connect
        #      2) virtual
        #      3) local
        if not isinstance(guest, (tmt.steps.provision.GuestSsh,
                                  tmt.steps.provision.testcloud.ProvisionTestcloud,
                                  tmt.steps.provision.local.GuestLocal)):
            raise tmt.utils.GeneralError("The provision method is unsupported by this feature.")

        # Enable or disable epel/crb/fips
        for key in _FEATURES:
            value = getattr(self.data, key, None)
            if value is None:
                continue

            feature = _FEATURES[key](parent=self, guest=guest, logger=logger)
            value = value.lower() if isinstance(feature, ToggleableFeature) else None
            if value == 'enabled':
                feature.enable()
            elif value == 'disabled':
                feature.disable()
            else:
                raise tmt.utils.GeneralError("Unknown method")
