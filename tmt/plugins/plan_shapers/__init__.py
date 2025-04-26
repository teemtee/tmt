from collections.abc import Iterator
from typing import TYPE_CHECKING, Any, Callable

import tmt.log
import tmt.utils
from tmt.plugins import PluginRegistry

if TYPE_CHECKING:
    from tmt.base import Plan
    from tmt.options import ClickOptionDecoratorType
    from tmt.steps.discover import TestOrigin


PlanShaperClass = type['PlanShaper']


_PLAN_SHAPER_PLUGIN_REGISTRY: PluginRegistry[PlanShaperClass] = PluginRegistry('plan_shapers')


def provides_plan_shaper(shaper: str) -> Callable[[PlanShaperClass], PlanShaperClass]:
    """
    A decorator for registering plan shaper plugins.

    Decorate a plan shaper plugin class to register a plan shaper.
    """

    def _provides_plan_shaper(plan_shaper_cls: PlanShaperClass) -> PlanShaperClass:
        _PLAN_SHAPER_PLUGIN_REGISTRY.register_plugin(
            plugin_id=shaper, plugin=plan_shaper_cls, logger=tmt.log.Logger.get_bootstrap_logger()
        )

        return plan_shaper_cls

    return _provides_plan_shaper


class PlanShaper(tmt.utils.Common):
    """
    A base class for plan shaper plugins.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

    @classmethod
    def run_options(cls) -> list['ClickOptionDecoratorType']:
        """
        Return additional options for ``tmt run``.
        """

        raise NotImplementedError

    @classmethod
    def check(cls, plan: 'Plan', tests: list['TestOrigin']) -> bool:
        """
        Check whether this shaper should be applied to the given plan.

        :returns: ``True`` when the shaper would apply to the given plan.
        """

        raise NotImplementedError

    @classmethod
    def apply(cls, plan: 'Plan', tests: list['TestOrigin']) -> Iterator['Plan']:
        """
        Apply the shaper to a given plan and a set of tests.

        :returns: a sequence of plans replacing the original plan.
        """

        raise NotImplementedError
