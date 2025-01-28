import copy
import dataclasses
import functools
import json
import os
import signal as _signal
import subprocess
import threading
from contextlib import suppress
from dataclasses import dataclass
from tempfile import NamedTemporaryFile
from typing import TYPE_CHECKING, Any, Callable, Optional, TypeVar, Union, cast

import click
import fmf
import fmf.utils

import tmt
import tmt.base
import tmt.log
import tmt.steps
import tmt.utils
from tmt.checks import CheckEvent
from tmt.options import option
from tmt.plugins import PluginRegistry
from tmt.result import CheckResult, Result, ResultGuestData, ResultInterpret, ResultOutcome
from tmt.steps import Action, ActionTask, PhaseQueue, PluginTask, Step
from tmt.steps.discover import Discover, DiscoverPlugin, DiscoverStepData
from tmt.steps.provision import Guest
from tmt.utils import (
    Command,
    Path,
    ShellScript,
    Stopwatch,
    field,
    format_duration,
    format_timestamp,
    )
from tmt.utils.templates import render_template_file

if TYPE_CHECKING:
    import tmt.cli
    import tmt.options
    import tmt.result
    import tmt.steps.discover
    import tmt.steps.provision

# Test data and checks directory names
TEST_DATA = 'data'
CHECK_DATA = 'checks'

# Default test framework
DEFAULT_FRAMEWORK = 'shell'

# The main test output filename
TEST_OUTPUT_FILENAME = 'output.txt'

# Metadata file with details about the current test
TEST_METADATA_FILENAME = 'metadata.yaml'

#: Scripts source directory
SCRIPTS_SRC_DIR = tmt.utils.resource_files('steps/execute/scripts')

#: The default scripts destination directory
DEFAULT_SCRIPTS_DEST_DIR = Path("/usr/local/bin")

#: The default scripts destination directory for rpm-ostree based distributions, https://github.com/teemtee/tmt/discussions/3260
DEFAULT_SCRIPTS_DEST_DIR_OSTREE = Path("/var/lib/tmt/scripts")

#: The tmt environment variable name for forcing ``SCRIPTS_DEST_DIR``
SCRIPTS_DEST_DIR_VARIABLE = 'TMT_SCRIPTS_DIR'


@dataclass
class Script:
    """
    Represents a script provided by the internal executor.

    Must be used as a context manager. The context manager returns
    the source filename.

    The source file is defined by the ``source_filename`` attribute and its
    location is relative to the directory specified via the :py:data:`SCRIPTS_SRC_DIR`
    variable. All scripts must be located in this directory.

    The default destination directory of the scripts is :py:data:`DEFAULT_SCRIPTS_DEST_DIR`.
    On ``rpm-ostree`` distributions like Fedora CoreOS, the default destination
    directory is :py:data:``DEFAULT_SCRIPTS_DEST_DIR_OSTREE``. The destination directory
    of the scripts can be forced by the script using ``destination_path`` attribute.

    The destination directory can be overridden using the environment variable defined
    by the :py:data:`DEFAULT_SCRIPTS_DEST_DIR_VARIABLE` variable.

    The ``enabled`` attribute can specify a function which is called with :py:class:`Guest`
    instance to evaluate if the script is enabled. This can be useful to optionally disable
    a script for specific guests.
    """

    source_filename: str
    destination_path: Optional[Path]
    aliases: list[str]
    related_variables: list[str]
    enabled: Callable[[Guest], bool]

    def __enter__(self) -> Path:
        return SCRIPTS_SRC_DIR / self.source_filename

    def __exit__(self, *args: object) -> None:
        pass


@dataclass
class ScriptCreatingFile(Script):
    """
    Represents a script which creates a file.

    See :py:class:`Script` for more details.
    """

    created_file: str


@dataclass
class ScriptTemplate(Script):
    """
    Represents a Jinja2 templated script.

    The source filename is constructed from the name of the file specified
    via the ``source_filename`` attribute, with the ``.j2`` suffix appended.
    The template file must be located in the directory specified
    via :py:data:`SCRIPTS_SRC_DIR` variable.
    """

    context: dict[str, str]

    _rendered_script_path: Optional[Path] = None

    def __enter__(self) -> Path:
        with NamedTemporaryFile(mode='w', delete=False) as rendered_script:
            rendered_script.write(render_template_file(
                SCRIPTS_SRC_DIR / f"{self.source_filename}.j2", None, **self.context))

        self._rendered_script_path = Path(rendered_script.name)

        return self._rendered_script_path

    def __exit__(self, *args: object) -> None:
        assert self._rendered_script_path
        os.unlink(self._rendered_script_path)


def effective_scripts_dest_dir(default: Path = DEFAULT_SCRIPTS_DEST_DIR) -> Path:
    """
    Find out what the actual scripts destination directory is.

    If the ``TMT_SCRIPTS_DIR`` environment variable is set, it is used
    as the scripts destination directory. Otherwise, the ``default``
    parameter path is returned.
    """

    return Path(os.environ.get(SCRIPTS_DEST_DIR_VARIABLE, default))


# Script handling reboots, in restraint compatible fashion
TMT_REBOOT_SCRIPT = ScriptCreatingFile(
    source_filename='tmt-reboot',
    destination_path=None,
    aliases=[
        'rstrnt-reboot',
        'rhts-reboot'],
    related_variables=[
        "TMT_REBOOT_COUNT",
        "REBOOTCOUNT",
        "RSTRNT_REBOOTCOUNT"],
    created_file="reboot-request",
    enabled=lambda _: True
    )

TMT_REBOOT_CORE_SCRIPT = Script(
    source_filename='tmt-reboot-core',
    destination_path=None,
    aliases=[],
    related_variables=[],
    enabled=lambda _: True
    )

# Script handling result reporting, in restraint compatible fashion
TMT_REPORT_RESULT_SCRIPT = ScriptCreatingFile(
    source_filename='tmt-report-result',
    destination_path=None,
    aliases=[
        'rstrnt-report-result',
        'rhts-report-result'],
    related_variables=[],
    created_file="tmt-report-results.yaml",
    enabled=lambda _: True
    )

# Script for archiving a file, usable for BEAKERLIB_COMMAND_SUBMIT_LOG
TMT_FILE_SUBMIT_SCRIPT = Script(
    source_filename='tmt-file-submit',
    destination_path=None,
    aliases=[
        'rstrnt-report-log',
        'rhts-submit-log',
        'rhts_submit_log'],
    related_variables=[],
    enabled=lambda _: True
    )

# Script handling text execution abortion, in restraint compatible fashion
TMT_ABORT_SCRIPT = ScriptCreatingFile(
    source_filename='tmt-abort',
    destination_path=None,
    aliases=[
        'rstrnt-abort',
        'rhts-abort'],
    related_variables=[],
    created_file="abort",
    enabled=lambda _: True
    )

# Profile script for adding SCRIPTS_DEST_DIR to executable paths system-wide.
# Used only for distributions using rpm-ostree.
TMT_ETC_PROFILE_D = ScriptTemplate(
    source_filename='tmt.sh',
    destination_path=Path("/etc/profile.d/tmt.sh"),
    aliases=[],
    related_variables=[],
    context={
        'SCRIPTS_DEST_DIR': str(
            effective_scripts_dest_dir(
                default=DEFAULT_SCRIPTS_DEST_DIR_OSTREE))},
    enabled=lambda guest: guest.facts.is_ostree is True)


# List of all available scripts
SCRIPTS = (
    TMT_ABORT_SCRIPT,
    TMT_ETC_PROFILE_D,
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

    logger: tmt.log.Logger

    phase: 'ExecutePlugin[Any]'
    test: 'tmt.base.Test'
    guest: Guest

    #: Process running the test. What binary it is depends on the guest
    #: implementation and the test, it may be, for example, a shell process,
    #: SSH process, or a ``podman`` process.
    process: Optional[subprocess.Popen[bytes]] = None
    process_lock: threading.Lock = field(default_factory=threading.Lock)

    results: list[Result] = dataclasses.field(default_factory=list)
    check_results: list[CheckResult] = dataclasses.field(default_factory=list)

    check_data: dict[str, Any] = field(default_factory=dict)

    return_code: Optional[int] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    real_duration: Optional[str] = None

    #: Number of times the test has been restarted.
    _restart_count: int = 0
    #: Number of times the guest has been rebooted.
    _reboot_count: int = 0

    @functools.cached_property
    def path(self) -> Path:
        """ Absolute path to invocation directory """

        assert self.phase.step.workdir is not None  # narrow type

        path = self.phase.step.workdir \
            / TEST_DATA \
            / 'guest' \
            / self.guest.safe_name \
            / f'{self.test.safe_name.lstrip("/") or "default"}-{self.test.serial_number}'

        path.mkdir(parents=True, exist_ok=True)

        # Pre-create also the test data and checks path - cannot use
        # `self.test_data_path`, that would be an endless recursion.
        (path / TEST_DATA).mkdir(parents=True, exist_ok=True)
        (path / CHECK_DATA).mkdir(parents=True, exist_ok=True)

        return path

    @functools.cached_property
    def relative_path(self) -> Path:
        """ Invocation directory path relative to step workdir """

        assert self.phase.step.workdir is not None  # narrow type

        return self.path.relative_to(self.phase.step.workdir)

    @functools.cached_property
    def test_data_path(self) -> Path:
        """ Absolute path to test data directory """

        return self.path / TEST_DATA

    @functools.cached_property
    def relative_test_data_path(self) -> Path:
        """ Test data path relative to step workdir """

        return self.relative_path / TEST_DATA

    @functools.cached_property
    def check_files_path(self) -> Path:
        """ Construct a directory path for check files needed by tmt """

        return self.path / CHECK_DATA

    @functools.cached_property
    def reboot_request_path(self) -> Path:
        """ A path to the reboot request file """
        return self.test_data_path / TMT_REBOOT_SCRIPT.created_file

    @functools.cached_property
    def abort_request_path(self) -> Path:
        """ A path to the abort request file """
        return self.test_data_path / TMT_ABORT_SCRIPT.created_file

    @property
    def soft_reboot_requested(self) -> bool:
        """ If set, test requested a reboot """
        return self.reboot_request_path.exists()

    #: If set, an asynchronous observer requested a reboot while the test was
    #: running.
    hard_reboot_requested: bool = False

    @property
    def reboot_requested(self) -> bool:
        """ Whether a guest reboot has been requested while the test was running """
        return self.soft_reboot_requested or self.hard_reboot_requested

    @property
    def restart_requested(self) -> bool:
        """ Whether a test restart has been requested """

        return self.return_code in self.test.restart_on_exit_code

    @property
    def abort_requested(self) -> bool:
        """ Whether a testing abort was requested """

        return self.abort_request_path.exists()

    @property
    def is_guest_healthy(self) -> bool:
        """
        Whether the guest is deemed to be healthy and responsive.

        .. note::

            The answer is deduced from various flags set by execute code
            while observing the test, no additional checks are
            performed.
        """

        if self.hard_reboot_requested:
            return False

        if self.restart_requested:
            return False

        return True

    def handle_restart(self) -> bool:
        """
        "Restart" the test if the test requested it.

        .. note::

            The test is not actually restarted, because running the test
            is managed by a plugin calling this method. Instead, the
            method performs all necessary steps before letting plugin
            know it should run the test once again.

        Check whether a test restart was needed and allowed, and update
        the accounting info before letting the plugin know it's time to
        run the test once again.

        If requested by the test, the guest might be rebooted as well.

        :return: ``True`` when the restart is to take place, ``False``
            otherwise.
        """

        if not self.restart_requested:
            return False

        if self._restart_count >= self.test.restart_max_count:
            self.logger.debug(
                f"Test restart denied during test '{self.test}'"
                f" with reboot count {self._reboot_count}"
                f" and test restart count {self._restart_count}.")

            return False

        if self.test.restart_with_reboot:
            self.hard_reboot_requested = True

            if not self.handle_reboot():
                return False

        else:
            self._restart_count += 1

            # Even though the reboot was not requested, it might have
            # still happened! Imagine a test configuring autoreboot on
            # kernel panic plus a test restart. The reboot would happen
            # beyond tmt's control, and tmt would try to restart the
            # test, but the guest may be still booting. Make sure it's
            # alive.
            if not self.guest.reconnect():
                return False

        self.logger.debug(
            f"Test restart during test '{self.test}'"
            f" with reboot count {self._reboot_count}"
            f" and test restart count {self._restart_count}.")

        self.guest.push()

        return True

    def handle_reboot(self) -> bool:
        """
        Reboot the guest if the test requested it.

        Check for presence of a file signalling reboot request and orchestrate
        the reboot if it was requested. Also increment the ``REBOOTCOUNT``
        variable, reset it to zero if no reboot was requested (going forward to
        the next test).

        :return: ``True`` when the reboot has taken place, ``False`` otherwise.
        """

        if not self.reboot_requested:
            return False

        self._reboot_count += 1
        self._restart_count += 1

        self.logger.debug(
            f"{'Hard' if self.hard_reboot_requested else 'Soft'} reboot during test '{self.test}'"
            f" with reboot count {self._reboot_count}"
            f" and test restart count {self._restart_count}.")

        reboot_command: Optional[ShellScript] = None
        timeout: Optional[int] = None

        if self.hard_reboot_requested:
            pass

        elif self.soft_reboot_requested:
            # Extract custom hints from the file, and reset it.
            reboot_data = json.loads(self.reboot_request_path.read_text())

            if reboot_data.get('command'):
                with suppress(TypeError):
                    reboot_command = ShellScript(reboot_data.get('command'))

            try:
                timeout = int(reboot_data.get('timeout'))
            except ValueError:
                timeout = None

            os.remove(self.reboot_request_path)
            self.guest.push(self.test_data_path)

        rebooted = False

        try:
            rebooted = self.guest.reboot(
                hard=self.hard_reboot_requested,
                command=reboot_command,
                timeout=timeout)

        except tmt.utils.RunError:
            self.logger.fail(
                f"Failed to reboot guest using the custom command '{reboot_command}'.")

            raise

        except tmt.utils.ProvisionError:
            self.logger.warning(
                "Guest does not support soft reboot, trying hard reboot.")

            rebooted = self.guest.reboot(hard=True, timeout=timeout)

        if not rebooted:
            raise tmt.utils.RebootTimeoutError("Reboot timed out.")

        self.hard_reboot_requested = False

        return True

    def terminate_process(
            self,
            signal: _signal.Signals = _signal.SIGTERM,
            logger: Optional[tmt.log.Logger] = None) -> None:
        """
        Terminate the invocation process.

        .. warning::

            This method should be used carefully. Process running the
            invocation's test has been started by some part of tmt code which
            is responsible for its well-being. Unless you have a really good
            reason to do so, doing things behind the tmt's back may lead to
            unexpected results.

        :param signal: signal to send to the invocation process.
        :param logger: logger to use for logging.
        """

        logger = logger or self.logger

        with self.process_lock:
            if self.process is None:
                logger.debug('Test invocation process cannot be terminated because it is unset.',
                             level=3)

                return

            logger.debug(f'Terminating process {self.process.pid} with {signal.name}.', level=3)

            self.process.send_signal(signal)

            if isinstance(self.guest, tmt.steps.provision.GuestSsh):
                self.guest._cleanup_ssh_master_process(signal, logger)


@dataclasses.dataclass
class ResultCollection:
    """ Collection of raw results loaded from a file """

    invocation: TestInvocation

    filepaths: list[Path]
    file_exists: bool = False
    results: list['tmt.result.RawResult'] = dataclasses.field(default_factory=list)

    def validate(self) -> None:
        """
        Validate raw collected results against the result JSON schema.

        Report found errors as warnings via :py:attr:`invocation` logger.
        """

        schema = tmt.utils.load_schema(Path('results.yaml'))
        schema_store = tmt.utils.load_schema_store()

        result = fmf.utils.validate_data(self.results, schema, schema_store=schema_store)

        if not result.errors:
            self.invocation.logger.debug('Results successfully validated.', level=4, shift=1)

            return

        for _, error in tmt.utils.preformat_jsonschema_validation_errors(result.errors):
            self.invocation.logger.warning(
                f'Result format violation: {error}', shift=1)


class ExecutePlugin(tmt.steps.Plugin[ExecuteStepDataT, None]):
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
            environment: Optional[tmt.utils.Environment] = None,
            logger: tmt.log.Logger) -> None:
        self.go_prolog(logger)
        logger.verbose('exit-first', self.data.exit_first, 'green', level=2)

    @property
    def discover(self) -> Discover:
        """ Return discover plugin instance """
        # This is necessary so that upgrade plugin can inject a fake discover

        return self.step.plan.discover

    @discover.setter
    def discover(self, plugin: Optional[DiscoverPlugin[DiscoverStepData]]) -> None:
        self._discover = plugin

    def prepare_tests(self, guest: Guest, logger: tmt.log.Logger) -> list[TestInvocation]:
        """
        Prepare discovered tests for testing

        Check which tests have been discovered, for each test prepare
        the aggregated metadata in a file under the test data directory
        and finally return a list of discovered tests.
        """
        invocations: list[TestInvocation] = []

        for test in self.discover.tests(phase_name=self.discover_phase, enabled=True):
            invocation = TestInvocation(phase=self, test=test, guest=guest, logger=logger)
            invocations.append(invocation)

            # Exported metadata is the test's metadata along with other variables like the context
            test_metadata = test._metadata.copy()
            test_metadata["context"] = self.step.plan._fmf_context.to_spec()
            self.write(
                invocation.path / TEST_METADATA_FILENAME,
                tmt.utils.dict_to_yaml(test_metadata))

            # When running again then we only keep results for tests that won't be executed again
            if self.should_run_again:
                assert self.parent is not None  # narrow type
                assert isinstance(self.parent, Execute)  # narrow type
                self.parent._results = [
                    result for result in self.parent._results
                    if not (
                        test.name == result.name and test.serial_number == result.serial_number)]

        # Keep old results in another variable to have numbers only for actually executed tests
        if self.should_run_again:
            assert self.parent is not None  # narrow type
            assert isinstance(self.parent, Execute)  # narrow type
            self.parent._old_results = self.parent._results[:]
            self.parent._results.clear()

        return invocations

    def prepare_scripts(self, guest: "tmt.steps.provision.Guest") -> None:
        """ Prepare additional scripts for testing """

        # Make sure scripts directory exists
        command = Command("mkdir", "-p", f"{guest.scripts_path}")

        if not guest.facts.is_superuser:
            command = Command("sudo") + command

        guest.execute(command)

        # Install all scripts on guest
        for script in self.scripts:
            with script as source:
                for filename in [script.source_filename, *script.aliases]:
                    if script.enabled(guest):
                        guest.push(
                            source=source,
                            destination=script.destination_path or guest.scripts_path / filename,
                            options=[
                                "-p",
                                "--chmod=755"],
                            superuser=guest.facts.is_superuser is not True)

    def _tmt_report_results_filepath(self, invocation: TestInvocation) -> Path:
        """ Create path to test's ``tmt-report-result`` file """

        return invocation.test_data_path / TMT_REPORT_RESULT_SCRIPT.created_file

    def _load_custom_results_file(self, invocation: TestInvocation) -> ResultCollection:
        """
        Load results created by the test itself.

        :param invocation: test invocation to which the results belong to.
        :returns: raw loaded results.
        """

        custom_results_path_yaml = invocation.test_data_path / 'results.yaml'
        custom_results_path_json = invocation.test_data_path / 'results.json'

        collection = ResultCollection(
            invocation=invocation,
            filepaths=[custom_results_path_yaml, custom_results_path_json])

        if custom_results_path_yaml.exists():
            collection.results = tmt.utils.yaml_to_list(custom_results_path_yaml.read_text())

        elif custom_results_path_json.exists():
            collection.results = tmt.utils.json_to_list(custom_results_path_json.read_text())

        else:
            return collection

        collection.file_exists = True

        return collection

    def _load_tmt_report_results_file(self, invocation: TestInvocation) -> ResultCollection:
        """
        Load results created by ``tmt-report-result`` script.

        :param invocation: test invocation to which the results belong to.
        :returns: raw loaded results.
        """

        results_path = self._tmt_report_results_filepath(invocation)
        collection = ResultCollection(invocation=invocation, filepaths=[results_path])

        # Nothing to do if there's no result file
        if not results_path.exists():
            return collection

        # Check the test result
        collection.file_exists = True
        collection.results = tmt.utils.yaml_to_list(results_path.read_text())

        return collection

    def _process_results_partials(
            self,
            invocation: TestInvocation,
            results: list['tmt.result.RawResult'],
            default_log: Optional[Path] = None) -> list['tmt.result.Result']:
        """
        Treat results as partial results belonging to a test.

        This is the default behavior for custom results, all results
        would be prefixed with test name, plus various their attributes
        would be updated.

        :param invocation: test invocation to which the results belong to.
        :param results: results to process.
        :param default_log: attach this log file to results which do not
            have any log provided.
        :returns: list of results.
        """

        test = invocation.test

        custom_results = []
        for partial_result_data in results:
            partial_result = tmt.Result.from_serialized(partial_result_data)

            # Name '/' means the test itself
            if partial_result.name == '/':
                partial_result.name = test.name

            else:
                if not partial_result.name.startswith('/'):
                    partial_result.note.append("custom test result name should start with '/'")
                    partial_result.name = '/' + partial_result.name
                partial_result.name = test.name + partial_result.name

            # Fix log paths as user provides relative path to `TMT_TEST_DATA`, but Result has to
            # point relative to the execute workdir
            partial_result.log = [
                invocation.relative_test_data_path / log for log in partial_result.log]

            # Include the default output log if no log provided
            if not partial_result.log and default_log is not None:
                partial_result.log.append(default_log)

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
            partial_result.guest = ResultGuestData.from_test_invocation(invocation=invocation)

            # For the result representing the test itself, set the important
            # attributes to reflect the reality.
            if partial_result.name == test.name:
                partial_result.start_time = invocation.start_time
                partial_result.end_time = invocation.end_time
                partial_result.duration = invocation.real_duration
                partial_result.context = self.step.plan._fmf_context

            custom_results.append(partial_result)

        return custom_results

    def extract_custom_results(self, invocation: TestInvocation) -> list["tmt.Result"]:
        """ Extract results from the file generated by the test itself """

        collection = self._load_custom_results_file(invocation)

        if not collection.file_exists:
            return [tmt.Result.from_test_invocation(
                invocation=invocation,
                note=[f"custom results file not found in '{invocation.test_data_path}'"],
                result=ResultOutcome.ERROR)]

        if not collection.results:
            return [tmt.Result.from_test_invocation(
                invocation=invocation,
                note=["no custom results were provided"],
                result=ResultOutcome.ERROR)]

        collection.validate()

        return self._process_results_partials(invocation, collection.results)

    def extract_tmt_report_results(self, invocation: TestInvocation) -> list["tmt.Result"]:
        """ Extract results from a file generated by ``tmt-report-result`` script """

        collection = self._load_tmt_report_results_file(invocation)

        results_path = collection.filepaths[0]

        if not collection.file_exists:
            self.debug(f"tmt-report-results file '{results_path}' does not exist.")

            return []

        self.debug(f"tmt-report-results file '{results_path}' detected.")

        if not collection.results:
            raise tmt.utils.ExecuteError(
                f"Test results not found in result file '{results_path}'.")

        collection.validate()

        # Fix log paths created by `tmt-report-result` on the guest, which are by default relative
        # to the `TMT_TEST_DATA`, to be relative to the `execute` directory.
        for result in collection.results:
            result["log"] = [
                str(invocation.relative_test_data_path / log) for log in result.get("log", [])]

        return [tmt.Result.from_serialized(result) for result in collection.results]

    def extract_tmt_report_results_restraint(
            self,
            invocation: TestInvocation,
            default_log: Path) -> list["tmt.Result"]:
        """
        Extract results from the file generated by ``tmt-report-result`` script.

        Special, restraint-like handling is used to convert each
        recorded result into a standalone result.
        """

        collection = self._load_tmt_report_results_file(invocation)

        results_path = collection.filepaths[0]

        if not collection.file_exists:
            self.debug(f"tmt-report-results file '{results_path}' does not exist.")

            return []

        self.debug(f"tmt-report-results file '{results_path}' detected.")

        if not collection.results:
            raise tmt.utils.ExecuteError(
                f"Test results not found in result file '{results_path}'.")

        collection.validate()

        return self._process_results_partials(
            invocation, collection.results, default_log=default_log)

    def extract_results(
            self,
            invocation: TestInvocation,
            logger: tmt.log.Logger) -> list[Result]:
        """ Check the test result """

        self.debug(f"Extract results of '{invocation.test.name}'.")

        if invocation.test.result == ResultInterpret.CUSTOM:
            return self.extract_custom_results(invocation)

        # Handle the 'tmt-report-result' command results as separate tests
        if invocation.test.result == ResultInterpret.RESTRAINT:
            return self.extract_tmt_report_results_restraint(
                invocation=invocation,
                default_log=invocation.relative_path / TEST_OUTPUT_FILENAME)

        # Load the results from the `tmt-report-results.yaml` if a file was generated.
        results = []
        if self._tmt_report_results_filepath(invocation).exists():
            results = self.extract_tmt_report_results(invocation)

        # Propagate loaded `results` to test framework, which will handle these results accordingly
        # (e.g. saves them as a tmt subresults).
        return invocation.test.test_framework.extract_results(invocation, results, logger)

    def check_abort_file(self, invocation: TestInvocation) -> bool:
        """
        Check for an abort file created by tmt-abort

        Returns whether an abort file is present (i.e. abort occurred).
        """
        return (invocation.test_data_path / TMT_ABORT_SCRIPT.created_file).exists()

    def timeout_hint(self, invocation: TestInvocation) -> None:
        """ Append a duration increase hint to the test output """
        output = invocation.path / TEST_OUTPUT_FILENAME
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
            environment: Optional[tmt.utils.Environment] = None,
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

                result.start_time = format_timestamp(timer.start_time)
                result.end_time = format_timestamp(timer.end_time)
                result.duration = format_duration(timer.duration)

            results += check_results

        return results

    def run_checks_before_test(
            self,
            *,
            invocation: TestInvocation,
            environment: Optional[tmt.utils.Environment] = None,
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
            environment: Optional[tmt.utils.Environment] = None,
            logger: tmt.log.Logger) -> list[CheckResult]:
        return self._run_checks_for_test(
            event=CheckEvent.AFTER_TEST,
            invocation=invocation,
            environment=environment,
            logger=logger
            )


class Execute(tmt.steps.Step):
    """ Run tests using the specified executor """

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
        self._old_results: list[tmt.Result] = []

    def load(self) -> None:
        """ Load test results """
        super().load()

        self._results = self._load_results(Result, allow_missing=True)

    def save(self) -> None:
        """ Save test results to the workdir """
        super().save()

        self._save_results(self.results())

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

        # Nothing more to do if already done and not asked to run again
        if self.status() == 'done' and not self.should_run_again:
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

    def go(self, force: bool = False) -> None:
        """ Execute tests """
        super().go(force=force)

        # Clean up possible old results
        if force:
            self._results.clear()

        if self.should_run_again:
            self.status('todo')

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
        queue: PhaseQueue[ExecuteStepData, None] = PhaseQueue(
            'execute',
            self._logger.descend(logger_name=f'{self}.queue'))

        execute_phases = self.phases(classes=(ExecutePlugin,))
        assert len(execute_phases) == 1

        # Clean up possible old results
        execute_phases[0]._results.clear()

        for phase in self.phases(classes=(Action, ExecutePlugin)):
            if isinstance(phase, Action):
                queue.enqueue_action(phase=phase)

            else:
                # A single execute plugin is expected to process (potentially)
                # multiple discover phases. There must be a way to tell the execute
                # plugin which discover phase to focus on. Unfortunately, the
                # current way is the execute plugin checking its `discover`
                # attribute. For each discover phase, we need a copy of the execute
                # plugin, so we could point it to that discover phase rather than
                # let is "see" all tests, or test in different discover phase.
                for discover in self.plan.discover.phases(classes=(DiscoverPlugin,)):
                    if not discover.enabled_by_when:
                        continue

                    phase_copy = cast(ExecutePlugin[ExecuteStepData], copy.copy(phase))
                    phase_copy.discover_phase = discover.name

                    queue.enqueue_plugin(
                        phase=phase_copy,
                        guests=[
                            guest
                            for guest in self.plan.provision.guests()
                            if discover.enabled_on_guest(guest)
                            ])

        failed_tasks: list[Union[ActionTask, PluginTask[ExecuteStepData, None]]] = []

        for outcome in queue.run():
            if outcome.exc:
                outcome.logger.fail(str(outcome.exc))

                failed_tasks.append(outcome)
                continue

        # Execute plugins do not return results. Instead, plugin collects results
        # in its internal `_results` list. To accommodate for different discover
        # phases, we create a copy of the execute phase for each discover phase
        # we have. All these copies share the `_results` list, and append to it.
        #
        # Therefore, avoid collecting results from phases when iterating the
        # outcomes - such a process would encounter the list multiple times,
        # which would make results appear several times. Instead, we can reach
        # into the original plugin, and use it as a singleton "entry point" to
        # access all collected `_results`.
        self._results += execute_phases[0].results()

        # To separate "execute" from the follow-up logging visually
        self.info('')

        # Give a summary, update status and save
        self.summary()
        if not failed_tasks:
            self.status('done')

        # Merge old results back to get all results in report step
        if self.should_run_again:
            self._results += self._old_results

        self.save()

        if failed_tasks:
            # TODO: needs a better message...
            raise tmt.utils.GeneralError(
                'execute step failed',
                causes=[outcome.exc for outcome in failed_tasks if outcome.exc is not None]
                )

    def results(self) -> list["tmt.result.Result"]:
        """
        Results from executed tests

        Return a list with test results according to the spec:
        https://tmt.readthedocs.io/en/latest/spec/plans.html#execute
        """
        return self._results

    def results_for_tests(
            self,
            tests: list['tmt.base.Test']
            ) -> list[tuple[Optional[Result], Optional['tmt.base.Test']]]:
        """
        Collect results and corresponding tests.

        :returns: a list of result and test pairs.
            * if there is not test found for the result, e.g. when
            results were loaded from storage but tests were not,
            ``None`` represents the missing test: ``(result, None)``.
            * if there is no result for a test, e.g. when the test was
            not executed, ``None`` represents the missing result:
            ``(None, test)``.
        """

        known_serial_numbers = {test.serial_number: test for test in tests}
        referenced_serial_numbers = {result.serial_number for result in self._results}

        return [
            (result, known_serial_numbers.get(result.serial_number))
            for result in self._results
            ] + [
            (None, test)
            for test in tests
            if test.serial_number not in referenced_serial_numbers
            ]
