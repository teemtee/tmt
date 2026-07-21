import collections
import itertools
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tmt.base.core import Test
    from tmt.base.plan import Plan
    from tmt.options import ClickOptionDecoratorType
    from tmt.steps.discover import TestOrigin

from tmt.plugins.plan_shapers import PlanShaper, provides_plan_shaper
from tmt.utils import EnvVarValue, Environment

MatrixCombination = dict[str, str]


def compute_combinations(
    variables: dict[str, list[str]],
) -> list[MatrixCombination]:
    """
    Compute the cartesian product of all matrix variables.
    """

    var_names = list(variables.keys())

    return [
        {name: value for name, value in zip(var_names, values)}
        for values in itertools.product(*variables.values())
    ]


def _stringify(value: Any) -> str:
    """
    Convert a YAML value to string, preserving lowercase for booleans.
    """

    if isinstance(value, bool):
        return 'true' if value else 'false'
    return str(value)


def parse_matrix(node_data: dict[str, Any]) -> dict[str, list[str]]:
    """
    Parse the ``matrix`` key from plan node data.

    :returns: a dict mapping variable names to their values.
    """

    matrix = node_data.get('matrix', {})

    return {
        key: [_stringify(v) for v in values] if isinstance(values, list) else [_stringify(values)]
        for key, values in matrix.items()
    }


def combination_name(combination: MatrixCombination) -> str:
    """
    Create a human-readable name from a matrix combination.
    """

    return '-'.join(combination.values())


def filter_combinations(
    combinations: list[MatrixCombination],
    filters: tuple[str, ...],
) -> list[MatrixCombination]:
    """
    Filter combinations by ``KEY=VALUE`` filters. All filters must match.
    """

    parsed: dict[str, str] = {}
    for f in filters:
        key, _, value = f.partition('=')
        parsed[key] = value

    return [
        combo for combo in combinations
        if all(combo.get(k) == v for k, v in parsed.items())
    ]


@provides_plan_shaper('matrix')
class MatrixPlanShaper(PlanShaper):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

    @classmethod
    def run_options(cls) -> list['ClickOptionDecoratorType']:
        from tmt.options import option
        return [
            option(
                '--matrix-filter',
                metavar='KEY=VALUE',
                help='Run only matrix combinations matching this filter. Can be specified multiple times.',
                multiple=True,
                default=(),
            )
        ]

    _inspected_plan_names: list[str] = []

    @classmethod
    def check(cls, plan: 'Plan', tests: list['TestOrigin']) -> bool:
        if plan.name in cls._inspected_plan_names:
            return False
        return bool(plan.node.data.get('matrix'))

    @classmethod
    def apply(cls, plan: 'Plan', tests: list['TestOrigin']) -> Iterator['Plan']:
        assert plan.my_run is not None

        if plan.name in cls._inspected_plan_names:
            return

        cls._inspected_plan_names.append(plan.name)

        variables = parse_matrix(plan.node.data)
        combinations = compute_combinations(variables)

        matrix_filters = plan.my_run.opt('matrix_filter') or ()
        if matrix_filters:
            combinations = filter_combinations(combinations, matrix_filters)

        plan.info(f'Expanding matrix into {len(combinations)} combinations.')

        batch: dict[str, list['Test']] = collections.defaultdict(list)
        for test_origin in tests:
            batch[test_origin.phase].append(test_origin.test)

        for combo in combinations:
            name = combination_name(combo)
            matrix_env = Environment({
                f'TMT_MATRIX_{key.upper()}': EnvVarValue(value)
                for key, value in combo.items()
            })
            derived_plan = plan.derive_plan(name, batch, extra_environment=matrix_env)

            cls._inspected_plan_names.append(derived_plan.name)
            yield derived_plan
