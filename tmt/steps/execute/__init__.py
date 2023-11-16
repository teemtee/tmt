import copy
import dataclasses
import datetime
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Optional, TypeVar, cast

import click
import fmf

import tmt
import tmt.base
import tmt.log
import tmt.steps
import tmt.utils
from tmt.checks import CheckEvent
from tmt.options import option
from tmt.plugins import PluginRegistry
from tmt.queue import TaskOutcome
from tmt.result import CheckResult, Result, ResultGuestData, ResultOutcome
from tmt.steps import Action, PhaseQueue, QueuedPhase, Step
from tmt.steps.discover import Discover, DiscoverPlugin, DiscoverStepData
from tmt.steps.provision import Guest
from tmt.utils import Path, Stopwatch, field

if TYPE_CHECKING:
    import tmt.cli
    import tmt.options
    import tmt.steps.discover
    import tmt.steps.provision

# Test data directory name
TEST_DATA = 'data'

# Default test framework
DEFAULT_FRAMEWORK = 'shell'

# The main test output filename
TEST_OUTPUT_FILENAME = 'output.txt'

# Metadata file with details about the current test
TEST_METADATA_FILENAME = 'metadata.yaml'

# Scripts source directory
SCRIPTS_SRC_DIR = tmt.utils.resource_files('steps/execute/scripts')


@dataclass
class Script:
    """ Represents a script provided by the internal executor """
    path: Path
    aliases: list[Path]
    related_variables: list[str]


@dataclass
class ScriptCreatingFile(Script):
    """ Represents a script which creates a file """
    created_file: str


# Script handling reboots, in restraint compatible fashion
TMT_REBOOT_SCRIPT = ScriptCreatingFile(
    path=Path("/usr/local/bin/tmt-reboot"),
    aliases=[
        Path("/usr/local/bin/rstrnt-reboot"),
        Path("/usr/local/bin/rhts-reboot")],
    related_variables=[
        "TMT_REBOOT_COUNT",
        "REBOOTCOUNT",
        "RSTRNT_REBOOTCOUNT"],
    created_file="reboot-request"
    )

TMT_REBOOT_CORE_SCRIPT = Script(
    path=Path("/usr/local/bin/tmt-reboot-core"),
    aliases=[],
    related_variables=[])

# Script handling result reporting, in restraint compatible fashion
TMT_REPORT_RESULT_SCRIPT = ScriptCreatingFile(
    path=Path("/usr/local/bin/tmt-report-result"),
    aliases=[
        Path("/usr/local/bin/rstrnt-report-result"),
        Path("/usr/local/bin/rhts-report-result")],
    related_variables=[],
    created_file="restraint-result"
    )

# Script for archiving a file, usable for BEAKERLIB_COMMAND_SUBMIT_LOG
TMT_FILE_SUBMIT_SCRIPT = Script(
    path=Path("/usr/local/bin/tmt-file-submit"),
    aliases=[
        Path("/usr/local/bin/rstrnt-report-log"),
        Path("/usr/local/bin/rhts-submit-log"),
        Path("/usr/local/bin/rhts_submit_log")],
    related_variables=[]
    )

# Script handling text execution abortion, in restraint compatible fashion
TMT_ABORT_SCRIPT = ScriptCreatingFile(
    path=Path("/usr/local/bin/tmt-abort"),
    aliases=[
        Path("/usr/local/bin/rstrnt-abort"),
        Path("/usr/local/bin/rhts-abort")],
    related_variables=[],
    created_file="abort"
    )

# List of all available scripts
SCRIPTS = (
    TMT_ABORT_SCRIPT,
    TMT_FILE_SUBMIT_SCRIPT,
    TMT_REBOOT_SCRIPT,
    TMT_REBOOT_CORE_SCRIPT,
    TMT_REPORT_RESULT_SCRIPT,
    )


@dataclasses.dataclass
class ExecuteStepData(tmt.steps.WhereableStepData, tmt.steps.StepData):
    duration: str = field(
        # TODO: ugly circular dependency (see tmt.base.DEFAULT_TEST_DURATION_L2)
        default='1h',
        option='--duration',
        help='The maximal time allowed for the test to run.'
        )
    exit_first: bool = field(
        default=False,
        option=('-x', '--exit-first'),
        is_flag=True,
        help='Stop execution after the first test failure.')


ExecuteStepDataT = TypeVar('ExecuteStepDataT', bound=ExecuteStepData)


@dataclasses.dataclass
class TestInvocation:
    """
    A bundle describing one test invocation.

    Describes a ``test`` invoked on a particular ``guest`` under the
    supervision of an ``execute`` plugin ``phase``.
    """

    phase: 'ExecutePlugin[Any]'
    test: 'tmt.base.Test'
    guest: Guest

    def data_path(
            self,
            filename: Optional[str] = None,
            full: bool = False,
            create: bool = False) -> Path:
        """
        Prepare full/relative test data directory/file path.

        Construct test data directory path for given test, create it
        if requested and return the full or relative path to it (if
        filename not provided) or to the given data file otherwise.
        """
        # Prepare directory path, create if requested
        assert self.phase.step.workdir is not None  # narrow type
        directory = self.phase.step.workdir \
            / TEST_DATA \
            / 'guest' \
            / self.guest.safe_name \
            / f'{self.test.safe_name.lstrip("/") or "default"}-{self.test.serial_number}'
        if create and not directory.is_dir():
            directory.joinpath(TEST_DATA).mkdir(parents=True)
        if not filename:
            return directory
        path = directory / filename
        return path if full else path.relative_to(self.phase.step.workdir)


class ExecutePlugin(tmt.steps.Plugin[ExecuteStepDataT]):
    """ Common parent of execute plugins """

    # ignore[assignment]: as a base class, ExecuteStepData is not included in
    # ExecuteStepDataT.
    _data_class = ExecuteStepData  # type: ignore[assignment]

    # Methods ("how: ..." implementations) registered for the same step.
    _supported_methods: PluginRegistry[tmt.steps.Method] = PluginRegistry()

    # Internal executor is the default implementation
    how = 'tmt'

    scripts: tuple['Script', ...] = ()

    _login_after_test: Optional[tmt.steps.Login] = None

    #: If set, plugin should run tests only from this discover phase.
    discover_phase: Optional[str] = None

    def __init__(
            self,
            *,
            step: Step,
            data: ExecuteStepDataT,
            workdir: tmt.utils.WorkdirArgumentType = None,
            logger: tmt.log.Logger) -> None:
        super().__init__(logger=logger, step=step, data=data, workdir=workdir)
        self._results: list[tmt.Result] = []
        if tmt.steps.Login._opt('test'):
            self._login_after_test = tmt.steps.Login(logger=logger, step=self.step, order=90)

    @classmethod
    def base_command(
            cls,
            usage: str,
            method_class: Optional[type[click.Command]] = None) -> click.Command:
        """ Create base click command (common for all execute plugins) """

        # Prepare general usage message for the step
        if method_class:
            usage = Execute.usage(method_overview=usage)

        # Create the command
        @click.command(cls=method_class, help=usage)
        @click.pass_context
        @option(
            '-h', '--how', metavar='METHOD',
            help='Use specified method for test execution.')
        def execute(context: 'tmt.cli.Context', **kwargs: Any) -> None:
            context.obj.steps.add('execute')
            Execute.store_cli_invocation(context)

        return execute

    def go(
            self,
            *,
            guest: 'Guest',
            environment: Optional[tmt.utils.EnvironmentType] = None,
            logger: tmt.log.Logger) -> None:
        super().go(guest=guest, environment=environment, logger=logger)
        logger.verbose('exit-first', self.data.exit_first, 'green', level=2)

    @property
    def discover(self) -> Discover:
        """ Return discover plugin instance """
        # This is necessary so that upgrade plugin can inject a fake discover

        return self.step.plan.discover

    @discover.setter
    def discover(self, plugin: Optional[DiscoverPlugin[DiscoverStepData]]) -> None:
        self._discover = plugin

    def prepare_tests(self, guest: Guest) -> list[TestInvocation]:
        """
        Prepare discovered tests for testing

        Check which tests have been discovered, for each test prepare
        the aggregated metadata in a file under the test data directory
        and finally return a list of discovered tests.
        """
        invocations: list[TestInvocation] = []

        for test in self.discover.tests(phase_name=self.discover_phase, enabled=True):
            invocation = TestInvocation(phase=self, test=test, guest=guest)
            invocations.append(invocation)

            metadata_filename = invocation.data_path(
                filename=TEST_METADATA_FILENAME, full=True, create=True)
            self.write(
                metadata_filename, tmt.utils.dict_to_yaml(test._metadata))

        return invocations

    def prepare_scripts(self, guest: "tmt.steps.provision.Guest") -> None:
        """
        Prepare additional scripts for testing
        """
        # Install all scripts on guest
        for script in self.scripts:
            source = SCRIPTS_SRC_DIR / script.path.name

            for dest in [script.path, *script.aliases]:
                guest.push(
                    source=source,
                    destination=dest,
                    options=["-p", "--chmod=755"],
                    superuser=guest.facts.is_superuser is not True)

    def _tmt_report_results_filepath(self, invocation: TestInvocation) -> Path:
        """ Create path to test's ``tmt-report-result`` file """

        return invocation.data_path(full=True) \
            / TEST_DATA \
            / TMT_REPORT_RESULT_SCRIPT.created_file

    def load_tmt_report_results(self, invocation: TestInvocation) -> list["tmt.Result"]:
        """
        Load results from a file created by ``tmt-report-result`` script.

        :returns: list of :py:class:`tmt.Result` instances loaded from the file,
            or an empty list if the file does not exist.
        """

        report_result_path = self._tmt_report_results_filepath(invocation)

        # Nothing to do if there's no result file
        if not report_result_path.exists():
            self.debug(f"tmt-report-results file '{report_result_path}' does not exist.")
            return []

        # Check the test result
        self.debug(f"tmt-report-results file '{report_result_path} detected.")

        with open(report_result_path) as result_file:
            result_list = [line for line in result_file.readlines() if "TESTRESULT" in line]
        if not result_list:
            raise tmt.utils.ExecuteError(
                f"Test result not found in result file '{report_result_path}'.")
        result = result_list[0].split("=")[1].strip()

        # Map the restraint result to the corresponding tmt value
        actual_result = ResultOutcome.ERROR
        note: Optional[str] = None

        try:
            actual_result = ResultOutcome(result.lower())
        except ValueError:
            if result == 'SKIP':
                actual_result = ResultOutcome.INFO
            else:
                note = f"invalid test result '{result}' in result file"

        return [tmt.Result.from_test(
            test=invocation.test,
            result=actual_result,
            log=[invocation.data_path(TEST_OUTPUT_FILENAME)],
            note=note,
            guest=invocation.guest)]

    def load_custom_results(self, invocation: TestInvocation) -> list["tmt.Result"]:
        """
        Process custom results.yaml file created by the test itself.
        """
        test, guest = invocation.test, invocation.guest

        test_data_path = invocation.data_path(full=True) / TEST_DATA

        custom_results_path_yaml = test_data_path / 'results.yaml'
        custom_results_path_json = test_data_path / 'results.json'

        if custom_results_path_yaml.exists():
            with open(custom_results_path_yaml) as results_file:
                results = tmt.utils.yaml_to_list(results_file)

        elif custom_results_path_json.exists():
            with open(custom_results_path_json) as results_file:
                results = tmt.utils.json_to_list(results_file)

        else:
            return [tmt.Result.from_test(
                test=test,
                note=f"custom results file not found in '{test_data_path}'",
                result=ResultOutcome.ERROR,
                guest=guest)]

        if not results:
            return [tmt.Result.from_test(
                test=test,
                note="custom results are empty",
                result=ResultOutcome.ERROR,
                guest=guest)]

        custom_results = []
        for partial_result_data in results:
            partial_result = tmt.Result.from_serialized(partial_result_data)

            # Name '/' means the test itself
            if partial_result.name == '/':
                partial_result.name = test.name

            else:
                if not partial_result.name.startswith('/'):
                    if partial_result.note and isinstance(partial_result.note, str):
                        partial_result.note += ", custom test result name should start with '/'"
                    else:
                        partial_result.note = "custom test result name should start with '/'"
                    partial_result.name = '/' + partial_result.name
                partial_result.name = test.name + partial_result.name

            # Fix log paths as user provides relative path to TMT_TEST_DATA
            # but Result has to point relative to the execute workdir
            log_path_base = invocation.data_path(full=False, filename=TEST_DATA)
            partial_result.log = [log_path_base / log for log in partial_result.log]

            # TODO: this might need more care: the test has been assigned a serial
            # number, which is now part of its data directory path. Now, the test
            # produced custom results, with possibly many, many results. What
            # is the serial number of a test they belong to?
            #
            # A naive implementation assigns them the serial number of the test
            # that spawned them, but it can be argued the test may effectively
            # create results for virtual tests, would they deserve their own
            # serial numbers? On the hand, there's no risk of on-disk collision
            # as these tests do not really exist, they do not have their own
            # data directories, they are all confined into its parent test's
            # directory. And the serial number correspondence in results.yaml
            # can be useful, for grouping results that belong to the same tests.
            partial_result.serial_number = test.serial_number

            # Enforce the correct guest info
            partial_result.guest = ResultGuestData(name=guest.name, role=guest.role)

            # For the result representing the test itself, set the duration
            # and timestamps to what tmt measured.
            if partial_result.name == test.name:
                partial_result.start_time = test.start_time
                partial_result.end_time = test.end_time
                partial_result.duration = test.real_duration

            custom_results.append(partial_result)

        return custom_results

    def extract_results(
            self,
            invocation: TestInvocation,
            logger: tmt.log.Logger) -> list[Result]:
        """ Check the test result """

        self.debug(f"Extract results of '{invocation.test.name}'.")

        if invocation.test.result == 'custom':
            return self.load_custom_results(invocation)

        if self._tmt_report_results_filepath(invocation).exists():
            return self.load_tmt_report_results(invocation)

        return invocation.test.test_framework.extract_results(invocation, logger)

    def check_abort_file(self, invocation: TestInvocation) -> bool:
        """
        Check for an abort file created by tmt-abort

        Returns whether an abort file is present (i.e. abort occurred).
        """
        return (invocation.data_path(full=True)
                / TEST_DATA
                / TMT_ABORT_SCRIPT.created_file).exists()

    @staticmethod
    def format_timestamp(timestamp: datetime.datetime) -> str:
        """ Convert timestamp to a human readable format """

        return timestamp.isoformat()

    @staticmethod
    def format_duration(duration: datetime.timedelta) -> str:
        """ Convert duration to a human readable format """

        # A helper variable to hold the duration while we cut away days, hours and seconds.
        counter = int(duration.total_seconds())

        hours, counter = divmod(counter, 3600)
        minutes, seconds = divmod(counter, 60)

        return f'{hours:02}:{minutes:02}:{seconds:02}'

    def timeout_hint(self, invocation: TestInvocation) -> None:
        """ Append a duration increase hint to the test output """
        output = invocation.data_path(TEST_OUTPUT_FILENAME, full=True)
        self.write(
            output,
            f"\nMaximum test time '{invocation.test.duration}' exceeded.\n"
            f"Adjust the test 'duration' attribute if necessary.\n"
            f"https://tmt.readthedocs.io/en/stable/spec/tests.html#duration\n",
            mode='a', level=3)

    def results(self) -> list["tmt.Result"]:
        """ Return test results """
        raise NotImplementedError

    def _run_checks_for_test(
            self,
            *,
            event: CheckEvent,
            invocation: TestInvocation,
            environment: Optional[tmt.utils.EnvironmentType] = None,
            logger: tmt.log.Logger) -> list[CheckResult]:

        results: list[CheckResult] = []

        for check in invocation.test.check:
            with Stopwatch() as timer:
                check_results = check.go(
                    event=event,
                    invocation=invocation,
                    environment=environment,
                    logger=logger)

            for result in check_results:
                result.event = event

                result.start_time = self.format_timestamp(timer.start_time)
                result.end_time = self.format_timestamp(timer.end_time)
                result.duration = self.format_duration(timer.duration)

            results += check_results

        return results

    def run_checks_before_test(
            self,
            *,
            invocation: TestInvocation,
            environment: Optional[tmt.utils.EnvironmentType] = None,
            logger: tmt.log.Logger) -> list[CheckResult]:
        return self._run_checks_for_test(
            event=CheckEvent.BEFORE_TEST,
            invocation=invocation,
            environment=environment,
            logger=logger
            )

    def run_checks_after_test(
            self,
            *,
            invocation: TestInvocation,
            environment: Optional[tmt.utils.EnvironmentType] = None,
            logger: tmt.log.Logger) -> list[CheckResult]:
        return self._run_checks_for_test(
            event=CheckEvent.AFTER_TEST,
            invocation=invocation,
            environment=environment,
            logger=logger
            )


class Execute(tmt.steps.Step):
    """
    Run tests using the specified executor.
    """

    # Internal executor is the default implementation
    DEFAULT_HOW = 'tmt'

    _plugin_base_class = ExecutePlugin

    _preserved_workdir_members = ['step.yaml', 'results.yaml', 'data']

    def __init__(
            self,
            *,
            plan: "tmt.Plan",
            data: tmt.steps.RawStepDataArgument,
            logger: tmt.log.Logger) -> None:
        """ Initialize execute step data """
        super().__init__(plan=plan, data=data, logger=logger)
        # List of Result() objects representing test results
        self._results: list[tmt.Result] = []

    def load(self) -> None:
        """ Load test results """
        super().load()
        try:
            results = tmt.utils.yaml_to_list(self.read(Path('results.yaml')))
            self._results = [Result.from_serialized(data) for data in results]
        except tmt.utils.FileError:
            self.debug('Test results not found.', level=2)

    def save(self) -> None:
        """ Save test results to the workdir """
        super().save()
        results = [result.to_serialized() for result in self.results()]
        self.write(Path('results.yaml'), tmt.utils.dict_to_yaml(results))

    def wake(self) -> None:
        """ Wake up the step (process workdir and command line) """
        super().wake()

        # There should be just a single definition
        if len(self.data) > 1:
            raise tmt.utils.SpecificationError(
                f"Multiple execute steps defined in '{self.plan}'.")

        # Choose the right plugin and wake it up
        # FIXME: cast() - see https://github.com/teemtee/tmt/issues/1599
        executor = cast(
            ExecutePlugin[ExecuteStepData],
            ExecutePlugin.delegate(self, data=self.data[0]))
        executor.wake()
        self._phases.append(executor)

        # Nothing more to do if already done
        if self.status() == 'done':
            self.debug(
                'Execute wake up complete (already done before).', level=2)
        # Save status and step data (now we know what to do)
        else:
            self.status('todo')
            self.save()

    def summary(self) -> None:
        """ Give a concise summary of the execution """
        executed_tests = [r for r in self.results() if r.result != ResultOutcome.SKIP]
        skipped_tests = [r for r in self.results() if r.result == ResultOutcome.SKIP]

        message = [
            fmf.utils.listed(executed_tests, 'test') + ' executed'
            ]

        if skipped_tests:
            message.append(fmf.utils.listed(skipped_tests, 'test') + ' skipped')

        self.info('summary', ', '.join(message), 'green', shift=1)

    def go(self) -> None:
        """ Execute tests """
        super().go()

        # Nothing more to do if already done
        if self.status() == 'done':
            self.info('status', 'done', 'green', shift=1)
            self.summary()
            self.actions()
            return

        # Make sure that guests are prepared
        if not self.plan.provision.guests():
            raise tmt.utils.ExecuteError("No guests available for execution.")

        # Execute the tests, store results
        queue: PhaseQueue[ExecuteStepData] = PhaseQueue(
            'execute',
            self._logger.descend(logger_name=f'{self}.queue'))

        execute_phases = self.phases(classes=(ExecutePlugin,))
        assert len(execute_phases) == 1

        for phase in self.phases(classes=(Action, ExecutePlugin)):
            if isinstance(phase, Action):
                queue.enqueue(
                    phase=phase,
                    guests=[
                        guest
                        for guest in self.plan.provision.guests()
                        if phase.enabled_on_guest(guest)
                        ])

            else:
                # A single execute plugin is expected to process (potentialy)
                # multiple discover phases. There must be a way to tell the execute
                # plugin which discover phase to focus on. Unfortunately, the
                # current way is the execute plugin checking its `discover`
                # attribute. For each discover phase, we need a copy of the execute
                # plugin, so we could point it to that discover phase rather than
                # let is "see" all tests, or test in different discover phase.
                for discover in self.plan.discover.phases(classes=(DiscoverPlugin,)):
                    phase_copy = cast(ExecutePlugin[ExecuteStepData], copy.copy(phase))
                    phase_copy.discover_phase = discover.name

                    queue.enqueue(
                        phase=phase_copy,
                        guests=[
                            guest
                            for guest in self.plan.provision.guests()
                            if discover.enabled_on_guest(guest)
                            ])

        failed_phases: list[TaskOutcome[QueuedPhase[ExecuteStepData]]] = []

        for phase_outcome in queue.run():
            if phase_outcome.exc:
                phase_outcome.logger.fail(str(phase_outcome.exc))

                failed_phases.append(phase_outcome)
                continue

        # Execute plugins do not return results. Instead, plugin collects results
        # in its internal `_results` list. To accomodate for different discover
        # phases, we create a copy of the execute phase for each discover phase
        # we have. All these copies share the `_results` list, and append to it.
        #
        # Therefore, avoid collecting results from phases when iterating the
        # outcomes - such a process would encounter the list multiple times,
        # which would make results appear several times. Instead, we can reach
        # into the original plugin, and use it as a singleton "entry point" to
        # access all collected `_results`.
        self._results += execute_phases[0].results()

        if failed_phases:
            # TODO: needs a better message...
            raise tmt.utils.GeneralError(
                'execute step failed',
                causes=[outcome.exc for outcome in failed_phases if outcome.exc is not None]
                )

        # To separate "execute" from the follow-up logging visually
        self.info('')

        # Give a summary, update status and save
        self.summary()
        self.status('done')
        self.save()

    def results(self) -> list["tmt.result.Result"]:
        """
        Results from executed tests

        Return a dictionary with test results according to the spec:
        https://tmt.readthedocs.io/en/latest/spec/plans.html#execute
        """
        return self._results
