import configparser
import dataclasses
import enum
import re
from typing import Dict, List, Optional, cast

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
    CENTOS_7 = enum.auto()
    CENTOS_STREAM_8 = enum.auto()
    CENTOS_STREAM_9 = enum.auto()
    RHEL_7 = enum.auto()
    RHEL_8 = enum.auto()
    RHEL_9 = enum.auto()


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
            if re.match(r'^8$|^8\.', os_release.get('VERSION_ID', '')):
                return Distro.CENTOS_STREAM_8
            if re.match(r'^9$|^9\.', os_release.get('VERSION_ID', '')):
                return Distro.CENTOS_STREAM_9

        return None

    def get_guest_distro_name(self) -> Optional[str]:
        """ Get guest distro name by parsing the guest facts """
        os_release = self.guest.facts.os_release_content
        if os_release is None:
            return None
        return os_release.get('PRETTY_NAME', None)


FEDORA_EPEL_PACKAGE = 'epel-release'
FEDORA_EPEL_NEXT_PACKAGE = 'epel-next-release'
YUM_UTILS_PACKAGE = 'yum-utils'
RHEL_7_EPEL_PACKAGE = 'https://dl.fedoraproject.org/pub/epel/epel-release-latest-7.noarch.rpm'
RHEL_8_EPEL_PACKAGE = 'https://dl.fedoraproject.org/pub/epel/epel-release-latest-8.noarch.rpm'
RHEL_9_EPEL_PACKAGE = 'https://dl.fedoraproject.org/pub/epel/epel-release-latest-9.noarch.rpm'
RHEL_8_EPEL_NEXT_PACKAGE = \
    'https://dl.fedoraproject.org/pub/epel/epel-next-release-latest-8.noarch.rpm'
RHEL_9_EPEL_NEXT_PACKAGE = \
    'https://dl.fedoraproject.org/pub/epel/epel-next-release-latest-9.noarch.rpm'

# Repos of epel and epel-next. For details, please refer to files in the following:
# 1) /etc/yum.repos.d/epel.repo
# 2) /etc/yum.repos.d/epel-next.repo
EPEL_REPOS = ['epel', 'epel-debuginfo', 'epel-source']
EPEL_NEXT_REPOS = ['epel-next', 'epel-next-debuginfo', 'epel-next-source']


class ToggleableFeature(Feature):
    def enable(self) -> None:
        raise NotImplementedError

    def disable(self) -> None:
        raise NotImplementedError

    def get_guest_repos(self) -> Optional[List[str]]:
        """ Get all repos on the guest """
        sudo = self.guest_sudo
        result = self.guest.execute(
            ShellScript(f"{sudo} cat /etc/yum.repos.d/*.repo"),
            silent=True)
        if result is None or result.stdout is None:
            return None
        repo_text = result.stdout
        config = configparser.ConfigParser()
        config.read_string(repo_text)
        return config.sections()


class EPEL(ToggleableFeature):
    KEY = 'epel'

    def get_repos_status(self, repos: List[str]) -> Optional[Dict[str, str]]:
        """ Get status of repos related to 'epel' """
        sudo = self.guest_sudo
        result = self.guest.execute(
            ShellScript(f"{sudo} cat /etc/yum.repos.d/*.repo"),
            silent=True)
        if result is None or result.stdout is None:
            return None

        repo_text = result.stdout
        config = configparser.ConfigParser()
        config.read_string(repo_text)
        repos_status: Dict[str, str] = {}
        for repo in repos:
            if config.has_option(repo, 'enabled'):
                option_value = config.get(repo, 'enabled')
                repos_status[repo] = 'disabled' if int(option_value) == 0 else 'enabled'
        return repos_status

    def check_repos_status(self, repos: List[str], status: str) -> None:
        repos_status = self.get_repos_status(repos)
        if repos_status is None:
            raise tmt.utils.GeneralError(f"Failed to get status of repos: {' '.join(repos)}.")
        for repo in repos:
            repo_status = repos_status.get(repo, None)
            if repo_status != status:
                raise tmt.utils.GeneralError(f"Repo {repo} is not {status} but {repo_status}.")
            self.info('Repo', f"{repo} is {status}.")

    def get_epel_source_packages(self) -> List[str]:
        """
        Source packages are more than one type. For instance, on CentOS 9 Stream,
        the 'epel-release' package is 'epel-release'. But on RHEL 9,
        the 'epel-release' package is 'https://.../epel-release-latest-9.noarch.rpm'.
        By default, we don't consider '*.rpm' packages.
        """
        return [FEDORA_EPEL_PACKAGE, FEDORA_EPEL_NEXT_PACKAGE]

    def get_epel_target_packages(self) -> List[str]:
        return [FEDORA_EPEL_PACKAGE, FEDORA_EPEL_NEXT_PACKAGE]

    def get_epel_repos(self) -> List[str]:
        return EPEL_REPOS + EPEL_NEXT_REPOS

    def get_epel_repos_to_disable(self) -> List[str]:
        repos_guest = self.get_guest_repos()
        if repos_guest is None:
            raise tmt.utils.GeneralError("Failed to get repos on the guest.")
        repos = self.get_epel_repos()
        repos2disable = set(repos).intersection(set(repos_guest))
        return list(repos2disable)

    def enable(self) -> None:
        epel_child = _EPEL_FEATURES.get(cast(Distro, self.guest_distro), None)
        if epel_child is None:
            distro_name = cast(str, self.guest_distro_name)
            self.warn(f"Enable {self.KEY.upper()}: '{distro_name}' of the guest is unsupported.")
            return
        feature = epel_child(parent=cast(PrepareFeature, self),
                             guest=self.guest,
                             logger=self.logger)
        feature.enable()

    def disable(self) -> None:
        """
        Just disable the repo because we don't know whether the packages related to epel
        was installed by user on purpose or not.
        """
        epel_child = _EPEL_FEATURES.get(cast(Distro, self.guest_distro), None)
        if epel_child is None:
            distro_name = cast(str, self.guest_distro_name)
            self.warn(f"Disable {self.KEY.upper()}: '{distro_name}' of the guest is unsupported.")
            return
        feature = epel_child(parent=cast(PrepareFeature, self),
                             guest=self.guest,
                             logger=self.logger)
        feature.disable()


class FedoraEPEL(EPEL):
    def enable(self) -> None:
        distro_name = cast(str, self.guest_distro_name)
        self.info(f"Enable {self.KEY.upper()}: nothing to do on {distro_name}.")

    def disable(self) -> None:
        distro_name = cast(str, self.guest_distro_name)
        self.info(f"Disable {self.KEY.upper()}: nothing to do on {distro_name}.")


class CentOS7EPEL(EPEL):
    def get_epel_source_packages(self) -> List[str]:
        # XXX: Utility 'yum-config-manager' is provided by package 'yum-utils'
        return [FEDORA_EPEL_PACKAGE, YUM_UTILS_PACKAGE]

    def get_epel_target_packages(self) -> List[str]:
        return [FEDORA_EPEL_PACKAGE, YUM_UTILS_PACKAGE]

    def get_epel_repos(self) -> List[str]:
        return EPEL_REPOS

    def enable(self) -> None:
        sudo = self.guest_sudo
        distro_name = cast(str, self.guest_distro_name)
        source_packages = self.get_epel_source_packages()
        target_packages = self.get_epel_target_packages()
        repos = self.get_epel_repos()

        self.info(f"Enable {self.KEY.upper()} on {distro_name}")
        self.guest.execute(
            ShellScript(f"""
                        set -x;
                        rpm -q {' '.join(source_packages)} || \
                            {sudo} yum -y install {' '.join(target_packages)};
                        {sudo} yum-config-manager --enable {' '.join(repos)}
                        """),
            silent=True)
        self.check_repos_status(repos, 'enabled')

    def disable(self) -> None:
        sudo = self.guest_sudo
        distro_name = cast(str, self.guest_distro_name)
        package = YUM_UTILS_PACKAGE

        repos = self.get_epel_repos_to_disable()
        if not repos:
            self.info(f"Disable {self.KEY.upper()} on {distro_name}: nothing to do!")
            return

        self.info(f"Disable {self.KEY.upper()} on {distro_name}")
        self.guest.execute(
            ShellScript(f"""
                        set -x;
                        rpm -q {package} || {sudo} yum -y install {package};
                        {sudo} yum-config-manager --disable {' '.join(repos)}
                        """),
            silent=True)
        self.check_repos_status(repos, 'disabled')


class RHEL7EPEL(CentOS7EPEL):
    def get_epel_source_packages(self) -> List[str]:
        return [RHEL_7_EPEL_PACKAGE, YUM_UTILS_PACKAGE]


class C8SEPEL(EPEL):
    def get_epel_source_packages(self) -> List[str]:
        # XXX: Some CentOS 8 Stream or RHEL 8 distros don't support 'dnf config-manager'. Hence,
        #      we have to use 'yum-config-manager' which is provided by package 'yum-utils'.
        return [FEDORA_EPEL_PACKAGE, FEDORA_EPEL_NEXT_PACKAGE, YUM_UTILS_PACKAGE]

    def get_epel_target_packages(self) -> List[str]:
        return [FEDORA_EPEL_PACKAGE, FEDORA_EPEL_NEXT_PACKAGE, YUM_UTILS_PACKAGE]

    def enable(self) -> None:
        sudo = self.guest_sudo
        distro_name = cast(str, self.guest_distro_name)
        target_packages = self.get_epel_target_packages()
        source_packages = self.get_epel_source_packages()
        repos = self.get_epel_repos()

        self.info(f"Enable {self.KEY.upper()} on {distro_name}")
        self.guest.execute(
            ShellScript(f"""
                        set -x;
                        rpm -q {' '.join(target_packages)} || \
                            {sudo} dnf -y install {' '.join(source_packages)};
                        {sudo} yum-config-manager --enable {' '.join(repos)};
                        """),
            silent=True)
        self.check_repos_status(repos, 'enabled')

    def disable(self) -> None:
        sudo = self.guest_sudo
        distro_name = cast(str, self.guest_distro_name)
        package = YUM_UTILS_PACKAGE

        repos = self.get_epel_repos_to_disable()
        if not repos:
            self.info(f"Disable {self.KEY.upper()} on {distro_name}: nothing to do!")
            return

        self.info(f"Disable {self.KEY.upper()} on {distro_name}")
        self.guest.execute(
            ShellScript(f"""
                        set -x;
                        rpm -q {package} || {sudo} dnf -y install {package};
                        {sudo} yum-config-manager --disable {' '.join(repos)}
                        """),
            silent=True)
        self.check_repos_status(repos, 'disabled')


class RHEL8EPEL(C8SEPEL):
    def get_epel_source_packages(self) -> List[str]:
        return [RHEL_8_EPEL_PACKAGE, RHEL_8_EPEL_NEXT_PACKAGE, YUM_UTILS_PACKAGE]


class C9SEPEL(EPEL):
    def enable(self) -> None:
        sudo = self.guest_sudo
        distro_name = cast(str, self.guest_distro_name)
        target_packages = self.get_epel_target_packages()
        source_packages = self.get_epel_source_packages()
        repos = self.get_epel_repos()
        self.info(f"Enable {self.KEY.upper()} on {distro_name}")
        self.guest.execute(
            ShellScript(f"""
                        set -x;
                        rpm -q {' '.join(target_packages)} || \
                            {sudo} dnf -y install {' '.join(source_packages)};
                        {sudo} dnf config-manager --enable {' '.join(repos)}
                        """),
            silent=True)
        self.check_repos_status(repos, 'enabled')

    def disable(self) -> None:
        sudo = self.guest_sudo
        distro_name = cast(str, self.guest_distro_name)

        repos = self.get_epel_repos_to_disable()
        if not repos:
            self.info(f"Disable {self.KEY.upper()} on {distro_name}: nothing to do!")
            return

        self.info(f"Disable {self.KEY.upper()} on {distro_name}")
        self.guest.execute(
            ShellScript(f"""
                        set -x;
                        {sudo} dnf config-manager --disable {' '.join(repos)}
                        """),
            silent=True)
        self.check_repos_status(repos, 'disabled')


class RHEL9EPEL(C9SEPEL):
    def get_epel_source_packages(self) -> List[str]:
        return [RHEL_9_EPEL_PACKAGE, RHEL_9_EPEL_NEXT_PACKAGE]


_EPEL_FEATURES = {
    Distro.FEDORA: FedoraEPEL,
    Distro.CENTOS_7: CentOS7EPEL,
    Distro.CENTOS_STREAM_8: C8SEPEL,
    Distro.CENTOS_STREAM_9: C9SEPEL,
    Distro.RHEL_7: RHEL7EPEL,
    Distro.RHEL_8: RHEL8EPEL,
    Distro.RHEL_9: RHEL9EPEL
    }


class CRB(ToggleableFeature):
    KEY = 'crb'

    def get_crp_repos(self) -> Optional[str]:
        distro = self.guest_distro
        if distro in (Distro.CENTOS_STREAM_8, Distro.CENTOS_STREAM_9):
            return 'crb'
        if distro in (Distro.RHEL_8, Distro.RHEL_9):
            return 'rhel-CRB'
        return None

    def enable(self) -> None:
        """
        Ensable CRB on the guest. Note that RHEL8, RHEL9, CentOS Stream 8 and CentOS Stream 9
        are supported.
        """
        distro = self.guest_distro
        sudo = self.guest_sudo

        key_name = self.KEY.upper()
        distro_name = cast(str, self.guest_distro_name)
        crb_repos = cast(str, self.get_crp_repos())

        if distro in (Distro.CENTOS_STREAM_8,
                      Distro.CENTOS_STREAM_9,
                      Distro.RHEL_8,
                      Distro.RHEL_9):
            self.info(f"Enable {key_name} on '{distro_name}'")
            self.guest.execute(
                ShellScript(f"""
                            set -x;
                            {sudo} dnf config-manager --enable {crb_repos}
                            """),
                silent=True)
        else:
            self.warn(f"Enable {key_name}: '{distro_name}' of the guest is unsupported.")

    def disable(self) -> None:
        """
        Disable CRB on the guest. Note that RHEL8, RHEL9, CentOS Stream 8 and CentOS Stream 9
        are supported.
        """
        distro = self.guest_distro
        sudo = self.guest_sudo

        key_name = self.KEY.upper()
        distro_name = cast(str, self.guest_distro_name)
        crb_repos = cast(str, self.get_crp_repos())

        if distro in (Distro.CENTOS_STREAM_8,
                      Distro.CENTOS_STREAM_9,
                      Distro.RHEL_8,
                      Distro.RHEL_9):
            self.info(f"Disable {key_name} on '{distro_name}'")
            self.guest.execute(
                ShellScript(f"""
                            set -x;
                            {sudo} dnf config-manager --disable {crb_repos}
                            """),
                silent=True)
        else:
            self.warn(f"Disable {key_name}: '{distro_name}' of the guest is unsupported.")


class FIPS(ToggleableFeature):
    KEY = 'fips'

    def _reboot_guest(self) -> None:
        self.info('reboot', 'Rebooting guest', color='yellow')
        self.guest.reboot()
        self.info('reboot', 'Reboot finished', color='yellow')

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

        if distro in (Distro.FEDORA,
                      Distro.RHEL_8,
                      Distro.RHEL_9,
                      Distro.CENTOS_STREAM_8,
                      Distro.CENTOS_STREAM_9):
            self.info(f"Enable {key_name} on '{distro_name}'")
            self.guest.execute(ShellScript(f'{sudo} fips-mode-setup --enable'), silent=True)
            self._reboot_guest()
        else:
            self.warn(f"Enable {key_name}: '{distro_name}' of the guest is unsupported.")

    def disable(self) -> None:
        distro = self.guest_distro
        sudo = self.guest_sudo

        key_name = self.KEY.upper()
        distro_name = cast(str, self.guest_distro_name)

        if distro in (Distro.FEDORA,
                      Distro.RHEL_8,
                      Distro.RHEL_9,
                      Distro.CENTOS_STREAM_8,
                      Distro.CENTOS_STREAM_9):
            self.info(f"Disable {key_name} on '{distro_name}'")
            self.guest.execute(ShellScript(f'{sudo} fips-mode-setup --disable'), silent=True)
            self._reboot_guest()
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
        option=('--epel'),
        metavar='<enabled|disabled>',
        help='epel to be enabled or disabled.'
        )

    crb: Optional[str] = field(
        default=None,
        option=('--crb'),
        metavar='<enabled|disabled>',
        help='crb to be enabled or disabled.'
        )

    fips: Optional[str] = field(
        default=None,
        option=('--fips'),
        metavar='<enabled|disabled>',
        help='fips to be enabled or disabled.'
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

        # XXX: Currently four provision methods in the following are supported:
        #      1) connect
        #      2) virtual
        #      3) container
        #      4) local
        if not isinstance(guest, (tmt.steps.provision.GuestSsh,
                                  tmt.steps.provision.testcloud.ProvisionTestcloud,
                                  tmt.steps.provision.podman.GuestContainer,
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
