from typing import TYPE_CHECKING, Any, Optional, cast

import tmt.utils
from tmt.container import SerializableContainer, container, field
from tmt.log import Logger
from tmt.steps import Step, StepData
from tmt.steps.discover import Discover
from tmt.steps.execute import Execute
from tmt.utils import Common, Environment, FmfContext, Path

if TYPE_CHECKING:
    import tmt.base
    from tmt.base import Plan, Run, Test, _RawAdjustRule


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
    enabled: bool
    phases: list[StepData] = field(
        serialize=lambda value: [phase.to_serialized() for phase in value],
    )

    @classmethod
    def from_plan(cls, plan: 'Plan', step_name: str) -> '_Step':
        step = getattr(plan, step_name)
        if isinstance(step, Discover):
            return _DiscoverStep(
                enabled=bool(step.enabled),
                phases=cast(Step, step).data if step.enabled else [],
                tests=[test_origin.test for test_origin in step.tests()],
            )
        if isinstance(step, Execute):
            return _ExecuteStep(
                enabled=bool(step.enabled),
                phases=cast(Step, step).data if step.enabled else [],
                results_path=(step.step_workdir / 'results.yaml').relative_to(step.run_workdir),
            )
        if isinstance(step, Step):
            return _Step(enabled=bool(step.enabled), phases=step.data if step.enabled else [])

        raise ValueError(f"Step '{step_name}' is not defined in plan '{plan.name}'")


@container
class _DiscoverStep(_Step):
    tests: list['Test'] = field(serialize=_serialize_tests)


@container
class _ExecuteStep(_Step):
    results_path: Optional[Path] = field(
        serialize=lambda value: str(value) if isinstance(value, Path) else None,
        unserialize=lambda value: Path(value) if value is not None else None,
    )


@container
class _RecipePlan(SerializableContainer):
    name: str
    summary: Optional[str]
    description: Optional[str]
    author: list[str]
    contact: list[str]
    enabled: bool
    order: int
    id: Optional[str]
    tag: list[str]
    tier: Optional[str]
    adjust: Optional[list['_RawAdjustRule']]
    gate: list[str]
    environment_from_fmf: Environment = field(
        serialize=lambda environment: environment.to_fmf_spec(),
        unserialize=lambda serialized: Environment.from_fmf_spec(serialized),
    )
    environment_from_importing: Environment = field(
        serialize=lambda environment: environment.to_fmf_spec(),
        unserialize=lambda serialized: Environment.from_fmf_spec(serialized),
    )
    environment_from_cli: Environment = field(
        serialize=lambda environment: environment.to_fmf_spec(),
        unserialize=lambda serialized: Environment.from_fmf_spec(serialized),
    )
    environment_from_intrinsics: Environment = field(
        serialize=lambda environment: environment.to_fmf_spec(),
        unserialize=lambda serialized: Environment.from_fmf_spec(serialized),
    )

    discover: _Step = field(serialize=lambda step: cast(_Step, step).to_serialized())
    provision: _Step = field(serialize=lambda step: cast(_Step, step).to_serialized())
    prepare: _Step = field(serialize=lambda step: cast(_Step, step).to_serialized())
    execute: _Step = field(serialize=lambda step: cast(_Step, step).to_serialized())
    report: _Step = field(serialize=lambda step: cast(_Step, step).to_serialized())
    finish: _Step = field(serialize=lambda step: cast(_Step, step).to_serialized())
    cleanup: _Step = field(serialize=lambda step: cast(_Step, step).to_serialized())

    context: FmfContext = field(
        default_factory=FmfContext,
        serialize=lambda context: context.to_spec(),
    )
    link: Optional['tmt.base.Links'] = field(
        default=None,
        serialize=lambda value: value.to_spec() if value is not None else [],
    )

    @classmethod
    def from_plan(cls, plan: 'Plan') -> '_RecipePlan':
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
            environment_from_fmf=plan._environment_from_fmf,
            environment_from_importing=plan._environment_from_importing,
            environment_from_cli=plan._environment_from_cli,
            environment_from_intrinsics=plan._environment_from_intrinsics,
            context=plan.context,
            gate=plan.gate,
            discover=_Step.from_plan(plan, 'discover'),
            provision=_Step.from_plan(plan, 'provision'),
            prepare=_Step.from_plan(plan, 'prepare'),
            execute=_Step.from_plan(plan, 'execute'),
            report=_Step.from_plan(plan, 'report'),
            finish=_Step.from_plan(plan, 'finish'),
            cleanup=_Step.from_plan(plan, 'cleanup'),
        )


@container
class _RecipeRun(SerializableContainer):
    root: Optional[str]
    remove: bool
    environment: Environment = field(
        serialize=lambda environment: environment.to_fmf_spec(),
        unserialize=lambda serialized: Environment.from_fmf_spec(serialized),
    )
    context: FmfContext = field(
        default_factory=FmfContext,
        serialize=lambda context: context.to_spec(),
    )


@container
class Recipe(SerializableContainer):
    run: _RecipeRun = field(serialize=lambda run: cast(_RecipeRun, run).to_serialized())
    plans: list[_RecipePlan] = field(
        default_factory=list[_RecipePlan],
        serialize=lambda plans: [plan.to_serialized() for plan in plans],
    )


class RecipeBuilder(Common):
    def __init__(self, logger: Logger, recipe: Optional[Recipe] = None):
        super().__init__(logger=logger)
        self.recipe: Optional[Recipe] = recipe

    def save(self, run: 'Run') -> None:
        self.recipe = Recipe(
            run=_RecipeRun(
                root=str(run.tree.root) if run.tree and run.tree.root else None,
                remove=bool(run.remove),
                environment=run.environment,
                context=run.fmf_context,
            ),
            plans=[_RecipePlan.from_plan(plan) for plan in run.plans],
        )
        self.write(
            run.run_workdir / 'recipe.yaml', tmt.utils.dict_to_yaml(self.recipe.to_serialized())
        )
