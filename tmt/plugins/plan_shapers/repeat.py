import collections
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tmt.base import Plan, Test
    from tmt.options import ClickOptionDecoratorType
    from tmt.steps.discover import TestOrigin

from tmt.plugins.plan_shapers import PlanShaper, provides_plan_shaper


@provides_plan_shaper('repeat')
class RepeatPlanShaper(PlanShaper):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

    @classmethod
    def run_options(cls) -> list['ClickOptionDecoratorType']:
        from tmt.options import option

        return [
            option('--repeat', metavar='N', help='Repeat a plan N times.', type=int, default=-1)
        ]

    _inspected_plan_names: list[str] = []

    @classmethod
    def check(cls, plan: 'Plan', tests: list['TestOrigin']) -> bool:
        if not plan.my_run:
            return False

        repetitions = plan.my_run.opt('repeat')

        if repetitions <= 0:
            return False

        if plan.name in cls._inspected_plan_names:
            return False

        return True

    @classmethod
    def apply(cls, plan: 'Plan', tests: list['TestOrigin']) -> Iterator['Plan']:
        assert plan.my_run is not None

        if plan.name in cls._inspected_plan_names:
            return

        repetitions = plan.my_run.opt('repeat')

        plan.info(f'Repeating plan {repetitions} times.')

        batch: dict[str, list[Test]] = collections.defaultdict(list)

        for test_origin in tests:
            batch[test_origin.phase].append(test_origin.test)

        cls._inspected_plan_names.append(plan.name)

        for batch_id in range(1, repetitions + 1):
            derived_plan = plan.derive_plan(batch_id, batch)

            cls._inspected_plan_names.append(derived_plan.name)

            yield derived_plan
