import dataclasses
from typing import Optional, cast

import tmt
import tmt.base
import tmt.log
import tmt.options
import tmt.steps
import tmt.steps.prepare
import tmt.utils
from tmt.steps.provision import Guest
from tmt.utils import Path, field


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

    def get_guest_distro_name(self) -> Optional[str]:
        """ Get guest distro name by parsing the guest facts """
        os_release = self.guest.facts.os_release_content
        if os_release is None:
            return None
        return os_release.get('PRETTY_NAME', None)


class ToggleableFeature(Feature):
    def get_root_path(self) -> Path:
        assert self.parent is not None  # narrow type
        assert self.parent.parent is not None  # narrow type
        assert self.parent.parent.parent is not None  # narrow type
        parent3 = cast(tmt.base.Plan, self.parent.parent.parent)
        assert parent3.my_run is not None  # narrow type
        assert parent3.my_run.tree is not None  # narrow type
        assert parent3.my_run.tree.root is not None  # narrow type
        return parent3.my_run.tree.root

    def _enable_or_disable_by_playbook(self, op: str, key: str, playbook: Path) -> None:
        distro_name = cast(str, self.get_guest_distro_name())
        if not playbook.exists():
            self.warn(f"{op} {key}: '{distro_name}' of the guest is unsupported.")
            return
        self.info(f"{op} {key} on '{distro_name}' ...")
        self.logger.info('playbook', playbook, 'green')
        self.guest.ansible(playbook.relative_to(self.get_root_path()))

    def enable_by_playbook(self, key: str, playbook: Path) -> None:
        self._enable_or_disable_by_playbook('Enable', key, playbook)

    def disable_by_playbook(self, key: str, playbook: Path) -> None:
        self._enable_or_disable_by_playbook('Disable', key, playbook)

    def enable(self) -> None:
        raise NotImplementedError

    def disable(self) -> None:
        raise NotImplementedError


class EPEL(ToggleableFeature):
    KEY = 'epel'

    def enable(self) -> None:
        playbook = Path(__file__).parent / 'feature/epel-enable.yaml'
        self.enable_by_playbook(self.KEY.upper(), playbook)

    def disable(self) -> None:
        playbook = Path(__file__).parent / 'feature/epel-disable.yaml'
        self.disable_by_playbook(self.KEY.upper(), playbook)


class CRB(ToggleableFeature):
    KEY = 'crb'

    def enable(self) -> None:
        playbook = Path(__file__).parent / 'feature/crb-enable.yaml'
        self.enable_by_playbook(self.KEY.upper(), playbook)

    def disable(self) -> None:
        playbook = Path(__file__).parent / 'feature/crb-disable.yaml'
        self.disable_by_playbook(self.KEY.upper(), playbook)


class FIPS(ToggleableFeature):
    KEY = 'fips'

    def enable(self) -> None:
        playbook = Path(__file__).parent / 'feature/fips-enable.yaml'
        self.enable_by_playbook(self.KEY.upper(), playbook)

    def disable(self) -> None:
        playbook = Path(__file__).parent / 'feature/fips-disable.yaml'
        self.disable_by_playbook(self.KEY.upper(), playbook)


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
class PrepareFeature(tmt.steps.prepare.PreparePlugin[PrepareFeatureData]):
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