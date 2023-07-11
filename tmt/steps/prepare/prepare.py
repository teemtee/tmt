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


class FeatureBase(tmt.utils.Common):
    """ Base class for feature implementations """

    def __init__(
            self,
            *,
            parent: tmt.steps.prepare.PreparePlugin,
            guest: Guest,
            logger: tmt.log.Logger) -> None:
        """ Initialize prepare data """
        super().__init__(logger=logger, parent=parent, relative_indent=0)
        self.guest = guest

    def get_system_release(self) -> Optional[str]:
        """ Get the release of the guest """
        self.debug('Get release of the guest.', level=2)
        command = Command()
        if self.guest.facts.is_superuser is False:
            command += Command('sudo')
        command += Command('cat', '/etc/system-release')
        user_output = self.guest.execute(command, silent=True)
        if user_output.stdout is None:
            return None

        # Parse file /etc/system-release to get the system release
        # e.g.
        #     1. Fedora  : Fedora release 36 (Thirty Six)                    ==> Fedora
        #     2. CentOS 7: CentOS Linux release 7.9.2009 (Core)              ==> CentOS-7
        #     3. RHEL 8  : Red Hat Enterprise Linux release 8.9 Beta (Ootpa) ==> RHEL-8
        #     4. RHEL 9  : Red Hat Enterprise Linux release 9.3 Beta (Plow)  ==> RHEL-9
        if re.search(r'Fedora release \d+', user_output.stdout):
            return 'Fedora'
        if re.search(r'CentOS Linux.*7\.?', user_output.stdout):
            return 'CentOS-7'
        if re.search(r'CentOS Stream.*8', user_output.stdout):
            return 'CentOS-Stream-8'
        if re.search(r'CentOS Stream.*9', user_output.stdout):
            return 'CentOS-Stream-9'
        if re.search(r'Red Hat Enterprise Linux.*\d+\.?', user_output.stdout):
            # RHEL-{7, 8, 9, ...}
            out = re.search(r'\d+\.?', user_output.stdout)
            if out is None:
                return None
            rhel_version = out.group().replace('.', '')
            return f'RHEL-{rhel_version}'
        return None

    def enable_epel(self) -> None:
        system_release = self.get_system_release()
        if system_release is None:
            raise tmt.utils.PrepareError('The system release of guest is not supported.')

        if system_release == 'Fedora':
            # XXX: What to do?
            self.info('enable epel on Fedora')
        elif system_release == 'CentOS-Stream-8':
            # dnf config-manager --set-enabled powertools
            # dnf install epel-release epel-next-release
            self.debug('Enable epel on CentOS Stream 8')
            command = Command()
            if self.guest.facts.is_superuser is False:
                command += Command('sudo')
            command1 = command + Command('dnf', 'config-manager', '--set-enabled', 'powertools')
            command2 = command + Command('dnf', '-y', 'install',
                                         'epel-release', 'epel-next-release')
            self.guest.execute(command1, silent=True)
            self.guest.execute(command2, silent=True)
        elif system_release == 'RHEL-8':
            # subscription-manager repos --enable codeready-builder-for-rhel-8-$(arch)-rpms
            # dnf install https://dl.fedoraproject.org/pub/epel/epel-release-latest-8.noarch.rpm
            self.debug('Enable epel on RHEL 8')
            command = Command()
            if self.guest.facts.is_superuser is False:
                command += Command('sudo')
            command1 = command + \
                Command('subscription-manager', 'repos', '--enable',
                        'codeready-builder-for-rhel-8-$(arch)-rpms')
            command2 = command + \
                Command('dnf', '-y', 'install',
                        'https://dl.fedoraproject.org/pub/epel/epel-release-latest-8.noarch.rpm')
        else:
            pass

    def disable_epel(self) -> None:
        system_release = self.get_system_release()
        if system_release is None:
            raise tmt.utils.PrepareError('The system release of guest is not supported.')

        if system_release == 'Fedora':
            # XXX: What to do?
            self.debug('Disable epel on Fedora')
        else:
            pass


@dataclasses.dataclass
class PrepareFeatureData(tmt.steps.prepare.PrepareStepData):
    epel: List[str] = field(
        default_factory=list,
        option=('-e', '--epel'),
        metavar='EPEL',
        multiple=True,
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
        """ Perform preparation for the guests """
        super().go(guest=guest, environment=environment, logger=logger)

        # Nothing to do in dry mode
        if self.opt('dry'):
            return

        # Enable epel
        epel_flag: bool = self.get('script')
        feature = FeatureBase(logger=logger, parent=self, guest=guest)
        if epel_flag:
            feature.enable_epel()
        else:
            feature.disable_epel()
