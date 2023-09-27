import dataclasses
import enum
from typing import Optional

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
        self.guest_arch = self.guest.facts.arch

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

        if os_release.get('NAME') == 'Fedora Linux':
            return Distro.FEDORA

        if os_release.get('NAME') == 'Red Hat Enterprise Linux':
            if os_release.get('VERSION_ID', '').startswith('9.'):
                return Distro.RHEL_9
            if os_release.get('VERSION_ID', '').startswith('8.'):
                return Distro.RHEL_8
            if os_release.get('VERSION_ID', '').startswith('7.'):
                return Distro.RHEL_7

        if os_release.get('NAME') == 'CentOS Linux' and os_release.get(
                'VERSION_ID', '').startswith('7.'):
            return Distro.CENTOS_7

        if os_release.get('NAME') == 'CentOS Stream':
            if os_release.get('VERSION_ID', '').startswith('8.'):
                return Distro.CENTOS_STREAM_8
            if os_release.get('VERSION_ID', '').startswith('9.'):
                return Distro.CENTOS_STREAM_9

        return None


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


CRB_RHEL_8_REPO_X86_64 = ['codeready-builder-for-rhel-8-x86_64-rpms']


class EPEL(ToggleableFeature):
    KEY = 'epel'

    def enable(self) -> None:
        distro = self.guest_distro
        sudo = self.guest_sudo

        if distro == Distro.FEDORA:
            self.info('Nothing to do on Fedora for EPEL')
        elif distro == Distro.CENTOS_7:
            # yum install epel-release
            self.info(f"Enable {self.KEY.upper()} on CentOS 7")
            self.guest.execute(
                ShellScript(f'{sudo} yum -y install {" ".join(CENTOS_7_PACKAGES)}'),
                silent=True)
        elif distro == Distro.CENTOS_STREAM_8:
            # dnf -y install epel-release epel-next-release
            self.info(f"Enable {self.KEY.upper()} on CentOS Stream 8")
            self.guest.execute(
                ShellScript(f'{sudo} dnf -y install {" ".join(FEDORA_PACKAGES)}'),
                silent=True)
        elif distro == Distro.CENTOS_STREAM_9:
            # dnf -y install epel-release epel-next-release
            self.info(f"Enable {self.KEY.upper()} on CentOS Stream 9")
            self.guest.execute(
                ShellScript(f'{sudo} dnf -y install {" ".join(FEDORA_PACKAGES)}'),
                silent=True)
        elif distro == Distro.RHEL_7:
            # yum install https://dl.fedoraproject.org/pub/epel/epel-release-latest-7.noarch.rpm
            self.info(f"Enable {self.KEY.upper()} on RHEL 7")
            self.guest.execute(
                ShellScript(f'{sudo} yum -y install {" ".join(RHEL_7_PACKAGES)}'),
                silent=True)
        elif distro == Distro.RHEL_8:
            # dnf -y install https://dl.fedoraproject.org/pub/epel/epel-release-latest-8.noarch.rpm
            self.info(f"Enable {self.KEY.upper()} on RHEL 8")
            self.guest.execute(
                ShellScript(f'{sudo} dnf -y install {" ".join(RHEL_8_PACKAGES)}'),
                silent=True)
        elif distro == Distro.RHEL_9:
            # dnf -y install https://dl.fedoraproject.org/pub/epel/epel-release-latest-9.noarch.rpm
            self.info(f"Enable {self.KEY.upper()} on RHEL 9")
            self.guest.execute(
                ShellScript(f'{sudo} dnf -y install {" ".join(RHEL_9_PACKAGES)}'),
                silent=True)
        else:
            self.warn(f"Enable {self.KEY.upper()}: '{distro}' of the guest is unsupported.")

    def disable(self) -> None:
        distro = self.guest_distro
        sudo = self.guest_sudo

        if distro == Distro.FEDORA:
            self.info('Nothing to do on Fedora for EPEL')
        elif distro == Distro.CENTOS_7:
            # yum -y remove epel-release
            self.info(f"Disable {self.KEY.upper()} on CentOS 7")
            self.guest.execute(
                ShellScript(f'{sudo} yum -y remove {" ".join(CENTOS_7_PACKAGES)}'),
                silent=True)
        elif distro == Distro.CENTOS_STREAM_8:
            # dnf -y remove epel-release epel-next-release
            self.info(f"Disable {self.KEY.upper()} on CentOS Stream 8")
            self.guest.execute(
                ShellScript(f'{sudo} dnf -y remove {" ".join(FEDORA_PACKAGES)}'),
                silent=True)
        elif distro == Distro.CENTOS_STREAM_9:
            # dnf -y remove epel-release epel-next-release
            self.info(f"Disable {self.KEY.upper()} on CentOS Stream 9")
            self.guest.execute(
                ShellScript(f'{sudo} dnf -y remove {" ".join(FEDORA_PACKAGES)}'),
                silent=True)
        elif distro == Distro.RHEL_7:
            # dnf -y remove epel-release
            self.info(f"Disable {self.KEY.upper()} on RHEL 7")
            self.guest.execute(
                ShellScript(f'{sudo} yum -y remove epel-release'),
                silent=True)
        elif distro == Distro.RHEL_8:
            # dnf -y remove epel-release
            self.info(f"Disable {self.KEY.upper()} on RHEL 8")
            self.guest.execute(
                ShellScript(f'{sudo} dnf -y remove epel-release'),
                silent=True)
        elif distro == Distro.RHEL_9:
            # dnf -y remove epel-release
            self.info(f"Disable {self.KEY.upper()} on RHEL 9")
            self.guest.execute(
                ShellScript(f'{sudo} dnf -y remove epel-release'),
                silent=True)
        else:
            self.warn(f"Disable {self.KEY.upper()}: '{distro}' of the guest is unsupported.")


class CRB(ToggleableFeature):
    KEY = 'crb'

    def enable(self) -> None:
        distro = self.guest_distro
        sudo = self.guest_sudo

        if distro == Distro.RHEL_8:
            if self.guest_arch == 'x86_64':
                # subscription-manager repos --enable codeready-builder-for-rhel-8-x86_64-rpms
                self.info(f"Enable {self.KEY.upper()} on RHEL 8")
                self.guest.execute(
                    ShellScript(f"{sudo} subscription-manager "
                                f"repos --enable {' '.join(CRB_RHEL_8_REPO_X86_64)}"),
                    silent=True)
            else:
                self.warn(f"Disable {self.KEY.upper()}: '{self.guest_arch}' "
                          f"of the guest is unsupported.")
        else:
            self.warn(f"Enable {self.KEY.upper()}: '{distro}' of the guest is unsupported.")

    def disable(self) -> None:
        distro = self.guest_distro
        sudo = self.guest_sudo

        if distro == Distro.RHEL_8:
            if self.guest_arch == 'x86_64':
                # subscription-manager repos --disable codeready-builder-for-rhel-8-x86_64-rpms
                self.info(f"Disable {self.KEY.upper()} on RHEL 8")
                self.guest.execute(
                    ShellScript(f"{sudo} subscription-manager "
                                f"repos --disable {' '.join(CRB_RHEL_8_REPO_X86_64)}"),
                    silent=True)
            else:
                self.warn(f"Disable {self.KEY.upper()}: '{self.guest_arch}' "
                          f"of the guest is unsupported.")
        else:
            self.warn(f"Disable {self.KEY.upper()}: '{distro}' of the guest is unsupported.")


class FIPS(ToggleableFeature):
    KEY = 'fips'

    def enable(self) -> None:
        # Doc: https://access.redhat.com/documentation/en-us/red_hat_enterprise_linux/8/html/\
        #      security_hardening/using-the-system-wide-cryptographic-policies_security-hardening\
        #      #switching-the-system-to-fips-mode_using-the-system-wide-cryptographic-policies
        #
        # 1. To switch the system to FIPS mode:
        #    $ sudo fips-mode-setup --enable
        # 2. Restart the system to allow the kernel to switch to FIPS mode:
        #    $ sudo reboot
        # 3. After the restart, check the current state of FIPS mode via:
        #    $ sudo fips-mode-setup --check
        distro = self.guest_distro
        sudo = self.guest_sudo

        if distro == Distro.FEDORA:
            self.info(f"Enable {self.KEY.upper()} on Fedora")
        elif distro == Distro.RHEL_8:
            self.info(f"Enable {self.KEY.upper()} on RHEL 8")
            self.guest.execute(ShellScript(f'{sudo} fips-mode-setup --enable'), silent=True)
            self.info('reboot', 'Rebooting guest', color='yellow')
            self.guest.reboot()
            self.info('reboot', 'Reboot finished', color='yellow')
        else:
            self.warn(f"Enable {self.KEY.upper()}: '{distro}' of the guest is unsupported.")

    def disable(self) -> None:
        distro = self.guest_distro
        sudo = self.guest_sudo

        if distro == Distro.FEDORA:
            self.info(f"Disable {self.KEY.upper()} on Fedora")
        elif distro == Distro.RHEL_8:
            self.info(f"Disable {self.KEY.upper()} on RHEL 8")
            self.guest.execute(ShellScript(f'{sudo} fips-mode-setup --disable'), silent=True)
            self.info('reboot', 'Rebooting guest', color='yellow')
            self.guest.reboot()
            self.info('reboot', 'Reboot finished', color='yellow')
        else:
            self.warn(f"Disable {self.KEY.upper()}: '{distro}' of the guest is unsupported.")


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
    Enable common features such as epel, crb and fips on the guest

    Example config:

        prepare:
            how: feature
            epel: enabled
            crb: enabled
            fips: enabled

    ...<TBD>...
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
