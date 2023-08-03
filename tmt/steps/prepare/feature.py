import dataclasses
import enum
from typing import List, Optional

import tmt
import tmt.base
import tmt.log
import tmt.options
import tmt.steps
import tmt.steps.prepare
import tmt.utils
from tmt.steps.provision import Guest
from tmt.utils import Command, field


class Distro(enum.Enum):
    FEDORA = enum.auto()
    RHEL_7 = enum.auto()
    RHEL_8 = enum.auto()
    RHEL_9 = enum.auto()
    RHEL_10 = enum.auto()
    CENTOS_LINUX_7 = enum.auto()
    CENTOS_STREAM_8 = enum.auto()
    CENTOS_STREAM_9 = enum.auto()
    CENTOS_STREAM_10 = enum.auto()


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

    def get_guest_distro(self, guest: Guest, logger: tmt.log.Logger) -> Optional[Distro]:
        """ Get guest distro by parsing the guest facts """
        os_release = guest.facts.os_release_content
        if os_release is None:
            return None

        if os_release.get('NAME') == 'Fedora Linux':
            return Distro.FEDORA

        if os_release.get('NAME') == 'Red Hat Enterprise Linux':
            if os_release.get('VERSION_ID', '').startswith('9'):
                return Distro.RHEL_9
            if os_release.get('VERSION_ID', '').startswith('8'):
                return Distro.RHEL_8
            if os_release.get('VERSION_ID', '').startswith('7'):
                return Distro.RHEL_7

        if os_release.get('NAME') == 'CentOS Linux' and os_release.get(
                'VERSION_ID', '').startswith('7'):
            return Distro.CENTOS_LINUX_7

        if os_release.get('NAME') == 'CentOS Stream':
            if os_release.get('VERSION_ID', '').startswith('8'):
                return Distro.CENTOS_STREAM_8
            if os_release.get('VERSION_ID', '').startswith('9'):
                return Distro.CENTOS_STREAM_9

        return None


class ToggleableFeature(Feature):
    def enable(self, guest: Guest, logger: tmt.log.Logger) -> None:
        raise NotImplementedError

    def disable(self, guest: Guest, logger: tmt.log.Logger) -> None:
        raise NotImplementedError


class CRB(ToggleableFeature):
    KEY = 'crb'
    # TBD


class FIPS(ToggleableFeature):
    KEY = 'fips'
    # TBD


class EPEL(ToggleableFeature):
    KEY = 'epel'

    def enable(self, guest: Guest, logger: tmt.log.Logger) -> None:
        guest_distro = self.get_guest_distro(guest=guest, logger=logger)
        if guest_distro is None:
            raise tmt.utils.PrepareError('The distro of the guest is not supported.')

        if guest_distro == Distro.FEDORA:
            self.info('Enable EPEL on Fedora, do nothing ...')
        elif guest_distro == Distro.CENTOS_STREAM_8:
            # dnf config-manager --set-enabled powertools
            # dnf install epel-release epel-next-release
            self.info('Enable EPEL on CentOS Stream 8')
            command = Command()
            if self.guest.facts.is_superuser is False:
                command += Command('sudo')
            command1 = command + Command('dnf', 'config-manager', '--set-enabled', 'powertools')
            command2 = command + Command('dnf', '-y', 'install',
                                         'epel-release', 'epel-next-release')
            self.guest.execute(command1, silent=True)
            self.guest.execute(command2, silent=True)
        elif guest_distro == Distro.RHEL_8:
            # subscription-manager repos --enable codeready-builder-for-rhel-8-$(arch)-rpms
            # dnf install https://dl.fedoraproject.org/pub/epel/epel-release-latest-8.noarch.rpm
            self.info('Enable EPEL on RHEL 8')
            command = Command()
            if self.guest.facts.is_superuser is False:
                command += Command('sudo')
            command1 = command + \
                Command('subscription-manager', 'repos', '--enable',
                        'codeready-builder-for-rhel-8-$(arch)-rpms')
            command2 = command + \
                Command('dnf', '-y', 'install',
                        'https://dl.fedoraproject.org/pub/epel/epel-release-latest-8.noarch.rpm')
            self.guest.execute(command1, silent=True)
            self.guest.execute(command2, silent=True)
        else:
            raise tmt.utils.PrepareError('The distro of the guest is not supported.')

    def disable(self, guest: Guest, logger: tmt.log.Logger) -> None:
        guest_distro = self.get_guest_distro(guest=guest, logger=logger)
        if guest_distro is None:
            raise tmt.utils.PrepareError('The distro of the guest is not supported.')

        if guest_distro == Distro.FEDORA:
            # XXX: What to do?
            self.info('Disable epel on Fedora, do nothing ...')
        else:
            pass


_FEATURES = {
    EPEL.KEY: EPEL,
    CRB.KEY: CRB,
    FIPS.KEY: FIPS
    }


@dataclasses.dataclass
class PrepareFeatureData(tmt.steps.prepare.PrepareStepData):
    epel: List[str] = field(
        default_factory=list,
        option=('-e', '--epel'),
        metavar='EPEL',
        multiple=False,
        help='epel to be enabled.',
        normalize=tmt.utils.normalize_string_list
        )


@tmt.steps.provides_method('feature')
class PrepareFeature(tmt.steps.prepare.PreparePlugin):
    """
    Enable common features such as epel, crb and fips on the guest

    Example config:

        prepare:
            how: feature
            epel: enabled

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

        # Enable epel/crb/fips
        for key, value in self.data.items():
            # PrepareFeatureData(name='default-0',
            #                    how='feature',
            #                    order=50,
            #                    summary=None,
            #                    where=[],
            #                    epel=['enabled'])
            if key in ['name', 'how', 'order', 'summary', 'where']:
                continue

            if key not in _FEATURES:
                raise tmt.utils.GeneralError("Unknown key")

            feature = _FEATURES[key](parent=self, guest=guest, logger=logger)
            if isinstance(feature, ToggleableFeature):
                if isinstance(value, str):
                    value = value.lower()
                elif isinstance(value, list):
                    value = value[0].lower()
                else:
                    raise tmt.utils.GeneralError("Bad value")
            if value == 'enabled':
                feature.enable(guest=guest, logger=logger)
            elif value == 'disabled':
                feature.disable(guest=guest, logger=logger)
            else:
                raise tmt.utils.GeneralError("Unknown method")
