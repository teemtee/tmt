import dataclasses
import re
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


class Feature(tmt.utils.Common):
    """ Base class for feature implementations """

    KEY: str

    def __init__(
            self,
            *,
            parent: tmt.steps.prepare.PreparePlugin,
            guest: Guest,
            logger: tmt.log.Logger) -> None:
        """ Initialize feature data """
        super().__init__(logger=logger, parent=parent, relative_indent=0)
        self.guest = guest

    def get_guest_distro(self, guest: Guest, logger: tmt.log.Logger) -> Optional[str]:
        """ Get guest distro by parsing the guest facts """
        distro = self.guest.facts.distro
        if distro is None:
            return None

        if re.search(r'Fedora Linux \d+', distro):
            return 'Fedora'
        if re.search(r'CentOS Linux.*7\.', distro):
            return 'CentOS-7'
        if re.search(r'CentOS Stream.*8', distro):
            return 'CentOS-Stream-8'
        if re.search(r'CentOS Stream.*9', distro):
            return 'CentOS-Stream-9'
        if re.search(r'Red Hat Enterprise Linux.*8\.', distro):
            return 'RHEL-8'
        if re.search(r'Red Hat Enterprise Linux.*9\.', distro):
            return 'RHEL-9'
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

        if guest_distro == 'Fedora':
            self.info('Enable EPEL on Fedora, do nothing ...')
        elif guest_distro == 'CentOS-Stream-8':
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
        elif guest_distro == 'RHEL-8':
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

        if guest_distro == 'Fedora':
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
