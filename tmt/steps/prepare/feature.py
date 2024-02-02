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

FEATURE_PLAYEBOOK_DIRECTORY = tmt.utils.resource_files('steps/prepare/feature')


class Feature(tmt.utils.Common):
    """ Base class for feature implementations """

    NAME: str

    def __init__(
            self,
            *,
            parent: 'PrepareFeature',
            guest: Guest,
            logger: tmt.log.Logger) -> None:
        """ Initialize feature data """
        super().__init__(logger=logger, parent=parent, relative_indent=0)

        self.guest = guest

    def _find_playbook(self, filename: str) -> Optional[Path]:
        filepath = FEATURE_PLAYEBOOK_DIRECTORY / filename

        if filepath.exists():
            return filepath

        self.warn(f"Cannot find any suitable playbook for '{filename}'.")

        return None


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

    def _run_playbook(self, op: str, playbook_filename: str) -> None:
        playbook_path = self._find_playbook(playbook_filename)

        if not playbook_path:
            self.warn(f'{op.capitalize()} {self.NAME.upper()} is not supported on this guest.')
            return

        self.info(f'{op.capitalize()} {self.NAME.upper()}')

        self.guest.ansible(playbook_path.relative_to(self.get_root_path()))

    def _enable(self, playbook_filename: str) -> None:
        self._run_playbook('enable', playbook_filename)

    def _disable(self, playbook_filename: str) -> None:
        self._run_playbook('disable', playbook_filename)

    def enable(self) -> None:
        raise NotImplementedError

    def disable(self) -> None:
        raise NotImplementedError


class EPEL(ToggleableFeature):
    NAME = 'epel'

    def enable(self) -> None:
        self._enable('epel-enable.yaml')

    def disable(self) -> None:
        self._disable('epel-disable.yaml')


class CRB(ToggleableFeature):
    NAME = 'crb'

    def enable(self) -> None:
        self._enable('crb-enable.yaml')

    def disable(self) -> None:
        self._disable('crb-disable.yaml')


class FIPS(ToggleableFeature):
    NAME = 'fips'

    def enable(self) -> None:
        self._enable('fips-enable.yaml')

    def disable(self) -> None:
        self._disable('fips-disable.yaml')


_FEATURES: dict[str, type[Feature]] = {
    EPEL.NAME: EPEL,
    CRB.NAME: CRB,
    FIPS.NAME: FIPS
    }


@dataclasses.dataclass
class PrepareFeatureData(tmt.steps.prepare.PrepareStepData):
    epel: Optional[str] = field(
        default=None,
        option='--epel',
        metavar='enabled|disabled',
        help='Whether EPEL repository should be installed & enabled or disabled.'
        )

    crb: Optional[str] = field(
        default=None,
        option='--crb',
        metavar='enabled|disabled',
        help='Whether CRB repository should be enabled or disabled.'
        )

    fips: Optional[str] = field(
        default=None,
        option='--fips',
        metavar='enabled|disabled',
        help='Whether FIPS should be enabled or disabled.'
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

        # Enable or disable epel/crb/fips
        for feature_key in _FEATURES:
            value = cast(Optional[str], getattr(self.data, feature_key, None))

            if value is None:
                continue

            feature = _FEATURES[feature_key](parent=self, guest=guest, logger=logger)

            if isinstance(feature, ToggleableFeature):
                value = value.lower()

                if value == 'enabled':
                    feature.enable()

                elif value == 'disabled':
                    feature.disable()

                else:
                    raise tmt.utils.GeneralError(f"Unknown feature setting '{value}'.")

            else:
                raise tmt.utils.GeneralError(f"Unsupported feature '{feature_key}'.")
