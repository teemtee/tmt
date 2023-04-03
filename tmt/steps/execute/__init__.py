import dataclasses
import re
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, List, Optional, Tuple, Type, cast

import click
import fmf
import pkg_resources

import tmt
import tmt.base
import tmt.steps
import tmt.utils
from tmt.result import Result, ResultGuestData, ResultOutcome
from tmt.steps import Action, Step, StepData
from tmt.steps.provision import Guest
from tmt.utils import GeneralError, Path

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
SCRIPTS_SRC_DIR = Path(pkg_resources.resource_filename(
    'tmt', 'steps/execute/scripts'))


@dataclass
class Script:
    """ Represents a script provided by the internal executor """
    path: Path
    aliases: List[Path]
    related_variables: List[str]


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
    TMT_REPORT_RESULT_SCRIPT,
    )


@dataclasses.dataclass
class ExecuteStepData(tmt.steps.WhereableStepData, tmt.steps.StepData):
    # TODO: ugly circular dependency (see tmt.base.DEFAULT_TEST_DURATION_L2)
    duration: str = '1h'
    exit_first: bool = False


class ExecutePlugin(tmt.steps.Plugin):
    """ Common parent of execute plugins """

    _data_class = ExecuteStepData

    # List of all supported methods aggregated from all plugins of the same step.
    _supported_methods: List[tmt.steps.Method] = []

    # Internal executor is the default implementation
    how = 'tmt'

    scripts: Tuple['Script', ...] = ()

    _login_after_test: Optional[tmt.steps.Login] = None

    def __init__(
            self,
            *,
            step: Step,
            data: StepData,
            workdir: tmt.utils.WorkdirArgumentType = None,
            logger: tmt.log.Logger) -> None:
        super().__init__(logger=logger, step=step, data=data, workdir=workdir)
        if tmt.steps.Login._opt('test'):
            self._login_after_test = tmt.steps.Login(logger=logger, step=self.step, order=90)

    @classmethod
    def base_command(
            cls,
            usage: str,
            method_class: Optional[Type[click.Command]] = None) -> click.Command:
        """ Create base click command (common for all execute plugins) """

        # Prepare general usage message for the step
        if method_class:
            usage = Execute.usage(method_overview=usage)

        # Create the command
        @click.command(cls=method_class, help=usage)
        @click.pass_context
        @click.option(
            '-h', '--how', metavar='METHOD',
            help='Use specified method for test execution.')
        def execute(context: 'tmt.cli.Context', **kwargs: Any) -> None:
            context.obj.steps.add('execute')
            Execute._save_context(context)

        return execute

    @classmethod
    def options(cls, how: Optional[str] = None) -> List[tmt.options.ClickOptionDecoratorType]:
        # Add option to exit after the first test failure
        return [
            click.option(
                '-x', '--exit-first', is_flag=True,
                help='Stop execution after the first test failure.'),
            ] + super().options(how)

    def go(
            self,
            *,
            guest: 'Guest',
            environment: Optional[tmt.utils.EnvironmentType] = None,
            logger: tmt.log.Logger) -> None:
        super().go(guest=guest, environment=environment, logger=logger)
        logger.verbose(
            'exit-first', self.get('exit-first', default=False),
            'green', level=2)

    @property
    def discover(self) -> tmt.steps.discover.Discover:
        """ Return discover plugin instance """
        # This is necessary so that upgrade plugin can inject a fake discover

        return self.step.plan.discover

    def data_path(
            self,
            test: "tmt.Test",
            guest: Guest,
            filename: Optional[str] = None,
            full: bool = False,
            create: bool = False) -> Path:
        """
        Prepare full/relative test data directory/file path

        Construct test data directory path for given test, create it
        if requested and return the full or relative path to it (if
        filename not provided) or to the given data file otherwise.
        """
        # Prepare directory path, create if requested
        assert self.step.workdir is not None  # narrow type
        directory = self.step.workdir \
            / TEST_DATA \
            / 'guest' \
            / guest.name \
            / f'{test.name.lstrip("/") or "default"}-{test.serialnumber}'
        if create and not directory.is_dir():
            directory.joinpath(TEST_DATA).mkdir(parents=True)
        if not filename:
            return directory
        path = directory / filename
        return path if full else path.relative_to(self.step.workdir)

    def prepare_tests(self, guest: Guest) -> List["tmt.Test"]:
        """
        Prepare discovered tests for testing

        Check which tests have been discovered, for each test prepare
        the aggregated metadata in a file under the test data directory
        and finally return a list of discovered tests.
        """
        tests: List[tmt.Test] = self.discover.tests()
        for test in tests:
            metadata_filename = self.data_path(
                test, guest, filename=TEST_METADATA_FILENAME, full=True, create=True)
            self.write(
                metadata_filename, tmt.utils.dict_to_yaml(test._metadata))
        return tests

    def prepare_scripts(self, guest: "tmt.steps.provision.Guest") -> None:
        """
        Prepare additional scripts for testing
        """
        # Install all scripts on guest
        for script in self.scripts:
            source = SCRIPTS_SRC_DIR / script.path.name

            for dest in [script.path] + script.aliases:
                guest.push(
                    source=source,
                    destination=dest,
                    options=["-p", "--chmod=755"],
                    superuser=True)

    def check_shell(self, test: "tmt.Test", guest: Guest) -> List["tmt.Result"]:
        """ Check result of a shell test """
        assert test.returncode is not None
        assert test.real_duration is not None
        note = None

        try:
            # Process the exit code and prepare the log path
            result = {0: ResultOutcome.PASS, 1: ResultOutcome.FAIL}[test.returncode]
        except KeyError:
            result = ResultOutcome.ERROR
            # Add note about the exceeded duration
            if test.returncode == tmt.utils.PROCESS_TIMEOUT:
                note = 'timeout'
                self.timeout_hint(test, guest)

        return [tmt.Result.from_test(
            test=test,
            result=result,
            log=[self.data_path(test, guest, TEST_OUTPUT_FILENAME)],
            note=note,
            duration=test.real_duration,
            guest=guest)]

    def check_beakerlib(self, test: "tmt.Test", guest: Guest) -> List["tmt.Result"]:
        """ Check result of a beakerlib test """
        # Initialize data, prepare log paths
        note: Optional[str] = None
        log: List[Path] = []
        for filename in [TEST_OUTPUT_FILENAME, 'journal.txt']:
            if self.data_path(test, guest, filename, full=True).is_file():
                log.append(self.data_path(test, guest, filename))

        # Check beakerlib log for the result
        try:
            beakerlib_results_file = self.data_path(test, guest, 'TestResults', full=True)
            results = self.read(beakerlib_results_file, level=3)
        except tmt.utils.FileError:
            self.debug(f"Unable to read '{beakerlib_results_file}'.", level=3)
            note = 'beakerlib: TestResults FileError'

            return [tmt.Result.from_test(
                test=test,
                result=ResultOutcome.ERROR,
                note=note,
                log=log,
                duration=test.real_duration,
                guest=guest)]

        search_result = re.search('TESTRESULT_RESULT_STRING=(.*)', results)
        # States are: started, incomplete and complete
        # FIXME In quotes until beakerlib/beakerlib/pull/92 is merged
        search_state = re.search(r'TESTRESULT_STATE="?(\w+)"?', results)

        if search_result is None or search_state is None:
            self.debug(
                f"No result or state found in '{beakerlib_results_file}'.",
                level=3)
            note = 'beakerlib: Result/State missing'
            return [tmt.Result.from_test(
                test=test,
                result=ResultOutcome.ERROR,
                note=note,
                log=log,
                duration=test.real_duration,
                guest=guest)]

        result = search_result.group(1)
        state = search_state.group(1)

        # Check if it was killed by timeout (set by tmt executor)
        actual_result = ResultOutcome.ERROR
        if test.returncode == tmt.utils.PROCESS_TIMEOUT:
            note = 'timeout'
            self.timeout_hint(test, guest)
        # Test results should be in complete state
        elif state != 'complete':
            note = f"beakerlib: State '{state}'"
        # Finally we have a valid result
        else:
            actual_result = ResultOutcome.from_spec(result.lower())
        return [tmt.Result.from_test(
            test=test,
            result=actual_result,
            note=note,
            log=log,
            duration=test.real_duration,
            guest=guest)]

    def check_result_file(self, test: "tmt.Test", guest: Guest) -> List["tmt.Result"]:
        """
        Check result file created by tmt-report-result

        Extract the test result from the result file if it exists and
        return a Result instance. Raise the FileError exception when no
        test result file is found.
        """
        report_result_path = self.data_path(test, guest, full=True) \
            / tmt.steps.execute.TEST_DATA \
            / TMT_REPORT_RESULT_SCRIPT.created_file

        # Nothing to do if there's no result file
        if not report_result_path.exists():
            raise tmt.utils.FileError(f"Results file '{report_result_path}' does not exist.")

        # Check the test result
        self.debug("The report-result output file detected.", level=3)
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
            test=test,
            result=actual_result,
            log=[self.data_path(test, guest, TEST_OUTPUT_FILENAME)],
            duration=test.real_duration,
            note=note,
            guest=guest)]

    def check_custom_results(self, test: "tmt.Test", guest: Guest) -> List["tmt.Result"]:
        """
        Process custom results.yaml file created by the test itself.
        """
        self.debug("Processing custom 'results.yaml' file created by the test itself.")

        test_data_path = self.data_path(test, guest, full=True) \
            / tmt.steps.execute.TEST_DATA

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
            log_path_base = self.data_path(
                test,
                guest,
                full=False,
                filename=tmt.steps.execute.TEST_DATA)
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
            partial_result.serialnumber = test.serialnumber

            # Enforce the correct guest info
            partial_result.guest = ResultGuestData(name=guest.name, role=guest.role)

            custom_results.append(partial_result)

        return custom_results

    def check_abort_file(self, test: "tmt.Test", guest: Guest) -> bool:
        """
        Check for an abort file created by tmt-abort

        Returns whether an abort file is present (i.e. abort occurred).
        """
        return self.data_path(test, guest, full=True).joinpath(
            tmt.steps.execute.TEST_DATA,
            TMT_ABORT_SCRIPT.created_file).exists()

    @staticmethod
    def test_duration(start: float, end: float) -> str:
        """ Convert duration to a human readable format """
        return time.strftime("%H:%M:%S", time.gmtime(end - start))

    def timeout_hint(self, test: "tmt.Test", guest: Guest) -> None:
        """ Append a duration increase hint to the test output """
        output = self.data_path(test, guest, TEST_OUTPUT_FILENAME, full=True)
        self.write(
            output,
            f"\nMaximum test time '{test.duration}' exceeded.\n"
            f"Adjust the test 'duration' attribute if necessary.\n"
            f"https://tmt.readthedocs.io/en/stable/spec/tests.html#duration\n",
            mode='a', level=3)

    def results(self) -> List["tmt.Result"]:
        """ Return test results """
        raise NotImplementedError


class Execute(tmt.steps.Step):
    """
    Run tests using the specified executor.
    """

    # Internal executor is the default implementation
    DEFAULT_HOW = 'tmt'

    _plugin_base_class = ExecutePlugin

    _preserved_files = ['step.yaml', 'results.yaml', 'data']

    def __init__(
            self,
            *,
            plan: "tmt.Plan",
            data: tmt.steps.RawStepDataArgument,
            logger: tmt.log.Logger) -> None:
        """ Initialize execute step data """
        super().__init__(plan=plan, data=data, logger=logger)
        # List of Result() objects representing test results
        self._results: List[tmt.Result] = []

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
                "Multiple execute steps defined in '{}'.".format(self.plan))

        # Choose the right plugin and wake it up
        # FIXME: cast() - see https://github.com/teemtee/tmt/issues/1599
        executor = cast(ExecutePlugin, ExecutePlugin.delegate(self, data=self.data[0]))
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
        tests = fmf.utils.listed(self.results(), 'test')
        self.info('summary', f'{tests} executed', 'green', shift=1)

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
        for guest in self.plan.provision.guests():
            for phase in self.phases(classes=(Action, ExecutePlugin)):
                if not phase.enabled_on_guest(guest):
                    continue

                if isinstance(phase, Action):
                    phase.go()

                elif isinstance(phase, ExecutePlugin):
                    # TODO: re-injecting the logger already given to the guest,
                    # with multihost support heading our way this will change
                    # to be not so trivial.
                    phase.go(guest=guest, logger=guest._logger)

                    self._results.extend(phase.results())

                else:
                    raise GeneralError(f'Unexpected phase in execute step: {phase}')

        # Give a summary, update status and save
        self.summary()
        self.status('done')
        self.save()

    def results(self) -> List["tmt.result.Result"]:
        """
        Results from executed tests

        Return a dictionary with test results according to the spec:
        https://tmt.readthedocs.io/en/latest/spec/plans.html#execute
        """
        return self._results
