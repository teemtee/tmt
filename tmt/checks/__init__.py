import dataclasses
import enum
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Type, TypedDict, cast

import tmt.log
import tmt.steps.provision
import tmt.utils
from tmt.plugins import PluginRegistry
from tmt.utils import (
    NormalizeKeysMixin,
    SerializableContainer,
    SpecBasedContainer,
    cached_property,
    field,
    )

if TYPE_CHECKING:
    from tmt.result import CheckResult
    from tmt.steps.execute import ExecutePlugin


CheckPluginClass = Type['CheckPlugin']

_CHECK_PLUGIN_REGISTRY: PluginRegistry[CheckPluginClass] = PluginRegistry()


def provides_check(check: str) -> Callable[[CheckPluginClass], CheckPluginClass]:
    """
    A decorator for registering test checks.

    Decorate a test check plugin class to register its checks.
    """

    def _provides_check(check_cls: CheckPluginClass) -> CheckPluginClass:
        _CHECK_PLUGIN_REGISTRY.register_plugin(
            plugin_id=check,
            plugin=check_cls,
            logger=tmt.log.Logger.get_bootstrap_logger())

        return check_cls

    return _provides_check


def find_plugin(name: str) -> 'CheckPluginClass':
    """
    Find a plugin by its name.

    :raises GeneralError: when the plugin does not exist.
    """

    plugin = _CHECK_PLUGIN_REGISTRY.get_plugin(name)

    if plugin is None:
        raise tmt.utils.GeneralError(
            f"Test check '{name}' was not found in check registry.")

    return plugin


# A "raw" test check as stored in fmf node data.
class _RawCheck(TypedDict, total=False):
    name: str
    enabled: bool


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


@dataclasses.dataclass
class Check(
        SpecBasedContainer[_RawCheck, _RawCheck],
        SerializableContainer,
        NormalizeKeysMixin):
    """
    Represents a single check from test's ``check`` field.

    Serves as a link between raw fmf/CLI specification and an actual
    check implementation/plugin.
    """

    name: str
    enabled: bool = field(default=True)

    @cached_property
    def plugin(self) -> 'CheckPluginClass':
        return find_plugin(self.name)

    # ignore[override]: expected, we need to accept one extra parameter, `logger`.
    @classmethod
    def from_spec(  # type: ignore[override]
            cls,
            raw_data: _RawCheck,
            logger: tmt.log.Logger) -> 'Check':
        data = cls(name=raw_data['name'])
        data._load_keys(cast(Dict[str, Any], raw_data), cls.__name__, logger)

        return data

    def to_spec(self) -> _RawCheck:
        return cast(_RawCheck, {
            tmt.utils.key_to_option(key): value
            for key, value in self.items()
            })

    def go(
            self,
            *,
            event: CheckEvent,
            guest: tmt.steps.provision.Guest,
            test: 'tmt.base.Test',
            plugin: 'tmt.steps.execute.ExecutePlugin',
            environment: Optional[tmt.utils.EnvironmentType] = None,
            logger: tmt.log.Logger) -> List['CheckResult']:
        """
        Run the check.

        :param event: when the check is running - before the test, after the test, etc.
        :param guest: on this guest the ``test`` will run/was executed.
        :param test: test to which the check belongs to.
        :param plugin: an ``execute`` step plugin managing the test execution.
        :param environment: optional environment to set for the check.
        :param logger: logger to use for logging.
        :returns: list of results produced by checks.
        """

        # TODO: there's "skipped" outcome brewing, we should use it once
        # it lands
        if not self.enabled:
            return []

        if event == CheckEvent.BEFORE_TEST:
            return self.plugin.before_test(
                check=self,
                plugin=plugin,
                guest=guest,
                test=test,
                environment=environment,
                logger=logger)

        if event == CheckEvent.AFTER_TEST:
            return self.plugin.after_test(
                check=self,
                plugin=plugin,
                guest=guest,
                test=test,
                environment=environment,
                logger=logger)

        raise tmt.utils.GeneralError(f"Unsupported test check event '{event}'.")


class CheckPlugin(tmt.utils._CommonBase):
    """ Base class for plugins providing extra checks before, during and after tests """

    _check_class: Type[Check] = Check

    # Keep this method around, to correctly support Python's method resolution order.
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

    @classmethod
    def delegate(
            cls,
            *,
            raw_data: _RawCheck,
            logger: tmt.log.Logger) -> Check:
        """ Create a check data instance for the plugin """

        return find_plugin(raw_data['name'])._check_class.from_spec(raw_data, logger)

    @classmethod
    def before_test(
            cls,
            *,
            check: Check,
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
            check: Check,
            plugin: 'ExecutePlugin',
            guest: tmt.steps.provision.Guest,
            test: 'tmt.base.Test',
            environment: Optional[tmt.utils.EnvironmentType] = None,
            logger: tmt.log.Logger) -> List['CheckResult']:
        return []


def normalize_test_check(
        key_address: str,
        raw_test_check: Any,
        logger: tmt.log.Logger) -> Check:
    """ Normalize a single test check """

    if isinstance(raw_test_check, str):
        try:
            return CheckPlugin.delegate(raw_data={'name': raw_test_check}, logger=logger)

        except Exception as exc:
            raise tmt.utils.SpecificationError(
                f"Cannot instantiate check from '{key_address}'.") from exc

    if isinstance(raw_test_check, dict):
        try:
            return CheckPlugin.delegate(
                raw_data=cast(_RawCheck, raw_test_check),
                logger=logger)

        except Exception as exc:
            raise tmt.utils.SpecificationError(
                f"Cannot instantiate check from '{key_address}'.") from exc

    raise tmt.utils.NormalizationError(
        key_address,
        raw_test_check,
        'a string or a dictionary')


def normalize_checks(
        key_address: str,
        raw_checks: Any,
        logger: tmt.log.Logger) -> List[Check]:
    """ Normalize (prepare/finish/test) checks """

    if raw_checks is None:
        return []

    if isinstance(raw_checks, str):
        return [normalize_test_check(key_address, raw_checks, logger)]

    if isinstance(raw_checks, dict):
        return [normalize_test_check(key_address, raw_checks, logger)]

    if isinstance(raw_checks, list):
        return [
            normalize_test_check(f'{key_address}[{i}]', raw_test_check, logger)
            for i, raw_test_check in enumerate(raw_checks)
            ]

    raise tmt.utils.NormalizationError(
        key_address,
        raw_checks,
        'a string, a dictionary, or a list of their combinations')
