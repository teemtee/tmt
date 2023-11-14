import dataclasses
import enum
import re
from pathlib import Path
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

    def get_guest_distro_id(self) -> Optional[str]:
        """ Get guest distro ID by parsing the guest facts """
        os_release = self.guest.facts.os_release_content
        if os_release is None:
            return None
        return os_release.get('ID', '')


class ToggleableFeature(Feature):
    def enable(self) -> None:
        raise NotImplementedError

    def disable(self) -> None:
        raise NotImplementedError


class EPEL(ToggleableFeature):
    KEY = 'epel'

    def enable(self) -> None:
        distro_name = cast(str, self.get_guest_distro_name())
        playbook_id = cast(str, self.get_guest_distro_id())
        playbook_dir = Path(__file__).parent / 'feature'
        playbook_path = playbook_dir / f"epel-enable-{playbook_id}.yaml"
        if not playbook_path.exists():
            self.warn(f"Enable {self.KEY.upper()}: '{distro_name}' of the guest is unsupported.")
            return
        self.info(f"Enable {self.KEY.upper()} on '{distro_name}' ...")
        print(playbook_path)
        # https://tmt.readthedocs.io/en/stable/classes.html#tmt.Guest.ansible
        # self.guest.ansible()

    def disable(self) -> None:
        pass


class CRB(ToggleableFeature):
    KEY = 'crb'

    def enable(self) -> None:
        pass

    def disable(self) -> None:
        pass


class FIPS(ToggleableFeature):
    KEY = 'fips'

    def enable(self) -> None:
        pass

    def disable(self) -> None:
        pass


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
