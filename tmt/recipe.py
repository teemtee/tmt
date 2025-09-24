from typing import TYPE_CHECKING, Optional, cast

import tmt.utils
from tmt.checks import Check
from tmt.container import SerializableContainer, container, field
from tmt.log import Logger
from tmt.result import ResultInterpret
from tmt.steps import Step, StepData
from tmt.steps.discover import Discover, TestOrigin
from tmt.steps.execute import Execute
from tmt.utils import Common, Environment, FmfContext, Path, ShellScript

if TYPE_CHECKING:
    import tmt.base
    from tmt.base import Dependency, Plan, Run, _RawAdjustRule


@container
class _RecipeTest(SerializableContainer):
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
    component: list[str]
    framework: str
    manual: bool
    tty: bool
    duration: str
    where: list[str]
    restart_on_exit_code: list[int]
    restart_max_count: int
    restart_with_reboot: bool
    serial_number: int
    discover_phase: str
    link: Optional['tmt.base.Links'] = field(
        serialize=lambda value: cast(tmt.base.Links, value).to_spec() if value else []
    )
    test: ShellScript = field(serialize=lambda value: str(value))
    path: Optional[Path] = field(
        serialize=lambda value: str(value) if value else None,
    )
    require: list['Dependency'] = field(
        serialize=lambda value: [dependency.to_minimal_spec() for dependency in value],
    )
    recommend: list['Dependency'] = field(
        serialize=lambda value: [dependency.to_minimal_spec() for dependency in value],
    )
    environment: tmt.utils.Environment = field(
        serialize=lambda environment: environment.to_fmf_spec(),
        unserialize=lambda serialized: tmt.utils.Environment.from_fmf_spec(serialized),
    )
    result: ResultInterpret = field(
        serialize=lambda result: result.value,
        unserialize=ResultInterpret.from_spec,
    )
    check: list[Check] = field(
        serialize=lambda checks: [check.to_spec() for check in checks],
        unserialize=lambda serialized: [Check.from_spec(**check) for check in serialized],
    )

    @classmethod
    def from_test_origin(cls, test_origin: 'TestOrigin') -> '_RecipeTest':
        return _RecipeTest(
            name=test_origin.test.name,
            summary=test_origin.test.summary,
            description=test_origin.test.description,
            author=test_origin.test.author,
            contact=test_origin.test.contact,
            enabled=test_origin.test.enabled,
            order=test_origin.test.order,
            id=test_origin.test.id,
            tag=test_origin.test.tag,
            tier=test_origin.test.tier,
            adjust=test_origin.test.adjust,
            link=test_origin.test.link,
            component=test_origin.test.component,
            test=test_origin.test.test or ShellScript(''),
            path=test_origin.test.path,
            framework=test_origin.test.framework,
            manual=test_origin.test.manual,
            tty=test_origin.test.tty,
            require=test_origin.test.require,
            recommend=test_origin.test.recommend,
            environment=test_origin.test._original_fmf_environment,
            duration=test_origin.test.duration,
            result=test_origin.test.result,
            where=test_origin.test.where,
            check=test_origin.test.check,
            restart_on_exit_code=test_origin.test.restart_on_exit_code,
            restart_max_count=test_origin.test.restart_max_count,
            restart_with_reboot=test_origin.test.restart_with_reboot,
            serial_number=test_origin.test.serial_number,
            discover_phase=test_origin.phase,
        )


@container
class _RecipeStep(SerializableContainer):
    enabled: bool
    phases: list[StepData] = field(
        serialize=lambda value: [phase.to_serialized() for phase in value],
    )

    @classmethod
    def from_step(cls, step: 'Step') -> '_RecipeStep':
        enabled = bool(step.enabled)
        if isinstance(step, Discover):
            return _RecipeDiscoverStep(
                enabled=enabled,
                phases=step.data if enabled else [],
                tests=[_RecipeTest.from_test_origin(test_origin) for test_origin in step.tests()],
            )
        if isinstance(step, Execute):
            return _RecipeExecuteStep(
                enabled=enabled,
                phases=step.data if enabled else [],
                results_path=(step.step_workdir / 'results.yaml').relative_to(step.run_workdir),
            )
        return _RecipeStep(enabled=enabled, phases=step.data if enabled else [])


@container
class _RecipeDiscoverStep(_RecipeStep):
    tests: list[_RecipeTest] = field(
        default_factory=list[_RecipeTest],
        serialize=lambda tests: [test.to_serialized() for test in tests],
    )


@container
class _RecipeExecuteStep(_RecipeStep):
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
    link: Optional['tmt.base.Links'] = field(
        serialize=lambda value: cast(tmt.base.Links, value).to_spec() if value else []
    )
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

    discover: _RecipeStep = field(serialize=lambda step: cast(_RecipeStep, step).to_serialized())
    provision: _RecipeStep = field(serialize=lambda step: cast(_RecipeStep, step).to_serialized())
    prepare: _RecipeStep = field(serialize=lambda step: cast(_RecipeStep, step).to_serialized())
    execute: _RecipeStep = field(serialize=lambda step: cast(_RecipeStep, step).to_serialized())
    report: _RecipeStep = field(serialize=lambda step: cast(_RecipeStep, step).to_serialized())
    finish: _RecipeStep = field(serialize=lambda step: cast(_RecipeStep, step).to_serialized())
    cleanup: _RecipeStep = field(serialize=lambda step: cast(_RecipeStep, step).to_serialized())

    context: FmfContext = field(
        default_factory=FmfContext,
        serialize=lambda context: context.to_spec(),
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
            discover=_RecipeStep.from_step(plan.discover),
            provision=_RecipeStep.from_step(plan.provision),
            prepare=_RecipeStep.from_step(plan.prepare),
            execute=_RecipeStep.from_step(plan.execute),
            report=_RecipeStep.from_step(plan.report),
            finish=_RecipeStep.from_step(plan.finish),
            cleanup=_RecipeStep.from_step(plan.cleanup),
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
