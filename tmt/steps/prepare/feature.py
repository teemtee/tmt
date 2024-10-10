import dataclasses
from typing import Callable, Optional, cast

import tmt
import tmt.base
import tmt.log
import tmt.options
import tmt.steps
import tmt.steps.prepare
import tmt.steps.provision
import tmt.utils
from tmt.plugins import PluginRegistry
from tmt.result import PhaseResult
from tmt.steps.provision import Guest
from tmt.utils import Path, field

FEATURE_PLAYEBOOK_DIRECTORY = tmt.utils.resource_files('steps/prepare/feature')

FeatureClass = type['Feature']
_FEATURE_PLUGIN_REGISTRY: PluginRegistry[FeatureClass] = PluginRegistry()


def provides_feature(
        feature: str) -> Callable[[FeatureClass], FeatureClass]:
    """
    A decorator for registering feature plugins.
    Decorate a feature plugin class to register a feature.
    """

    def _provides_feature(feature_cls: FeatureClass) -> FeatureClass:
        _FEATURE_PLUGIN_REGISTRY.register_plugin(
            plugin_id=feature,
            plugin=feature_cls,
            logger=tmt.log.Logger.get_bootstrap_logger())

        return feature_cls

    return _provides_feature


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

    def enable(self) -> None:
        raise NotImplementedError

    def disable(self) -> None:
        raise NotImplementedError

    def _find_playbook(self, filename: str) -> Optional[Path]:
        filepath = FEATURE_PLAYEBOOK_DIRECTORY / filename
        if filepath.exists():
            return filepath

        self.warn(f"Cannot find any suitable playbook for '{filename}'.")
        return None

    def _run_playbook(self, op: str, playbook_filename: str) -> None:
        playbook_path = self._find_playbook(playbook_filename)
        if not playbook_path:
            raise tmt.utils.GeneralError(
                f"{op.capitalize()} {self.NAME.upper()} is not supported on this guest.")

        self.info(f'{op.capitalize()} {self.NAME.upper()}')
        self.guest.ansible(playbook_path)


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

    .. warning::

       The plugin may be a subject of various limitations, imposed by
       the fact it uses Ansible to implement some of the features:

       * Ansible 2.17+ no longer supports Python 3.6 and older. Guests
         where Python 3.7+ is not available cannot be prepared with the
         ``feature`` plugin. This has been observed when Fedora Rawhide
         runner is used with CentOS 7 or CentOS Stream 8 guests. Possible
         workarounds: downgrade Ansible tmt uses, or install Python 3.7+
         before using ``feature`` plugin from an alternative repository
         or local build.

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

        print("### DEBUG IZMI ###")
        print(f"obsah registru: {list(_FEATURE_PLUGIN_REGISTRY.iter_plugins())}")
        print_value = cast(Optional[str], getattr(self.data, "epel", None))
        print(f"obsah value: {print_value}")

        for feature_id in _FEATURE_PLUGIN_REGISTRY.iter_plugin_ids():
            feature = _FEATURE_PLUGIN_REGISTRY.get_plugin(feature_id)

            assert feature is not None  # narrow type

            value = cast(Optional[str], getattr(self.data, feature.NAME, None))
            if value is None:
                continue
            if isinstance(feature, Feature):
                value = value.lower()
                if value == 'enabled':
                    feature.enable()
                elif value == 'disabled':
                    feature.disable()
                else:
                    raise tmt.utils.GeneralError(f"Unknown feature setting '{value}'.")

        return results

    def essential_requires(self) -> list[tmt.base.Dependency]:
        """
        Collect all essential requirements of the plugin.

        Essential requirements of a plugin are necessary for the plugin to
        perform its basic functionality.

        :returns: a list of requirements.
        """

        return tmt.steps.provision.essential_ansible_requires()
