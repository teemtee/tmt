import abc
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any, Callable

import tmt.utils
from tmt.plugins import PluginRegistry

if TYPE_CHECKING:
    from tmt.base import Plan
    from tmt.options import ClickOptionDecoratorType
    from tmt.steps.discover import TestOrigin


class PlanShaper(tmt.utils.Common):
    """
    A base class for plan shaper plugins.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

    @classmethod
    @abc.abstractmethod
    def run_options(cls) -> list['ClickOptionDecoratorType']:
        """
        Return additional options for ``tmt run``.
        """

        raise NotImplementedError

    @classmethod
    @abc.abstractmethod
    def check(cls, plan: 'Plan', tests: list['TestOrigin']) -> bool:
        """
        Check whether this shaper should be applied to the given plan.

        :returns: ``True`` when the shaper would apply to the given plan.
        """

        raise NotImplementedError

    @classmethod
    @abc.abstractmethod
    def apply(cls, plan: 'Plan', tests: list['TestOrigin']) -> Iterator['Plan']:
        """
        Apply the shaper to a given plan and a set of tests.

        :returns: a sequence of plans replacing the original plan.
        """

        raise NotImplementedError


_PLAN_SHAPER_PLUGIN_REGISTRY: PluginRegistry[type[PlanShaper]] = PluginRegistry('plan_shapers')

provides_plan_shaper: Callable[
    [str],
    Callable[[type[PlanShaper]], type[PlanShaper]],
] = _PLAN_SHAPER_PLUGIN_REGISTRY.create_decorator()
