import itertools
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tmt.base import Plan, Test
    from tmt.options import ClickOptionDecoratorType
    from tmt.steps.discover import TestOrigin

from tmt.plugins.plan_shapers import PlanShaper, provides_plan_shaper


@provides_plan_shaper('max-tests')
class MaxTestsPlanShaper(PlanShaper):
    """
    Reshape a plan by limiting the number of tests in a plan.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

    @classmethod
    def run_options(cls) -> list['ClickOptionDecoratorType']:
        from tmt.options import option

        return [
            option(
                '--max',
                metavar='N',
                help='Split plans to include N tests at max.',
                type=int,
                default=-1,
            )
        ]

    @classmethod
    def check(cls, plan: 'Plan', tests: list['TestOrigin']) -> bool:
        if not plan.my_run:
            return False

        max_test_count = plan.my_run.opt('max')

        if max_test_count <= 0:
            return False

        if len(tests) <= max_test_count:
            return False

        return True

    @classmethod
    def apply(cls, plan: 'Plan', tests: list['TestOrigin']) -> Iterator['Plan']:
        # Prevent modification of caller's list.
        tests = tests[:]

        assert plan.my_run is not None

        max_test_per_batch = plan.my_run.opt('max')

        plan.info(f'Splitting plan to batches of {max_test_per_batch} tests.')

        for batch_id in itertools.count(1):
            if not tests:
                break

            batch: dict[str, list[Test]] = {}

            for _ in range(max_test_per_batch):
                if not tests:
                    break

                test_origin = tests.pop(0)

                if test_origin.phase not in batch:
                    batch[test_origin.phase] = [test_origin.test]

                else:
                    batch[test_origin.phase].append(test_origin.test)

            yield plan.derive_plan(batch_id, batch)
