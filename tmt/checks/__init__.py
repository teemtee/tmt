import enum
from typing import TYPE_CHECKING, Any, Callable, ClassVar, List, Optional, Type

import tmt.log
import tmt.steps.provision
import tmt.utils
from tmt.plugins import PluginRegistry

if TYPE_CHECKING:
    from tmt.base import Check
    from tmt.result import CheckResult
    from tmt.steps.execute import ExecutePlugin


CheckPluginClass = Type['CheckPlugin']


class CheckEvent(enum.Enum):
    """ Events in test runtime when a check can be executed """

    BEFORE_TEST = 'before-test'
    AFTER_TEST = 'after-test'

    @classmethod
    def from_spec(cls, spec: str) -> 'CheckEvent':
        try:
            return CheckEvent(spec)
        except ValueError:
            raise tmt.utils.SpecificationError(f"Invalid test check event '{spec}'.")


class CheckPlugin(tmt.utils._CommonBase):
    """ Base class for plugins providing extra checks before, during and after tests """

    _test_check_plugin_registry: ClassVar[PluginRegistry[CheckPluginClass]]

    # Keep this method around, to correctly support Python's method resolution order.
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

    # Cannot use @property as this must remain classmethod
    @classmethod
    def get_test_check_plugin_registry(cls) -> PluginRegistry[CheckPluginClass]:
        """ Return - or initialize - export plugin registry """

        if not hasattr(cls, '_test_check_plugin_registry'):
            cls._test_check_plugin_registry = PluginRegistry()

        return cls._test_check_plugin_registry

    @classmethod
    def provides_check(cls, check: str) -> Callable[[CheckPluginClass], CheckPluginClass]:
        """
        A decorator for registering test checks.

        Decorate a test check plugin class to register its checks.
        """

        def _provides_check(check_cls: CheckPluginClass) -> CheckPluginClass:
            cls.get_test_check_plugin_registry().register_plugin(
                plugin_id=check,
                plugin=check_cls,
                logger=tmt.log.Logger.get_bootstrap_logger())

            return check_cls

        return _provides_check

    @classmethod
    def before_test(
            cls,
            *,
            check: 'Check',
            plugin: 'ExecutePlugin',
            guest: tmt.steps.provision.Guest,
            test: 'tmt.base.Test',
            environment: Optional[tmt.utils.EnvironmentType] = None,
            logger: tmt.log.Logger) -> List['CheckResult']:
        return []

    @classmethod
    def after_test(
            cls,
            *,
            check: 'Check',
            plugin: 'ExecutePlugin',
            guest: tmt.steps.provision.Guest,
            test: 'tmt.base.Test',
            environment: Optional[tmt.utils.EnvironmentType] = None,
            logger: tmt.log.Logger) -> List['CheckResult']:
        return []
