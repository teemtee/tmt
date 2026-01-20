from typing import TYPE_CHECKING, Any, Optional

import fmf

import tmt.utils
from tmt.checks import Check
from tmt.container import SerializableContainer, container, field
from tmt.log import Logger
from tmt.result import ResultInterpret
from tmt.steps import Step, StepData, _RawStepData
from tmt.steps.discover import Discover, TestOrigin
from tmt.utils import Common, Environment, FmfContext, Path, ShellScript

if TYPE_CHECKING:
    import tmt.base
    from tmt.base import Dependency, Plan, Run, _RawAdjustRule, _RawLinks


# This needs to be a stand-alone function because of the import of `tmt.base`.
# It cannot be imported on module level because of circular dependency.
def _unserialize_dependency(
    serialized: Optional['tmt.base._RawDependencyItem'],
) -> 'tmt.base.Dependency':
    from tmt.base import dependency_factory

    return dependency_factory(serialized)


# This needs to be a stand-alone function because of the import of `tmt.base`.
# It cannot be imported on module level because of circular dependency.
def _unserialize_links(serialized: Optional['_RawLinks']) -> Optional['tmt.base.Links']:
    from tmt.base import Links

    return Links(data=serialized)


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
        serialize=lambda value: value.to_spec() if value else [],
        unserialize=lambda value: _unserialize_links(value),
    )
    test: ShellScript = field(
        serialize=lambda value: str(value),
        unserialize=lambda value: ShellScript(value),
    )
    path: Optional[Path] = field(
        serialize=lambda value: str(value) if value else None,
        unserialize=lambda value: Path(value) if value else None,
    )
    require: list['Dependency'] = field(
        serialize=lambda value: [dependency.to_minimal_spec() for dependency in value],
        unserialize=lambda value: [_unserialize_dependency(dep) for dep in value],
    )
    recommend: list['Dependency'] = field(
        serialize=lambda value: [dependency.to_minimal_spec() for dependency in value],
        unserialize=lambda value: [_unserialize_dependency(dep) for dep in value],
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
            require=test_origin.test._original_require,
            recommend=test_origin.test._original_recommend,
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

    def to_minimal_spec(self) -> dict[str, Any]:
        data = {
            key: value
            for key, value in self.to_serialized().items()
            if value not in (None, [], {})
        }
        data.pop('__class__')
        data.pop('discover-phase')
        return data

    def to_test(self, logger: Logger) -> 'tmt.base.Test':
        from tmt.base import Test

        data = self.to_minimal_spec()
        name = data.pop('name')
        serial_number = data.pop('serial-number')
        where = data.pop('where', [])

        test = Test.from_dict(mapping=data, name=name, logger=logger)
        try:
            test.serial_number = int(serial_number)
        except ValueError as error:
            raise tmt.utils.SpecificationError(
                f"Invalid serial number in test '{name}'."
            ) from error
        test.where = where
        return test


@container
class _RecipeStep(SerializableContainer):
    enabled: bool
    phases: list[StepData] = field(
        serialize=lambda value: [phase.to_serialized() for phase in value]
    )

    # ignore[override]: does not match the signature on purpose, we need to pass logger
    @classmethod
    def from_serialized(cls, serialized: dict[str, Any], logger: Logger) -> '_RecipeStep':  # type: ignore[override]
        enabled = bool(serialized.get('enabled', False))
        return _RecipeStep(
            enabled=enabled,
            phases=[StepData.unserialize(phase, logger) for phase in serialized.get('phases', [])]
            if enabled
            else [],
        )

    @classmethod
    def from_step(cls, step: 'Step') -> '_RecipeStep':
        enabled = bool(step.enabled)
        return _RecipeStep(enabled=enabled, phases=step.data if enabled else [])

    def to_spec(self) -> list[_RawStepData]:
        return [phase.to_minimal_spec() for phase in self.phases]


@container
class _RecipeDiscoverStep(_RecipeStep):
    tests: list[_RecipeTest] = field(
        default_factory=list[_RecipeTest],
        serialize=lambda tests: [test.to_serialized() for test in tests],
    )

    # ignore[override]: does not match the signature on purpose, we need to pass logger
    @classmethod
    def from_serialized(cls, serialized: dict[str, Any], logger: Logger) -> '_RecipeDiscoverStep':  # type: ignore[override]
        enabled = bool(serialized.get('enabled', False))
        return _RecipeDiscoverStep(
            enabled=enabled,
            phases=[StepData.unserialize(phase, logger) for phase in serialized.get('phases', [])]
            if enabled
            else [],
            tests=[_RecipeTest.from_serialized(test) for test in serialized.get('tests', [])],
        )

    @classmethod
    def from_step(cls, step: 'Step') -> '_RecipeDiscoverStep':
        assert isinstance(step, Discover)
        enabled = bool(step.enabled)
        return _RecipeDiscoverStep(
            enabled=enabled,
            phases=step.data if enabled else [],
            tests=[_RecipeTest.from_test_origin(test_origin) for test_origin in step.tests()],
        )


@container
class _RecipeExecuteStep(_RecipeStep):
    results_path: Optional[Path] = field(
        serialize=lambda value: str(value) if isinstance(value, Path) else None,
        unserialize=lambda value: Path(value) if value is not None else None,
    )

    # ignore[override]: does not match the signature on purpose, we need to pass logger
    @classmethod
    def from_serialized(cls, serialized: dict[str, Any], logger: Logger) -> '_RecipeExecuteStep':  # type: ignore[override]
        enabled = bool(serialized.get('enabled', False))
        results_path = serialized.get('results-path')
        return _RecipeExecuteStep(
            enabled=enabled,
            phases=[StepData.unserialize(phase, logger) for phase in serialized.get('phases', [])]
            if enabled
            else [],
            results_path=Path(results_path) if results_path is not None else None,
        )

    @classmethod
    def from_step(cls, step: 'Step') -> '_RecipeExecuteStep':
        enabled = bool(step.enabled)
        return _RecipeExecuteStep(
            enabled=enabled,
            phases=step.data if enabled else [],
            results_path=(step.step_workdir / 'results.yaml').relative_to(step.run_workdir),
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
    link: Optional['tmt.base.Links'] = field(serialize=lambda link: link.to_spec() if link else [])
    environment_from_fmf: Environment = field(
        serialize=lambda environment: environment.to_fmf_spec()
    )
    environment_from_importing: Environment = field(
        serialize=lambda environment: environment.to_fmf_spec()
    )
    environment_from_cli: Environment = field(
        serialize=lambda environment: environment.to_fmf_spec()
    )
    environment_from_intrinsics: Environment = field(
        serialize=lambda environment: environment.to_fmf_spec()
    )

    discover: _RecipeDiscoverStep = field(serialize=lambda step: step.to_serialized())
    provision: _RecipeStep = field(serialize=lambda step: step.to_serialized())
    prepare: _RecipeStep = field(serialize=lambda step: step.to_serialized())
    execute: _RecipeExecuteStep = field(serialize=lambda step: step.to_serialized())
    report: _RecipeStep = field(serialize=lambda step: step.to_serialized())
    finish: _RecipeStep = field(serialize=lambda step: step.to_serialized())
    cleanup: _RecipeStep = field(serialize=lambda step: step.to_serialized())

    context: FmfContext = field(
        default_factory=FmfContext,
        serialize=lambda context: context.to_spec(),
    )

    # ignore[override]: does not match the signature on purpose, we need to pass logger
    @classmethod
    def from_serialized(cls, serialized: dict[str, Any], logger: Logger) -> '_RecipePlan':  # type: ignore[override]
        from tmt.base import DEFAULT_ORDER

        return _RecipePlan(
            name=serialized.get('name', ''),
            summary=serialized.get('summary'),
            description=serialized.get('description'),
            author=serialized.get('author', []),
            contact=serialized.get('contact', []),
            enabled=bool(serialized.get('enabled', False)),
            order=int(serialized.get('order', DEFAULT_ORDER)),
            id=serialized.get('id'),
            tag=serialized.get('tag', []),
            tier=serialized.get('tier'),
            adjust=serialized.get('adjust'),
            link=_unserialize_links(serialized.get('link')),
            environment_from_fmf=Environment.from_fmf_spec(
                serialized.get('environment-from-fmf', {})
            ),
            environment_from_importing=Environment.from_fmf_spec(
                serialized.get('environment-from-importing', {})
            ),
            environment_from_cli=Environment.from_fmf_spec(
                serialized.get('environment-from-cli', {})
            ),
            environment_from_intrinsics=Environment.from_fmf_spec(
                serialized.get('environment-from-intrinsics', {})
            ),
            discover=_RecipeDiscoverStep.from_serialized(serialized.get('discover', {}), logger),
            provision=_RecipeStep.from_serialized(serialized.get('provision', {}), logger),
            prepare=_RecipeStep.from_serialized(serialized.get('prepare', {}), logger),
            execute=_RecipeExecuteStep.from_serialized(serialized.get('execute', {}), logger),
            report=_RecipeStep.from_serialized(serialized.get('report', {}), logger),
            finish=_RecipeStep.from_serialized(serialized.get('finish', {}), logger),
            cleanup=_RecipeStep.from_serialized(serialized.get('cleanup', {}), logger),
            context=FmfContext.from_serialized(serialized.get('context', {})),
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
            discover=_RecipeDiscoverStep.from_step(plan.discover),
            provision=_RecipeStep.from_step(plan.provision),
            prepare=_RecipeStep.from_step(plan.prepare),
            execute=_RecipeExecuteStep.from_step(plan.execute),
            report=_RecipeStep.from_step(plan.report),
            finish=_RecipeStep.from_step(plan.finish),
            cleanup=_RecipeStep.from_step(plan.cleanup),
        )

    def to_spec(self) -> dict[str, Any]:
        # TODO: For now, only return the discover step.
        return {'discover': self.discover.to_spec()}


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
        unserialize=lambda serialized: FmfContext.from_serialized(serialized),
    )


@container
class Recipe(SerializableContainer):
    run: _RecipeRun = field(serialize=lambda run: run.to_serialized())
    plans: list[_RecipePlan] = field(
        default_factory=list[_RecipePlan],
        serialize=lambda plans: [plan.to_serialized() for plan in plans],
    )

    # ignore[override]: does not match the signature on purpose, we need to pass logger
    @classmethod
    def from_serialized(cls, serialized: dict[str, Any], logger: Logger) -> 'Recipe':  # type: ignore[override]
        return Recipe(
            run=_RecipeRun.from_serialized(serialized.get('run', {})),
            plans=[
                _RecipePlan.from_serialized(plan, logger) for plan in serialized.get('plans', [])
            ],
        )


class RecipeManager(Common):
    def __init__(self, logger: Logger):
        super().__init__(logger=logger)

    def load(self, path: Path) -> Recipe:
        return Recipe.from_serialized(tmt.utils.yaml_to_dict(self.read(path)), self._logger)

    def save(self, run: 'Run') -> None:
        recipe = Recipe(
            run=_RecipeRun(
                root=str(run.tree.root) if run.tree and run.tree.root else None,
                remove=bool(run.remove),
                environment=run.environment,
                context=run.fmf_context,
            ),
            plans=[_RecipePlan.from_plan(plan) for plan in run.plans],
        )
        self.write(run.run_workdir / 'recipe.yaml', tmt.utils.to_yaml(recipe.to_serialized()))

    def tests(self, recipe: Recipe, plan_name: str) -> list[TestOrigin]:
        for plan in recipe.plans:
            if plan.name == plan_name:
                return [
                    TestOrigin(
                        phase=test.discover_phase,
                        test=test.to_test(self._logger),
                    )
                    for test in plan.discover.tests
                ]

        raise tmt.utils.GeneralError(f"Plan '{plan_name}' not found in the recipe.")

    @staticmethod
    def update_tree(recipe: Recipe, tree: fmf.Tree) -> None:
        tree.update({plan.name: plan.to_spec() for plan in recipe.plans})
