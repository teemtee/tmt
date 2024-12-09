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


def find_plugin(name: str) -> 'FeatureClass':
    """
    Find a plugin by its name.

    :raises GeneralError: when the plugin does not exist.
    """

    plugin = _FEATURE_PLUGIN_REGISTRY.get_plugin(name)

    if plugin is None:
        raise tmt.utils.GeneralError(
            f"Feature plugin '{name}' was not found in the feature registry.")

    return plugin


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

    @classmethod
    def enable(cls, guest: Guest, logger: tmt.log.Logger) -> None:
        raise NotImplementedError

    @classmethod
    def disable(cls, guest: Guest, logger: tmt.log.Logger) -> None:
        raise NotImplementedError

    @classmethod
    def _find_playbook(cls, filename: str, logger: tmt.log.Logger) -> Optional[Path]:
        filepath = FEATURE_PLAYEBOOK_DIRECTORY / filename
        if filepath.exists():
            return filepath

        logger.warning(f"Cannot find any suitable playbook for '{filename}'.", 0)
        return None

    @classmethod
    def _run_playbook(
            cls,
            op: str,
            playbook_filename: str,
            guest: Guest,
            logger: tmt.log.Logger) -> None:
        playbook_path = cls._find_playbook(playbook_filename, logger)
        if not playbook_path:
            raise tmt.utils.GeneralError(
                f"{op.capitalize()} {cls.NAME.upper()} is not supported on this guest.")

        logger.info(f'{op.capitalize()} {cls.NAME.upper()}')
        guest.ansible(playbook_path)


@dataclasses.dataclass
class PrepareFeatureData(tmt.steps.prepare.PrepareStepData):
    # TODO: Change it to be able to create and discover custom fields to feature step data
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

        for plugin_id in _FEATURE_PLUGIN_REGISTRY.iter_plugin_ids():
            plugin = find_plugin(plugin_id)

            value = cast(Optional[str], getattr(self.data, plugin.NAME, None))
            if value is None:
                continue

            value = value.lower()
            if value == 'enabled':
                plugin.enable(guest, logger)
            elif value == 'disabled':
                plugin.disable(guest, logger)
            else:
                raise tmt.utils.GeneralError(f"Unknown plugin setting '{value}'.")

        return results

    def essential_requires(self) -> list[tmt.base.Dependency]:
        """
        Collect all essential requirements of the plugin.

        Essential requirements of a plugin are necessary for the plugin to
        perform its basic functionality.

        :returns: a list of requirements.
        """

        return tmt.steps.provision.essential_ansible_requires()
