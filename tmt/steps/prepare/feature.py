import dataclasses
from typing import Optional, cast

import tmt
import tmt.base
import tmt.log
import tmt.options
import tmt.steps
import tmt.steps.prepare
import tmt.utils
from tmt.result import PhaseResult
from tmt.steps.provision import Guest
from tmt.utils import Path, field

FEATURE_PLAYEBOOK_DIRECTORY = tmt.utils.resource_files('steps/prepare/feature')


class Feature(tmt.utils.Common):
    """ Base class for ``feature`` prepare plugin implementations """

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
    def _run_playbook(self, op: str, playbook_filename: str) -> None:
        playbook_path = self._find_playbook(playbook_filename)
        if not playbook_path:
            raise tmt.utils.GeneralError(
                f"{op.capitalize()} {self.NAME.upper()} is not supported on this guest.")

        self.info(f'{op.capitalize()} {self.NAME.upper()}')
        self.guest.ansible(playbook_path)

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


_FEATURES: dict[str, type[Feature]] = {
    EPEL.NAME: EPEL
    }


@dataclasses.dataclass
class PrepareFeatureData(tmt.steps.prepare.PrepareStepData):
    epel: Optional[str] = field(
        default=None,
        option='--epel',
        metavar='enabled|disabled',
        help='Whether EPEL repository should be installed & enabled or disabled.'
        )


@tmt.steps.provides_method('feature')
class PrepareFeature(tmt.steps.prepare.PreparePlugin[PrepareFeatureData]):
    """
    Enable or disable common features like repositories on the guest.

    Example config:

    .. code-block:: yaml

        prepare:
            how: feature
            epel: enabled

    Or

    .. code-block:: yaml

        prepare:
            how: feature
            epel: disabled
    """

    _data_class = PrepareFeatureData

    def go(
            self,
            *,
            guest: 'Guest',
            environment: Optional[tmt.utils.Environment] = None,
            logger: tmt.log.Logger) -> list[PhaseResult]:
        """ Prepare the guests """
        results = super().go(guest=guest, environment=environment, logger=logger)

        # Nothing to do in dry mode
        if self.opt('dry'):
            return []

        # Enable or disable epel
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

        return results
