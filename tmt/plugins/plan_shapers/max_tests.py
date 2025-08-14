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
        from tmt.options import Deprecated, option

        return [
            option(
                '--max-tests-per-plan',
                metavar='N',
                envvar='TMT_RUN_MAX_TESTS_PER_PLAN',
                help='Split every plan to include N tests at maximum.',
                type=int,
                default=-1,
            ),
            option(
                '--max',
                metavar='N',
                help='Split every plan to include N tests at maximum.',
                type=int,
                default=-1,
                deprecated=Deprecated('1.55', hint='use ``--max-tests-per-plan`` instead'),
            ),
        ]

    @classmethod
    def check(cls, plan: 'Plan', tests: list['TestOrigin']) -> bool:
        if not plan.my_run:
            return False

        # Check new option first, fall back to deprecated option
        max_test_count = plan.my_run.opt('max-tests-per-plan')
        if max_test_count <= 0:
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

        # Check new option first, fall back to deprecated option
        max_test_per_batch = plan.my_run.opt('max-tests-per-plan')
        if max_test_per_batch <= 0:
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
