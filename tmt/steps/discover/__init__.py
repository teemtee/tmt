import dataclasses
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any, Optional, TypeVar, cast

import click
from fmf.utils import listed

import tmt

if TYPE_CHECKING:
    import tmt.cli
    import tmt.options
    import tmt.steps

import tmt.base
import tmt.steps
import tmt.utils
from tmt.options import option
from tmt.plugins import PluginRegistry
from tmt.result import Result
from tmt.steps import Action
from tmt.utils import GeneralError, Path, field, key_to_option


@dataclasses.dataclass
class DiscoverStepData(tmt.steps.WhereableStepData, tmt.steps.StepData):
    dist_git_source: bool = field(
        default=False,
        option='--dist-git-source',
        is_flag=True,
        help='Download DistGit sources and ``rpmbuild -bp`` them (can be skipped).'
        )

    # TODO: use enum!
    dist_git_type: Optional[str] = field(
        default=None,
        option='--dist-git-type',
        choices=tmt.utils.get_distgit_handler_names,
        help='Use the provided DistGit handler instead of the auto detection.'
        )

    dist_git_download_only: bool = field(
        default=False,
        option="--dist-git-download-only",
        is_flag=True,
        help="Just download the sources. No ``rpmbuild -bp``, "
        "nor installation of require or buildddeps happens.",
        )

    dist_git_install_builddeps: bool = field(
        default=False,
        option="--dist-git-install-builddeps",
        is_flag=True,
        help="Install package build dependencies according to the specfile.",
        )

    dist_git_require: list['tmt.base.DependencySimple'] = field(
        default_factory=list,
        option="--dist-git-require",
        metavar='PACKAGE',
        multiple=True,
        help='Additional required package to be present before sources are prepared.',
        # *simple* requirements only
        normalize=lambda key_address, value, logger: tmt.base.assert_simple_dependencies(
            tmt.base.normalize_require(key_address, value, logger),
            "'dist_git_require' can be simple packages only",
            logger),
        serialize=lambda packages: [package.to_spec() for package in packages],
        unserialize=lambda serialized: [
            tmt.base.DependencySimple.from_spec(package)
            for package in serialized
            ]
        )


DiscoverStepDataT = TypeVar('DiscoverStepDataT', bound=DiscoverStepData)


class DiscoverPlugin(tmt.steps.GuestlessPlugin[DiscoverStepDataT]):
    """ Common parent of discover plugins """

    # ignore[assignment]: as a base class, DiscoverStepData is not included in
    # DiscoverStepDataT.
    _data_class = DiscoverStepData  # type: ignore[assignment]

    # Methods ("how: ..." implementations) registered for the same step.
    _supported_methods: PluginRegistry[tmt.steps.Method] = PluginRegistry()

    @classmethod
    def base_command(
            cls,
            usage: str,
            method_class: Optional[type[click.Command]] = None) -> click.Command:
        """ Create base click command (common for all discover plugins) """

        # Prepare general usage message for the step
        if method_class:
            usage = Discover.usage(method_overview=usage)

        # Create the command
        @click.command(cls=method_class, help=usage)
        @click.pass_context
        @option(
            '-h', '--how', metavar='METHOD',
            help='Use specified method to discover tests.')
        @tmt.steps.PHASE_OPTIONS
        def discover(context: 'tmt.cli.Context', **kwargs: Any) -> None:
            context.obj.steps.add('discover')
            Discover.store_cli_invocation(context)

        return discover

    def tests(
            self,
            *,
            phase_name: Optional[str] = None,
            enabled: Optional[bool] = None) -> list['tmt.Test']:
        """
        Return discovered tests

        Each DiscoverPlugin has to implement this method.
        Should return a list of Test() objects.
        """
        raise NotImplementedError

    def download_distgit_source(
            self,
            distgit_dir: Path,
            target_dir: Path,
            handler_name: Optional[str] = None) -> None:
        """
        Download sources to the target_dir

        distgit_dir is path to the DistGit repository
        """
        tmt.utils.distgit_download(
            distgit_dir=distgit_dir,
            target_dir=target_dir,
            handler_name=handler_name,
            caller=self,
            logger=self._logger
            )

    def log_import_plan_details(self) -> None:
        """ Log details about the imported plan """
        parent = cast(Optional[tmt.steps.discover.Discover], self.parent)
        if parent and parent.plan._original_plan and \
                parent.plan._original_plan._remote_plan_fmf_id:
            remote_plan_id = parent.plan._original_plan._remote_plan_fmf_id
            # FIXME: cast() - https://github.com/python/mypy/issues/7981
            # Note the missing Optional for values - to_minimal_dict() would
            # not include unset keys, therefore all values should be valid.
            for key, value in cast(dict[str, str], remote_plan_id.to_minimal_spec()).items():
                self.verbose(f'import {key}', value, 'green')

    def post_dist_git(self, created_content: list[Path]) -> None:
        """ Discover tests after dist-git applied patches """
        pass

    def filter_for_rerun(self) -> None:
        """ Filter out passed tests from previous run data """
        assert isinstance(self.step.parent, tmt.base.Plan)  # narrow type
        old_results: Path = self.step.parent.last_run_execute / 'results.yaml'
        results = [
            Result.from_serialized(data) for data in
            tmt.utils.yaml_to_list(self.read(old_results))]
        results_failed: list[str] = []
        results_passed: list[Result] = []
        for result in results:
            if (
                    result.result is not tmt.result.ResultOutcome.PASS and
                    result.result is not tmt.result.ResultOutcome.INFO):
                results_failed.append(result.name)
            else:
                results_passed.append(result)

        # Overwrite previous run results to only include passed cases
        self.debug(
            f"Overwriting {old_results} to only include passed results: "
            f"{', '.join([result.name for result in results_passed])}")
        self.write(
            old_results,
            tmt.utils.dict_to_yaml([result.to_serialized() for result in results_passed]))

        tests_to_execute: list[tmt.base.Test] = []
        for test in self._tests:
            if test.name in results_failed:
                tests_to_execute.append(test)
        self._tests: list[tmt.base.Test] = tests_to_execute


class Discover(tmt.steps.Step):
    """ Gather information about test cases to be executed. """

    _plugin_base_class = DiscoverPlugin
    _preserved_workdir_members = ['step.yaml', 'tests.yaml']

    def __init__(
            self,
            *,
            plan: 'tmt.base.Plan',
            data: tmt.steps.RawStepDataArgument,
            logger: tmt.log.Logger) -> None:
        """ Store supported attributes, check for sanity """
        super().__init__(plan=plan, data=data, logger=logger)

        # Collection of discovered tests
        self._tests: dict[str, list[tmt.Test]] = {}

        # Test will be (re)discovered in other phases/steps
        self.extract_tests_later: bool = False

    def load(self) -> None:
        """ Load step data from the workdir """
        super().load()
        try:
            raw_test_data = tmt.utils.yaml_to_list(self.read(Path('tests.yaml')))

            self._tests = {}

            for raw_test_datum in raw_test_data:
                # The name of `discover` phases providing the test was added in 1.24.
                # Unfortunately, the field is required for correct work of `execute`,
                # now when it is parallel in nature. Without it, it's not possible
                # to pick the right `discover` phase which then provides the list
                # of tests to execute. Therefore raising an error instead of guessing
                # what the phase could be.
                if key_to_option('discover_phase') not in raw_test_datum:
                    # TODO: there should be a method for creating workdir-aware paths...
                    path = self.workdir / Path('tests.yaml') if self.workdir \
                        else Path('tests.yaml')

                    raise tmt.utils.BackwardIncompatibleDataError(
                        f"Could not load '{path}' whose format is not compatible "
                        "with tmt 1.24 and newer."
                        )

                phase_name = raw_test_datum.pop(key_to_option('discover_phase'))

                if phase_name not in self._tests:
                    self._tests[phase_name] = []

                self._tests[phase_name].append(tmt.Test.from_dict(
                    logger=self._logger,
                    mapping=raw_test_datum,
                    name=raw_test_datum['name'],
                    skip_validation=True))

        except tmt.utils.FileError:
            self.debug('Discovered tests not found.', level=2)

    def save(self) -> None:
        """ Save step data to the workdir """
        super().save()

        # Create tests.yaml with the full test data
        raw_test_data: list['tmt.export._RawExportedInstance'] = []

        for phase_name, phase_tests in self._tests.items():
            for test in phase_tests:
                if test.enabled is not True:
                    continue

                exported_test = test._export(include_internal=True)
                exported_test[key_to_option('discover_phase')] = phase_name

                raw_test_data.append(exported_test)

        self.write(Path('tests.yaml'), tmt.utils.dict_to_yaml(raw_test_data))

    def _filter_for_rerun(self) -> None:
        """ Filter out passed tests from previous run data """
        assert isinstance(self.parent, tmt.base.Plan)  # narrow type
        old_results: Path = self.parent.last_run_execute / 'results.yaml'
        results = [
            Result.from_serialized(data) for data in
            tmt.utils.yaml_to_list(self.read(old_results))]
        results_failed: list[Result] = []
        results_passed: list[Result] = []
        for result in results:
            if (
                    result.result is not tmt.result.ResultOutcome.PASS and
                    result.result is not tmt.result.ResultOutcome.INFO):
                results_failed.append(result)
            else:
                results_passed.append(result)

        # Save positive results to specific results.yaml
        old_results_positive: Path = (
            self.parent.last_run_execute / 'positive_results.yaml')
        self.debug(
            f"Save positive results from last run to {old_results_positive}, these are: "
            f"{', '.join([result.name for result in results_passed])}")
        self.write(
            old_results_positive,
            tmt.utils.dict_to_yaml([result.to_serialized() for result in results_passed]))

        # Filter out failed tests based on test name and serial number
        filtered_tests: dict[str, list[tmt.base.Test]] = {}
        for phase in self._tests:
            current_phase_filtered: list[tmt.base.Test] = []
            for test in self._tests[phase]:
                for result in results_failed:
                    if test.name == result.name and test.serial_number == result.serial_number:
                        current_phase_filtered.append(test)
            filtered_tests[phase] = current_phase_filtered
        self._tests = filtered_tests

    def _discover_from_execute(self) -> None:
        """ Check the execute step for possible shell script tests """

        # Check scripts for command line and data, convert to list if needed
        scripts = self.plan.execute.opt('script')
        if not scripts:
            scripts = getattr(self.plan.execute.data[0], 'script', [])
        if not scripts:
            return
        if isinstance(scripts, str):
            scripts = [scripts]

        # Avoid circular imports
        from tmt.steps.discover.shell import DiscoverShellData, TestDescription

        # Give a warning when discover step defined as well
        if self.data and not all(datum.is_bare for datum in self.data):
            raise tmt.utils.DiscoverError(
                "Use either 'discover' or 'execute' step "
                "to define tests, but not both.")

        if not isinstance(self.data[0], DiscoverShellData):
            # TODO: or should we rather create a new `shell` discovery step data,
            # and fill it with our tests? Before step data patch, `tests` attribute
            # was simply created as a list, with no check whether the step data and
            # plugin even support `data.tests`. Which e.g. `internal` does not.
            # Or should we find the first DiscoverShellData instance, use it, and
            # create a new one when no such entry exists yet?
            raise GeneralError(
                f'Cannot append tests from execute to non-shell step "{self.data[0].how}"')

        discover_step_data = self.data[0]

        # Check the execute step for possible custom duration limit
        # FIXME: cast() - https://github.com/teemtee/tmt/issues/1540
        duration = cast(
            str,
            getattr(
                self.plan.execute.data[0],
                'duration',
                tmt.base.DEFAULT_TEST_DURATION_L2))

        # Prepare the list of tests
        for index, script in enumerate(scripts):
            name = f'script-{str(index).zfill(2)}'
            discover_step_data.tests.append(
                TestDescription(name=name, test=script, duration=duration)
                )

    def wake(self) -> None:
        """ Wake up the step (process workdir and command line) """
        super().wake()

        # Check execute step for possible tests (unless already done)
        if self.status() is None:
            self._discover_from_execute()

        # Choose the right plugin and wake it up
        for data in self.data:
            # FIXME: cast() - see https://github.com/teemtee/tmt/issues/1599
            plugin = cast(
                DiscoverPlugin[DiscoverStepData],
                DiscoverPlugin.delegate(self, data=data))
            self._phases.append(plugin)
            plugin.wake()

        # Nothing more to do if already done and not asked to run again
        if self.status() == 'done' and not self.should_run_again:
            self.debug(
                'Discover wake up complete (already done before).', level=2)
        # Save status and step data (now we know what to do)
        else:
            self.status('todo')
            self.save()

    def summary(self) -> None:
        """ Give a concise summary of the discovery """
        # Summary of selected tests
        text = listed(len(self.tests(enabled=True)), 'test') + ' selected'
        self.info('summary', text, 'green', shift=1)
        # Test list in verbose mode
        for test in self.tests(enabled=True):
            self.verbose(test.name, color='red', shift=2)

    def go(self, force: bool = False) -> None:
        """ Discover all tests """
        super().go(force=force)

        # Nothing more to do if already done
        if self.status() == 'done':
            self.info('status', 'done', 'green', shift=1)
            self.summary()
            self.actions()
            return

        # Perform test discovery, gather discovered tests
        for phase in self.phases(classes=(Action, DiscoverPlugin)):
            if isinstance(phase, Action):
                phase.go()

            elif isinstance(phase, DiscoverPlugin):
                # Go and discover tests
                phase.go()

                self._tests[phase.name] = []

                # Prefix test name only if multiple plugins configured
                prefix = f'/{phase.name}' if len(self.phases()) > 1 else ''
                # Check discovered tests, modify test name/path
                for test in phase.tests(enabled=True):
                    test.name = f"{prefix}{test.name}"
                    test.path = Path(f"/{phase.safe_name}{test.path}")
                    # Update test environment with plan environment
                    test.environment.update(self.plan.environment)
                    self._tests[phase.name].append(test)

            else:
                raise GeneralError(f'Unexpected phase in discover step: {phase}')

        for test in self.tests():
            test.serial_number = self.plan.draw_test_serial_number(test)

        # Filter selected tests if this is a rerun
        if self.is_rerun:
            self._filter_for_rerun()

        # Show fmf identifiers for tests discovered in plan
        # TODO: This part should go into the 'fmf.py' module
        if self.opt('fmf_id'):
            if self.tests(enabled=True):
                export_fmf_ids: list[str] = []

                for test in self.tests(enabled=True):
                    fmf_id = test.fmf_id

                    if not fmf_id.url:
                        continue

                    exported = test.fmf_id.to_minimal_spec()

                    if fmf_id.default_branch and fmf_id.ref == fmf_id.default_branch:
                        exported.pop('ref')

                    export_fmf_ids.append(tmt.utils.dict_to_yaml(exported, start=True))

                click.echo(''.join(export_fmf_ids), nl=False)
            return

        # Give a summary, update status and save
        self.summary()
        self.status('done')
        self.save()

    def tests(
            self,
            *,
            phase_name: Optional[str] = None,
            enabled: Optional[bool] = None) -> list['tmt.Test']:
        def _iter_all_tests() -> Iterator['tmt.Test']:
            for phase_tests in self._tests.values():
                yield from phase_tests

        def _iter_phase_tests() -> Iterator['tmt.Test']:
            assert phase_name is not None

            yield from self._tests[phase_name]

        iterator = _iter_all_tests if phase_name is None else _iter_phase_tests

        if enabled is None:
            return list(iterator())

        return [test for test in iterator() if test.enabled is enabled]
