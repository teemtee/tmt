from typing import TYPE_CHECKING, Any, Optional, cast

import tmt.utils
from tmt.container import SerializableContainer, container, field
from tmt.log import Logger
from tmt.steps import Login, Step, StepData
from tmt.steps.discover import Discover
from tmt.steps.execute import Execute
from tmt.utils import Common, Environment, FmfContext, Path

if TYPE_CHECKING:
    import tmt.base
    from tmt.base import Plan, RunData, Test, _RawAdjustRule


# TODO: this is a duplication of tmt.base.DEFAULT_ORDER.
DEFAULT_ORDER = 50


def _get_step(plan: 'Plan', step_name: str) -> '_Step':
    step = getattr(plan, step_name)
    if isinstance(step, Discover):
        return _DiscoverStep(
            phases=cast(Step, step).data, tests=[test_origin.test for test_origin in step.tests()]
        )
    if isinstance(step, Execute):
        return _ExecuteStep(
            phases=cast(Step, step).data,
            results_path=(step.step_workdir / 'results.yaml').relative_to(step.run_workdir),
        )
    if isinstance(step, Step):
        return _Step(phases=step.data)

    raise ValueError(f"Step '{step_name}' is not defined in plan '{plan.name}'")


def _serialize_tests(tests: list['Test']) -> list[dict[str, Any]]:
    serialized_tests: list[dict[str, Any]] = []
    for test in tests:
        serialized_test = test._export(include_internal=True)
        # Replace the modified environment with the original one
        serialized_test['environment'] = test._original_fmf_environment.to_fmf_spec()
        serialized_tests.append(serialized_test)
    return serialized_tests


@container
class _Step(SerializableContainer):
    phases: list[StepData] = field(
        default_factory=list[StepData],
        serialize=lambda value: [phase.to_serialized() for phase in value],
    )


@container
class _DiscoverStep(_Step):
    tests: list['Test'] = field(default_factory=list['Test'], serialize=_serialize_tests)


@container
class _ExecuteStep(_Step):
    results_path: Optional[Path] = field(
        default=None,
        normalize=tmt.utils.normalize_path,
        exporter=lambda value: str(value) if isinstance(value, Path) else None,
        serialize=lambda value: str(value) if isinstance(value, Path) else None,
        unserialize=lambda value: Path(value) if value is not None else None,
    )


@container
class _RecipePlan(SerializableContainer):
    name: str
    summary: Optional[str] = None
    description: Optional[str] = None
    author: list[str] = field(
        default_factory=list,
        normalize=tmt.utils.normalize_string_list,
    )
    contact: list[str] = field(
        default_factory=list,
        normalize=tmt.utils.normalize_string_list,
    )
    enabled: bool = True
    order: int = field(
        default=DEFAULT_ORDER,
        normalize=lambda key_address, raw_value, logger: DEFAULT_ORDER
        if raw_value is None
        else int(raw_value),
    )
    link: Optional['tmt.base.Links'] = field(
        default=None,
        exporter=lambda value: value.to_spec() if value is not None else [],
        serialize=lambda value: value.to_spec() if value is not None else [],
    )
    id: Optional[str] = None
    tag: list[str] = field(
        default_factory=list,
        normalize=tmt.utils.normalize_string_list,
    )
    tier: Optional[str] = field(
        default=None,
        normalize=lambda key_address, raw_value, logger: None
        if raw_value is None
        else str(raw_value),
    )
    adjust: Optional[list['_RawAdjustRule']] = field(
        default_factory=list['_RawAdjustRule'],
        normalize=lambda key_address, raw_value, logger: []
        if raw_value is None
        else cast(
            list['_RawAdjustRule'], ([raw_value] if not isinstance(raw_value, list) else raw_value)
        ),
    )
    environment: Environment = field(
        default_factory=Environment,
        serialize=lambda environment: environment.to_fmf_spec(),
        unserialize=lambda serialized: Environment.from_fmf_spec(serialized),
    )
    context: FmfContext = field(
        default_factory=FmfContext,
        normalize=FmfContext.from_spec,
        serialize=lambda context: context.to_spec(),
        exporter=lambda value: value.to_spec(),
    )
    gate: list[str] = field(
        default_factory=list,
        normalize=tmt.utils.normalize_string_list,
    )

    login: Optional[Login] = None

    discover: Optional[_Step] = field(
        default=None, serialize=lambda step: step.to_serialized() if step else None
    )
    provision: Optional[_Step] = field(
        default=None, serialize=lambda step: step.to_serialized() if step else None
    )
    prepare: Optional[_Step] = field(
        default=None, serialize=lambda step: step.to_serialized() if step else None
    )
    execute: Optional[_Step] = field(
        default=None, serialize=lambda step: step.to_serialized() if step else None
    )
    report: Optional[_Step] = field(
        default=None, serialize=lambda step: step.to_serialized() if step else None
    )
    finish: Optional[_Step] = field(
        default=None, serialize=lambda step: step.to_serialized() if step else None
    )
    cleanup: Optional[_Step] = field(
        default=None, serialize=lambda step: step.to_serialized() if step else None
    )

    @classmethod
    def from_plan(cls, plan: 'Plan') -> '_RecipePlan':
        environment = Environment(
            {
                **plan._environment_from_plan_environment_file,
                **plan._environment_from_fmf,
                **plan._environment_from_importing,
                **plan._environment_from_intrinsics,
            }
        )
        return _RecipePlan(
            name=plan.name,
            summary=plan.summary,
            description=plan.description,
            author=plan.author,
            contact=plan.contact,
            enabled=plan.enabled,
            order=plan.order,
            link=plan.link,
            id=plan.id,
            tag=plan.tag,
            tier=plan.tier,
            adjust=plan.adjust,
            environment=environment,
            context=plan.context,
            gate=plan.gate,
            login=plan.login,
            discover=_get_step(plan, 'discover'),
            provision=_get_step(plan, 'provision'),
            prepare=_get_step(plan, 'prepare'),
            execute=_get_step(plan, 'execute'),
            report=_get_step(plan, 'report'),
            finish=_get_step(plan, 'finish'),
            cleanup=_get_step(plan, 'cleanup'),
        )


@container
class _RecipeRun(SerializableContainer):
    root: Optional[str] = None
    remove: bool = False
    environment: Environment = field(
        default_factory=Environment,
        serialize=lambda environment: environment.to_fmf_spec(),
        unserialize=lambda serialized: Environment.from_fmf_spec(serialized),
    )
    context: FmfContext = field(
        default_factory=FmfContext,
        normalize=FmfContext.from_spec,
        serialize=lambda context: context.to_spec(),
        exporter=lambda value: value.to_spec(),
    )


@container
class Recipe(SerializableContainer):
    run: Optional[_RecipeRun] = field(
        default=None,
        serialize=lambda run: run.to_serialized() if run else None,
    )
    plans: list[_RecipePlan] = field(
        default_factory=list[_RecipePlan],
        serialize=lambda plans: [plan.to_serialized() for plan in plans],
    )


class RecipeBuilder(Common):
    def __init__(self, logger: Logger):
        super().__init__(logger=logger)
        self.recipe = Recipe()

    def set_run(self, run_data: 'RunData', run_context: FmfContext) -> None:
        self.recipe.run = _RecipeRun(
            root=run_data.root,
            remove=bool(run_data.remove),
            environment=run_data.environment,
            context=run_context,
        )

    def set_plans(self, plans: list['Plan']) -> None:
        self.recipe.plans = [_RecipePlan.from_plan(plan) for plan in plans]

    def save(self, path: Path) -> None:
        serialized = self.recipe.to_serialized()
        self.write(path / 'recipe.yaml', tmt.utils.dict_to_yaml(serialized))
