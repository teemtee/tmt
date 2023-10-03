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

    def get_epel_packages(self) -> Optional[str]:
        if self.guest_distro in (Distro.FEDORA,
                                 Distro.CENTOS_STREAM_8,
                                 Distro.CENTOS_STREAM_9):
            return ' '.join([FEDORA_EPEL_PACKAGE, FEDORA_EPEL_NEXT_PACKAGE])
        if self.guest_distro == Distro.CENTOS_7:
            return FEDORA_EPEL_PACKAGE
        if self.guest_distro == Distro.RHEL_7:
            return RHEL_7_EPEL_PACKAGE
        if self.guest_distro == Distro.RHEL_8:
            return ' '.join([RHEL_8_EPEL_PACKAGE, RHEL_8_EPEL_NEXT_PACKAGE])
        if self.guest_distro == Distro.RHEL_9:
            return ' '.join([RHEL_9_EPEL_PACKAGE, RHEL_9_EPEL_NEXT_PACKAGE])
        return None

    def get_epel_repos(self) -> Optional[str]:
        if self.guest_distro in (Distro.CENTOS_7,
                                 Distro.RHEL_7):
            return ' '.join(EPEL_REPOS)
        if self.guest_distro in (Distro.CENTOS_STREAM_8,
                                 Distro.CENTOS_STREAM_9,
                                 Distro.RHEL_8,
                                 Distro.RHEL_9):
            return ' '.join(EPEL_REPOS + EPEL_NEXT_REPOS)
        return None


class EPEL(ToggleableFeature):
    KEY = 'epel'

    def _get_repos_status(self, repos: List[str]) -> Optional[Dict[str, str]]:
        distro = self.guest_distro
        sudo = self.guest_sudo

        pkg_mgr = 'yum' if distro in (Distro.CENTOS_7, Distro.RHEL_7) else 'dnf'
        result = self.guest.execute(
            ShellScript(f"{sudo} {pkg_mgr} repolist --all {' '.join(repos)}"),
            silent=True)
        if result is None or result.stdout is None:
            return None

        repo_status: Dict[str, str] = {}
        for line in result.stdout.split('\n'):
            line = line.strip()
            if not line:
                continue
            repo, *_, status = line.split()
            if repo in repos:
                repo_status[repo] = status
        return repo_status

    def _check_repos_status(self, repos: List[str], status: str) -> None:
        repos_status = self._get_repos_status(repos)
        if repos_status is None:
            raise tmt.utils.GeneralError(f"Failed to get status of repos {' '.join(repos)}.")

        for repo in repos:
            repo_status = repos_status.get(repo)
            if repo_status != status:
                raise tmt.utils.GeneralError(f"Repo {repo} is not {status} but {repo_status}.")
            self.info(f"Repo {repo} is {status}")

    def enable(self) -> None:
        distro = self.guest_distro
        sudo = self.guest_sudo

        key_name = self.KEY.upper()
        distro_name = cast(str, self.guest_distro_name)
        epel_packages = cast(str, self.get_epel_packages())
        epel_repos = cast(str, self.get_epel_repos())
        if distro == Distro.FEDORA:
            self.info(f"Nothing to do on {distro_name} for {key_name}")
        elif distro in (Distro.CENTOS_7, Distro.RHEL_7):
            self.info(f"Enable {key_name} on {distro_name}")
            self.guest.execute(
                ShellScript(f"""
                            set -x;
                            rpm -q {epel_packages} || {sudo} yum -y install {epel_packages};
                            rpm -q yum-utils || {sudo} yum install -y yum-utils;
                            {sudo} yum-config-manager --enable {epel_repos};
                            """),
                silent=True)
            self._check_repos_status(epel_repos.split(), 'enabled')
        elif distro in (Distro.CENTOS_STREAM_8,
                        Distro.CENTOS_STREAM_9,
                        Distro.RHEL_8,
                        Distro.RHEL_9):
            self.info(f"Enable {key_name} on {distro_name}")
            self.guest.execute(
                ShellScript(f"""
                            set -x;
                            rpm -q {epel_packages} || {sudo} dnf -y install {epel_packages};
                            {sudo} dnf config-manager --enable {epel_repos};
                            """),
                silent=True)
            self._check_repos_status(epel_repos.split(), 'enabled')
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
        epel_repos = cast(str, self.get_epel_repos())
        if distro == Distro.FEDORA:
            self.info(f"Nothing to do on {distro_name} for {key_name}")
        elif distro in (Distro.RHEL_7,
                        Distro.CENTOS_7):
            self.info(f"Disable {key_name} on {distro_name}")
            self.guest.execute(
                ShellScript(f"""
                            set -x;
                            rpm -q yum-utils || {sudo} yum install -y yum-utils;
                            {sudo} yum-config-manager --disable {epel_repos}
                            """),
                silent=True)
            self._check_repos_status(epel_repos.split(), 'disabled')
        elif distro in (Distro.RHEL_8,
                        Distro.RHEL_9,
                        Distro.CENTOS_STREAM_8,
                        Distro.CENTOS_STREAM_9):
            self.info(f"Disable {key_name} on {distro_name}")
            self.guest.execute(
                ShellScript(f"""
                            set -x;
                            {sudo} dnf config-manager --disable {epel_repos}
                            """),
                silent=True)
            self._check_repos_status(epel_repos.split(), 'disabled')
        else:
            self.warn(f"Disable {key_name}: '{distro_name}' of the guest is unsupported.")


class CRB(ToggleableFeature):
    KEY = 'crb'

    def get_epel_packages(self) -> Optional[str]:
        """
        Override the method of its parent class because command 'crb' is from package
        'epel-release'.
        """

        if self.guest_distro in (Distro.FEDORA,
                                 Distro.CENTOS_7,
                                 Distro.CENTOS_STREAM_8,
                                 Distro.CENTOS_STREAM_9):
            return FEDORA_EPEL_PACKAGE
        if self.guest_distro == Distro.RHEL_7:
            return RHEL_7_EPEL_PACKAGE
        if self.guest_distro == Distro.RHEL_8:
            return RHEL_8_EPEL_PACKAGE
        if self.guest_distro == Distro.RHEL_9:
            return RHEL_9_EPEL_PACKAGE
        return None

    def enable(self) -> None:
        """
        Ensable CRB on the guest. Note that:
        1) RHEL8, RHEL9, CentOS Stream 8 and CentOS Stream 9 are supported;
        2) Package 'epel-release' should be installed because command 'crb' is from it.
        """

        distro = self.guest_distro
        sudo = self.guest_sudo

        key_name = self.KEY.upper()
        distro_name = cast(str, self.guest_distro_name)
        epel_packages = cast(str, self.get_epel_packages())

        if distro in (Distro.CENTOS_STREAM_8,
                      Distro.CENTOS_STREAM_9,
                      Distro.RHEL_8,
                      Distro.RHEL_9):
            self.info(f"Enable {key_name} on '{distro_name}'")
            self.guest.execute(
                ShellScript(f"""
                            set -x;
                            rpm -q {epel_packages} || {sudo} dnf -y install {epel_packages};
                            {sudo} /usr/bin/crb enable
                            """),
                silent=True)
        else:
            self.warn(f"Enable {key_name}: '{distro_name}' of the guest is unsupported.")

    def disable(self) -> None:
        """
        Disable CRB on the guest. Note that RHEL8, RHEL9, CentOS Stream 8 and
        CentOS Stream 9 are supported.
        """
        distro = self.guest_distro
        sudo = self.guest_sudo

        key_name = self.KEY.upper()
        distro_name = cast(str, self.guest_distro_name)
        epel_packages = cast(str, self.get_epel_packages())

        if distro in (Distro.CENTOS_STREAM_8,
                      Distro.CENTOS_STREAM_9,
                      Distro.RHEL_8,
                      Distro.RHEL_9):
            self.info(f"Disable {key_name} on '{distro_name}'")
            self.guest.execute(
                ShellScript(f"""
                            set -x;
                            rpm -q {epel_packages} || {sudo} dnf -y install {epel_packages};
                            {sudo} /usr/bin/crb disable
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

        # XXX: Currently three provision methods in the following are supported:
        #      1) connect
        #      2) virtual
        #      3) container
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
