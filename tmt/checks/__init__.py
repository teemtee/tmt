import dataclasses
import enum
import functools
from typing import TYPE_CHECKING, Any, Callable, Generic, Optional, TypedDict, TypeVar, cast

import tmt.log
import tmt.steps.provision
import tmt.utils
from tmt.plugins import PluginRegistry
from tmt.utils import (
    NormalizeKeysMixin,
    SerializableContainer,
    SpecBasedContainer,
    field,
    )

if TYPE_CHECKING:
    import tmt.base
    from tmt.result import CheckResult
    from tmt.steps.execute import TestInvocation
    from tmt.steps.provision import Guest


#: A type variable representing a :py:class:`Check` instances.
CheckT = TypeVar('CheckT', bound='Check')

CheckPluginClass = type['CheckPlugin[Any]']

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
class _RawCheck(TypedDict):
    how: str
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

    how: str
    enabled: bool = field(
        default=True,
        is_flag=True,
        help='Whether the check is enabled or not.')

    @functools.cached_property
    def plugin(self) -> 'CheckPluginClass':
        return find_plugin(self.how)

    # ignore[override]: expected, we need to accept one extra parameter, `logger`.
    @classmethod
    def from_spec(  # type: ignore[override]
            cls,
            raw_data: _RawCheck,
            logger: tmt.log.Logger) -> 'Check':
        data = cls(how=raw_data['how'])
        data._load_keys(cast(dict[str, Any], raw_data), cls.__name__, logger)

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
            invocation: 'TestInvocation',
            environment: Optional[tmt.utils.Environment] = None,
            logger: tmt.log.Logger) -> list['CheckResult']:
        """
        Run the check.

        :param event: when the check is running - before the test, after the test, etc.
        :param invocation: test invocation to which the check belongs to.
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
                invocation=invocation,
                environment=environment,
                logger=logger)

        if event == CheckEvent.AFTER_TEST:
            return self.plugin.after_test(
                check=self,
                invocation=invocation,
                environment=environment,
                logger=logger)

        raise tmt.utils.GeneralError(f"Unsupported test check event '{event}'.")


class CheckPlugin(tmt.utils._CommonBase, Generic[CheckT]):
    """ Base class for plugins providing extra checks before, during and after tests """

    _check_class: type[CheckT]

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

        return cast(CheckPlugin[CheckT], find_plugin(raw_data['how'])) \
            ._check_class.from_spec(raw_data, logger)

    @classmethod
    def essential_requires(
            cls,
            guest: 'Guest',
            test: 'tmt.base.Test',
            logger: tmt.log.Logger) -> list['tmt.base.DependencySimple']:
        """
        Collect all essential requirements of the test check.

        Essential requirements of a check are necessary for the check to
        perform its basic functionality.

        :returns: a list of requirements.
        """

        return []

    @classmethod
    def before_test(
            cls,
            *,
            check: CheckT,
            invocation: 'TestInvocation',
            environment: Optional[tmt.utils.Environment] = None,
            logger: tmt.log.Logger) -> list['CheckResult']:
        return []

    @classmethod
    def after_test(
            cls,
            *,
            check: CheckT,
            invocation: 'TestInvocation',
            environment: Optional[tmt.utils.Environment] = None,
            logger: tmt.log.Logger) -> list['CheckResult']:
        return []


def normalize_test_check(
        key_address: str,
        raw_test_check: Any,
        logger: tmt.log.Logger) -> Check:
    """ Normalize a single test check """

    if isinstance(raw_test_check, str):
        try:
            return CheckPlugin.delegate(
                raw_data={'how': raw_test_check, 'enabled': True},
                logger=logger)

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


def normalize_test_checks(
        key_address: str,
        raw_checks: Any,
        logger: tmt.log.Logger) -> list[Check]:
    """ Normalize (prepare/finish/test) checks """

    if raw_checks is None:
        return []

    if isinstance(raw_checks, str):
        return [normalize_test_check(key_address, raw_checks, logger)]

    if isinstance(raw_checks, dict):
        return [normalize_test_check(key_address, raw_checks, logger)]

    if isinstance(raw_checks, list):
        # ignore[redundant-cast]: mypy infers the type to be `list[Any]` while
        # pyright, not making assumptions about the type of items, settles for
        # `list[Unknown]`. The `cast()` helps pyright, but mypy complains.
        return [
            normalize_test_check(f'{key_address}[{i}]', raw_test_check, logger)
            for i, raw_test_check in enumerate(
                cast(list[Any], raw_checks))  # type: ignore[redundant-cast]
            ]

    raise tmt.utils.NormalizationError(
        key_address,
        raw_checks,
        'a string, a dictionary, or a list of their combinations')
