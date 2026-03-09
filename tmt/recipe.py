from typing import TYPE_CHECKING, Any, Callable, Optional, TypedDict, cast

import fmf

import tmt.utils
from tmt.checks import Check, _RawCheck, normalize_test_checks
from tmt.container import (
    SerializableContainer,
    SpecBasedContainer,
    container,
    field,
    key_to_option,
    option_to_key,
)
from tmt.log import Logger
from tmt.result import ResultInterpret
from tmt.steps import Step, _RawStepData
from tmt.steps.discover import Discover, TestOrigin
from tmt.utils import Common, Environment, FmfContext, NormalizeKeysMixin, Path, ShellScript

if TYPE_CHECKING:
    from tmt.base.core import (
        Dependency,
        Links,
        Run,
        Test,
        _RawAdjustRule,
        _RawDependency,
        _RawLinks,
    )
    from tmt.base.plan import Plan


# Copy of tmt.base.core.DEFAULT_ORDER
DEFAULT_ORDER = 50

# Copy of tmt.base.core.DEFAULT_TEST_DURATION_L1
DEFAULT_TEST_DURATION_L1 = '5m'


def _normalize_link(value: Optional['_RawLinks']) -> 'Links':
    from tmt.base.core import Links

    return Links(data=value)


def _normalize_require(
    key_address: str, raw_require: Optional['_RawDependency'], logger: Logger
) -> list['Dependency']:
    from tmt.base.core import normalize_require

    return normalize_require(key_address, raw_require, logger)


class _RawRecipeTest(TypedDict, total=False):
    name: str
    discover_phase: str
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
    link: Optional['_RawLinks']
    test: Optional[str]
    path: Optional[str]
    require: list['_RawDependency']
    recommend: list['_RawDependency']
    environment: dict[str, str]
    result: str
    check: list[_RawCheck]


class _RawRecipeStep(TypedDict, total=False):
    enabled: bool
    phases: list[_RawStepData]


class _RawRecipePlan(TypedDict, total=False):
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
    link: Optional['_RawLinks']
    environment: dict[str, str]
    context: dict[str, Any]
    discover: _RawRecipeStep
    provision: _RawRecipeStep
    prepare: _RawRecipeStep
    execute: _RawRecipeStep
    report: _RawRecipeStep
    finish: _RawRecipeStep
    cleanup: _RawRecipeStep


class _RawRecipeRun(TypedDict, total=False):
    root: Optional[str]
    remove: bool
    environment: dict[str, str]
    context: dict[str, Any]


class _RawRecipe(TypedDict, total=False):
    run: _RawRecipeRun
    plans: list[_RawRecipePlan]


@container
class _RecipeTest(
    SpecBasedContainer[_RawRecipeTest, _RawRecipeTest], NormalizeKeysMixin, SerializableContainer
):
    name: str = field()
    discover_phase: str = field()
    test: Optional[ShellScript] = field(default=None, normalize=tmt.utils.normalize_shell_script)
    path: Optional[Path] = field(default=None, normalize=tmt.utils.normalize_path)
    summary: Optional[str] = field(default=None)
    description: Optional[str] = field(default=None)
    author: list[str] = field(default_factory=list, normalize=tmt.utils.normalize_string_list)
    contact: list[str] = field(default_factory=list, normalize=tmt.utils.normalize_string_list)
    enabled: bool = field(default=True)
    order: int = field(default=DEFAULT_ORDER)
    id: Optional[str] = field(default=None)
    tag: list[str] = field(default_factory=list, normalize=tmt.utils.normalize_string_list)
    tier: Optional[str] = field(default=None)
    adjust: Optional[list['_RawAdjustRule']] = field(default=None)
    component: list[str] = field(default_factory=list, normalize=tmt.utils.normalize_string_list)
    framework: str = field(default='shell')
    manual: bool = field(default=False)
    tty: bool = field(default=False)
    duration: str = field(default=DEFAULT_TEST_DURATION_L1)
    where: list[str] = field(default_factory=list, normalize=tmt.utils.normalize_string_list)
    restart_on_exit_code: list[int] = field(
        default_factory=list, normalize=tmt.utils.normalize_integer_list
    )
    restart_max_count: int = field(default=1)
    restart_with_reboot: bool = field(default=False)
    serial_number: int = field(default=0)
    link: Optional['Links'] = field(
        default=None, normalize=lambda key_address, raw_value, logger: _normalize_link(raw_value)
    )
    require: list['Dependency'] = field(default_factory=list, normalize=_normalize_require)
    recommend: list['Dependency'] = field(default_factory=list, normalize=_normalize_require)
    environment: Environment = field(default_factory=Environment, normalize=Environment.normalize)
    result: ResultInterpret = field(
        default=ResultInterpret.RESPECT, normalize=ResultInterpret.normalize
    )
    check: list[Check] = field(default_factory=list, normalize=normalize_test_checks)

    @classmethod
    def from_spec(cls, spec: _RawRecipeTest, logger: Logger) -> '_RecipeTest':  # type: ignore[override]
        for key in ['name', 'discover-phase']:
            if key not in spec:
                raise tmt.utils.SpecificationError(f"Test requires '{key}' key")

        assert 'name' in spec
        assert 'discover-phase' in spec
        data = cls(name=spec['name'], discover_phase=spec['discover-phase'])  # type: ignore[typeddict-item]
        data._load_keys(cast(dict[str, Any], spec), cls.__name__, logger)
        return data

    @classmethod
    def from_test_origin(cls, test_origin: 'TestOrigin') -> '_RecipeTest':
        return _RecipeTest(
            name=test_origin.test.name,
            discover_phase=test_origin.phase,
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
            path=test_origin.test.path or Path('/'),
            framework=test_origin.test.framework,
            manual=test_origin.test.manual,
            tty=test_origin.test.tty,
            require=test_origin.test._original_require,
            recommend=test_origin.test._original_recommend,
            environment=test_origin.test.environment,
            duration=test_origin.test.duration,
            result=test_origin.test.result,
            where=test_origin.test.where,
            check=test_origin.test.check,
            restart_on_exit_code=test_origin.test.restart_on_exit_code,
            restart_max_count=test_origin.test.restart_max_count,
            restart_with_reboot=test_origin.test.restart_with_reboot,
            serial_number=test_origin.test.serial_number,
        )

    def to_minimal_spec(self) -> _RawRecipeTest:
        from tmt.base.core import _RawLinks

        spec = {
            key_to_option(key): value for key, value in self.items() if value not in (None, [], {})
        }

        field_map: dict[str, Callable[[Any], Any]] = {
            'test': lambda test: str(test) if test is not None else None,
            'path': lambda path: str(path) if path is not None else None,
            'link': lambda link: cast(_RawLinks, link.to_spec()) if link else None,
            'require': lambda requires: [require.to_minimal_spec() for require in requires],
            'recommend': lambda recommends: [
                recommend.to_minimal_spec() for recommend in recommends
            ],
            'environment': lambda environment: environment.to_fmf_spec(),
            'result': lambda result: result.value,
            'check': lambda checks: [check.to_spec() for check in checks],
        }

        for key, transform in field_map.items():
            value = getattr(self, option_to_key(key), None)
            if value is not None:
                value = transform(value)
            if value in (None, [], {}):
                spec.pop(key, None)
            else:
                spec[key] = value

        return cast(_RawRecipeTest, spec)

    def to_test(self, logger: Logger) -> 'Test':
        """
        Convert the recipe test to a :py:class:`tmt.base.core.Test` instance.
        """
        from tmt.base.core import Test

        data = self.to_minimal_spec()
        data.pop('discover-phase')  # type: ignore[typeddict-item]

        name: str = data.pop('name')
        serial_number: int = data.pop('serial-number')  # type: ignore[typeddict-item]
        where: list[str] = data.pop('where', [])

        test = Test.from_dict(mapping=cast(dict[str, Any], data), name=name, logger=logger)
        try:
            test.serial_number = int(serial_number)
        except ValueError as error:
            raise tmt.utils.SpecificationError(
                f"Invalid serial number in test '{name}'."
            ) from error
        test.where = where
        return test


@container
class _RecipeStep(SpecBasedContainer[_RawRecipeStep, _RawRecipeStep], SerializableContainer):
    enabled: bool
    phases: list[_RawStepData]

    @classmethod
    def from_step(cls, step: 'Step') -> '_RecipeStep':
        enabled = bool(step.enabled)
        return _RecipeStep(
            enabled=enabled,
            phases=[phase.to_minimal_spec() for phase in step.data] if enabled else [],
        )

    # ignore[override]: does not match the signature on purpose, we need to pass logger
    @classmethod
    def from_spec(cls, spec: _RawRecipeStep, logger: Logger) -> '_RecipeStep':  # type: ignore[override]
        enabled = bool(spec.get('enabled', False))
        return _RecipeStep(enabled=enabled, phases=spec.get('phases', []) if enabled else [])

    def to_spec(self) -> _RawRecipeStep:
        return _RawRecipeStep(enabled=self.enabled, phases=self.phases)

    def to_fmf_spec(self) -> list[_RawStepData]:
        """Convert step phases into a list of fmf-compatible specifications."""
        return cast(
            list[_RawStepData],
            [
                {key: value for key, value in phase.items() if value not in (None, [], {})}
                for phase in self.phases
            ],
        )


@container
class _RecipeDiscoverStep(_RecipeStep):
    tests: list[_RecipeTest]

    def to_spec(self) -> _RawRecipeStep:
        return _RawRecipeStep(
            enabled=self.enabled,
            phases=self.phases,
            tests=[test.to_minimal_spec() for test in self.tests],  # type: ignore[typeddict-unknown-key]
        )

    # ignore[override]: does not match the signature on purpose, we need to pass logger
    @classmethod
    def from_spec(cls, spec: _RawRecipeStep, logger: Logger) -> '_RecipeDiscoverStep':  # type: ignore[override]
        enabled = bool(spec.get('enabled', False))
        return _RecipeDiscoverStep(
            enabled=enabled,
            phases=spec.get('phases', []) if enabled else [],
            tests=[
                _RecipeTest.from_spec(test, logger)
                for test in cast(list[_RawRecipeTest], spec.get('tests', []))
            ],
        )

    @classmethod
    def from_step(cls, step: 'Step') -> '_RecipeDiscoverStep':
        assert isinstance(step, Discover)
        enabled = bool(step.enabled)
        return _RecipeDiscoverStep(
            enabled=enabled,
            phases=[phase.to_minimal_spec() for phase in step.data] if enabled else [],
            tests=[_RecipeTest.from_test_origin(test_origin) for test_origin in step.tests()],
        )


@container
class _RecipeExecuteStep(_RecipeStep):
    results_path: Optional[Path]

    def to_spec(self) -> _RawRecipeStep:
        spec = _RawRecipeStep(
            enabled=self.enabled,
            phases=self.phases,
        )
        spec['results-path'] = (  # type: ignore[typeddict-unknown-key]
            str(self.results_path) if isinstance(self.results_path, Path) else None
        )
        return spec

    # ignore[override]: does not match the signature on purpose, we need to pass logger
    @classmethod
    def from_spec(cls, spec: _RawRecipeStep, logger: Logger) -> '_RecipeExecuteStep':  # type: ignore[override]
        enabled = bool(spec.get('enabled', False))
        results_path = cast(Optional[str], spec.get('results-path', None))
        return _RecipeExecuteStep(
            enabled=enabled,
            phases=spec.get('phases', []) if enabled else [],
            results_path=Path(results_path) if results_path else None,
        )

    @classmethod
    def from_step(cls, step: 'Step') -> '_RecipeExecuteStep':
        enabled = bool(step.enabled)
        return _RecipeExecuteStep(
            enabled=enabled,
            phases=[phase.to_minimal_spec() for phase in step.data] if enabled else [],
            results_path=(step.step_workdir / 'results.yaml').relative_to(step.run_workdir),
        )


@container
class _RecipePlan(SpecBasedContainer[_RawRecipePlan, _RawRecipePlan], SerializableContainer):
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
    link: Optional['Links']
    environment: Environment
    context: FmfContext
    discover: _RecipeDiscoverStep
    provision: _RecipeStep
    prepare: _RecipeStep
    execute: _RecipeExecuteStep
    report: _RecipeStep
    finish: _RecipeStep
    cleanup: _RecipeStep

    # ignore[override]: does not match the signature on purpose, we need to pass logger
    @classmethod
    def from_spec(cls, spec: _RawRecipePlan, logger: Logger) -> '_RecipePlan':  # type: ignore[override]
        from tmt.base.core import DEFAULT_ORDER, _RawLinks

        return _RecipePlan(
            name=spec.get('name', ''),
            summary=spec.get('summary'),
            description=spec.get('description'),
            author=spec.get('author', []),
            contact=spec.get('contact', []),
            enabled=bool(spec.get('enabled', False)),
            order=int(spec.get('order', DEFAULT_ORDER)),
            id=spec.get('id'),
            tag=spec.get('tag', []),
            tier=spec.get('tier'),
            adjust=spec.get('adjust'),
            link=_normalize_link(cast(_RawLinks, spec.get('link'))),
            environment=Environment.from_fmf_spec(spec.get('environment', {})),
            context=FmfContext.from_serialized(spec.get('context', {})),
            discover=_RecipeDiscoverStep.from_spec(spec.get('discover', {}), logger),
            provision=_RecipeStep.from_spec(spec.get('provision', {}), logger),
            prepare=_RecipeStep.from_spec(spec.get('prepare', {}), logger),
            execute=_RecipeExecuteStep.from_spec(spec.get('execute', {}), logger),
            report=_RecipeStep.from_spec(spec.get('report', {}), logger),
            finish=_RecipeStep.from_spec(spec.get('finish', {}), logger),
            cleanup=_RecipeStep.from_spec(spec.get('cleanup', {}), logger),
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
            environment=plan._environment_from_fmf,
            context=plan.context,
            discover=_RecipeDiscoverStep.from_step(plan.discover),
            provision=_RecipeStep.from_step(plan.provision),
            prepare=_RecipeStep.from_step(plan.prepare),
            execute=_RecipeExecuteStep.from_step(plan.execute),
            report=_RecipeStep.from_step(plan.report),
            finish=_RecipeStep.from_step(plan.finish),
            cleanup=_RecipeStep.from_step(plan.cleanup),
        )

    def to_minimal_spec(self) -> _RawRecipePlan:
        from tmt.base.core import _RawLinks

        spec = {
            key_to_option(key): value for key, value in self.items() if value not in (None, [], {})
        }

        field_map: dict[str, Callable[[Any], Any]] = {
            'link': lambda link: cast(_RawLinks, link.to_spec()) if link else None,
            'environment': lambda environment: environment.to_fmf_spec(),
            'context': lambda context: context.to_spec(),
            'discover': lambda step: step.to_spec(),
            'provision': lambda step: step.to_spec(),
            'prepare': lambda step: step.to_spec(),
            'execute': lambda step: step.to_spec(),
            'report': lambda step: step.to_spec(),
            'finish': lambda step: step.to_spec(),
            'cleanup': lambda step: step.to_spec(),
        }

        for key, transform in field_map.items():
            value = getattr(self, option_to_key(key), None)
            if value is not None:
                value = transform(value)
            if value in (None, [], {}):
                spec.pop(key, None)
            else:
                spec[key] = value

        return cast(_RawRecipePlan, spec)

    def to_fmf_spec(self) -> dict[str, Any]:
        """Convert the plan into a specification suitable for an fmf tree node."""
        spec = cast(dict[str, Any], self.to_minimal_spec())

        spec.pop('name')
        spec['discover'] = self.discover.to_fmf_spec()
        spec['provision'] = self.provision.to_fmf_spec()
        spec['prepare'] = self.prepare.to_fmf_spec()
        spec['execute'] = self.execute.to_fmf_spec()
        spec['report'] = self.report.to_fmf_spec()
        spec['finish'] = self.finish.to_fmf_spec()
        spec['cleanup'] = self.cleanup.to_fmf_spec()
        return {key: value for key, value in spec.items() if value not in (None, [], {})}

    def get_step_by_name(self, name: str) -> _RecipeStep:
        steps = [value for key, value in self.items() if key == name]
        if len(steps) != 1 or not isinstance(steps[0], _RecipeStep):
            raise tmt.utils.GeneralError(
                f"Unable to find the correct step in the recipe: '{name}'"
            )
        return steps[0]


@container
class _RecipeRun(SpecBasedContainer[_RawRecipeRun, _RawRecipeRun], SerializableContainer):
    root: Optional[str]
    remove: bool
    environment: Environment
    context: FmfContext

    def to_spec(self) -> _RawRecipeRun:
        return {
            'root': self.root,
            'remove': self.remove,
            'environment': self.environment.to_fmf_spec(),
            'context': self.context.to_spec(),
        }

    @classmethod
    def from_spec(cls, spec: _RawRecipeRun) -> '_RecipeRun':
        return _RecipeRun(
            root=spec.get('root'),
            remove=bool(spec.get('remove', False)),
            environment=Environment.from_fmf_spec(spec.get('environment', {})),
            context=FmfContext.from_serialized(spec.get('context', {})),
        )


@container
class Recipe(SpecBasedContainer[_RawRecipe, _RawRecipe], SerializableContainer):
    run: _RecipeRun
    plans: list[_RecipePlan]

    # ignore[override]: does not match the signature on purpose, we need to pass logger
    @classmethod
    def from_spec(cls, spec: _RawRecipe, logger: Logger) -> 'Recipe':  # type: ignore[override]
        return Recipe(
            run=_RecipeRun.from_spec(spec.get('run', {})),
            plans=[_RecipePlan.from_spec(plan, logger) for plan in spec.get('plans', [])],
        )

    def to_spec(self) -> _RawRecipe:
        return {
            'run': self.run.to_spec(),
            'plans': [plan.to_minimal_spec() for plan in self.plans],
        }

    def get_plan_by_name(self, name: str) -> _RecipePlan:
        plans = [plan for plan in self.plans if plan.name == name]
        if len(plans) != 1:
            raise tmt.utils.GeneralError(
                f"Unable to find the correct plan in the recipe: '{name}'"
            )
        return plans[0]


class RecipeManager(Common):
    def __init__(self, logger: Logger):
        super().__init__(logger=logger)

    def load(self, path: Path) -> Recipe:
        return Recipe.from_spec(
            cast(_RawRecipe, tmt.utils.yaml_to_dict(self.read(path))), self._logger
        )

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
        self.write(run.run_workdir / 'recipe.yaml', tmt.utils.to_yaml(recipe.to_spec()))

    def tests(self, recipe: Recipe, plan_name: str) -> list[TestOrigin]:
        """
        Return the list of tests for the given plan name in the recipe.
        """
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
        """
        Load the plans from the recipe and update the given fmf tree with their specifications.
        """
        tree.children.clear()
        tree.update({plan.name: plan.to_fmf_spec() for plan in recipe.plans})
