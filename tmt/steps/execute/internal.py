import dataclasses
import json
import os
import textwrap
from contextlib import suppress
from typing import Any, Optional, cast

import click
import jinja2

import tmt
import tmt.base
import tmt.log
import tmt.options
import tmt.steps
import tmt.steps.execute
import tmt.utils
from tmt.result import BaseResult, CheckResult, Result, ResultOutcome
from tmt.steps import safe_filename
from tmt.steps.execute import SCRIPTS, TEST_OUTPUT_FILENAME, TMT_REBOOT_SCRIPT, TestInvocation
from tmt.steps.provision import Guest
from tmt.utils import EnvironmentType, Path, ShellScript, Stopwatch, field

TEST_PIDFILE_FILENAME = 'tmt-test.pid'
TEST_PIDFILE_LOCK_FILENAME = f'{TEST_PIDFILE_FILENAME}.lock'

#: The default directory for storing test pid file.
TEST_PIDFILE_ROOT = Path('/var/tmp')


def effective_pidfile_root() -> Path:
    """
    Find out what the actual pidfile directory is.

    If ``TMT_TEST_PIDFILE_ROOT`` variable is set, it is used. Otherwise,
    :py:const:`TEST_PIDFILE_ROOT` is picked.
    """

    if 'TMT_TEST_PIDFILE_ROOT' in os.environ:
        return Path(os.environ['TMT_TEST_PIDFILE_ROOT'])

    return TEST_PIDFILE_ROOT


TEST_WRAPPER_FILENAME = 'tmt-test-wrapper.sh'

# tmt test wrapper is getting complex. Besides honoring the timeout
# and interactivity request, it also must play nicely with reboots
# and `tmt-reboot`. The wrapper must present consistent info on what
# is the PID to kill from `tmt-reboot`, and where to save additional
# reboot info.
#
# For the duration of the test, the wrapper creates so-called "test
# pidfile". The pidfile contains test wrapper PID and path to the
# reboot-request file corresponding to the test being run. All actions
# against the pidfile must be taken while holding the pidfile lock,
# to serialize access between the wrapper and `tmt-reboot`. The file
# might be missing, that's allowed, but if it exists, it must contain
# correct info.
#
# Before quitting the wrapper, the pidfile is removed. There seems
# to be an apparent race condition: test quits -> `tmt-reboot` is
# called from a parallel session, grabs a pidfile lock, inspects
# pidfile, updates reboot-request, and sends signal to designed PID
# -> wrapper grabs the lock & removes the pidfile. This leaves us
# with `tmt-reboot` sending signal to non-existent PID - which is
# reported by `tmt-reboot`, "try again later" - and reboot-request
# file signaling reboot is needed *after the test is done*.
#
# This cannot be solved without the test being involved in the reboot,
# which does not seem like a viable option. The test must be restartable
# though, it may get restarted in this "weird" way. On the other hand,
# this is probably not a problem in real-life scenarios: tests that
# are to be interrupted by out-of-session reboot are expecting this
# action, and they do not finish on their own.
TEST_WRAPPER_TEMPLATE = jinja2.Template(textwrap.dedent("""
{% macro enter() %}
flock "$TMT_TEST_PIDFILE_LOCK" -c "echo '${test_pid} ${TMT_REBOOT_REQUEST}' > ${TMT_TEST_PIDFILE}" || exit 122
{%- endmacro %}

{% macro exit() %}
flock "$TMT_TEST_PIDFILE_LOCK" -c "rm -f ${TMT_TEST_PIDFILE}" || exit 123
{%- endmacro %}

[ ! -z "$TMT_DEBUG" ] && set -x

test_pid="$$";

mkdir -p "$(dirname $TMT_TEST_PIDFILE_LOCK)"

{% if INTERACTIVE %}
    {{ enter() }};
    {{ REMOTE_COMMAND }};
    _exit_code="$!";
    {{ exit() }};
{% else %}
    set -o pipefail;
    {{ enter() }};
    {{ REMOTE_COMMAND }} </dev/null |& cat;
    _exit_code="$?";
    {{ exit () }};
{% endif %}
exit $_exit_code;
"""  # noqa: E501
))


class UpdatableMessage(tmt.utils.UpdatableMessage):
    """
    Updatable message suitable for plan progress reporting.

    Based on :py:class:`tmt.utils.UpdatableMessage`, simplifies
    reporting of plan progress, namely by extracting necessary setup
    parameters from the plugin.
    """

    def __init__(self, plugin: 'ExecuteInternal') -> None:
        super().__init__(
            key='progress',
            enabled=not plugin.verbosity_level and not plugin.data.no_progress_bar,
            indent_level=plugin._level(),
            key_color='cyan',
            clear_on_exit=True)

        self.plugin = plugin
        self.debug_level = plugin.debug_level

    # ignore[override]: the signature differs on purpose, we wish to input raw
    # values and let our `update()` construct the message.
    def update(self, progress: str, test_name: str) -> None:  # type: ignore[override]
        message = f'{test_name} [{progress}]'

        # With debug mode enabled, we do not really update a single line. Instead,
        # we shall emit each update as a distinct logging message, which would be
        # mixed into the debugging output.
        if self.debug_level:
            self.plugin.info(message)

        else:
            self._update_message_area(message)


@dataclasses.dataclass
class ExecuteInternalData(tmt.steps.execute.ExecuteStepData):
    script: list[ShellScript] = field(
        default_factory=list,
        option=('-s', '--script'),
        metavar='SCRIPT',
        multiple=True,
        help='Shell script to be executed as a test.',
        normalize=tmt.utils.normalize_shell_script_list,
        serialize=lambda scripts: [str(script) for script in scripts],
        unserialize=lambda serialized: [ShellScript(script) for script in serialized])
    interactive: bool = field(
        default=False,
        option=('-i', '--interactive'),
        is_flag=True,
        help='Run in interactive mode, do not capture output.')
    no_progress_bar: bool = field(
        default=False,
        option='--no-progress-bar',
        is_flag=True,
        help='Disable interactive progress bar showing the current test.')

    # ignore[override] & cast: two base classes define to_spec(), with conflicting
    # formal types.
    def to_spec(self) -> dict[str, Any]:  # type: ignore[override]
        data = cast(dict[str, Any], super().to_spec())
        data['script'] = [str(script) for script in self.script]

        return data


@tmt.steps.provides_method('tmt')
class ExecuteInternal(tmt.steps.execute.ExecutePlugin[ExecuteInternalData]):
    """
    Use the internal tmt executor to execute tests

    The internal tmt executor runs tests on the guest one by one, shows
    testing progress and supports interactive debugging as well. Test
    result is based on the script exit code (for shell tests) or the
    results file (for beakerlib tests).
    """

    _data_class = ExecuteInternalData
    data: ExecuteInternalData

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        self._previous_progress_message = ""
        self.scripts = SCRIPTS

    def _test_environment(
            self,
            *,
            invocation: TestInvocation,
            extra_environment: Optional[EnvironmentType] = None,
            logger: tmt.log.Logger) -> EnvironmentType:
        """ Return test environment """

        extra_environment = extra_environment or {}

        data_directory = invocation.data_path(full=True, create=True)

        environment = extra_environment.copy()
        environment.update(invocation.test.environment)
        assert self.parent is not None
        assert isinstance(self.parent, tmt.steps.execute.Execute)

        environment['TMT_TEST_PIDFILE'] = str(
            effective_pidfile_root() / TEST_PIDFILE_FILENAME)
        environment['TMT_TEST_PIDFILE_LOCK'] = str(
            effective_pidfile_root() / TEST_PIDFILE_LOCK_FILENAME)
        environment["TMT_TEST_NAME"] = invocation.test.name
        environment["TMT_TEST_DATA"] = str(data_directory / tmt.steps.execute.TEST_DATA)
        environment['TMT_TEST_SERIAL_NUMBER'] = str(invocation.test.serial_number)
        environment["TMT_TEST_METADATA"] = str(
            data_directory / tmt.steps.execute.TEST_METADATA_FILENAME)
        environment["TMT_REBOOT_REQUEST"] = str(
            data_directory / tmt.steps.execute.TEST_DATA / TMT_REBOOT_SCRIPT.created_file)
        # Set all supported reboot variables
        for reboot_variable in TMT_REBOOT_SCRIPT.related_variables:
            environment[reboot_variable] = str(invocation.test._reboot_count)

        # Add variables the framework wants to expose
        environment.update(
            invocation.test.test_framework.get_environment_variables(
                invocation, logger))

        return environment

    def _test_output_logger(
            self,
            key: str,
            value: Optional[str] = None,
            color: Optional[str] = None,
            shift: int = 2,
            level: int = 3,
            topic: Optional[tmt.log.Topic] = None) -> None:
        """ Custom logger for test output with shift 2 and level 3 defaults """
        self.verbose(key=key, value=value, color=color, shift=shift, level=level)

    def execute(
            self,
            *,
            invocation: TestInvocation,
            extra_environment: Optional[EnvironmentType] = None,
            logger: tmt.log.Logger) -> list[CheckResult]:
        """ Run test on the guest """

        test, guest = invocation.test, invocation.guest

        logger.debug(f"Execute '{test.name}' as a '{test.framework}' test.")

        test_check_results: list[CheckResult] = []

        # Test will be executed in it's own directory, relative to the workdir
        assert self.discover.workdir is not None  # narrow type
        assert test.path is not None  # narrow type
        workdir = self.discover.workdir / test.path.unrooted()
        logger.debug(f"Use workdir '{workdir}'.", level=3)

        # Create data directory, prepare test environment
        environment = self._test_environment(
            invocation=invocation,
            extra_environment=extra_environment,
            logger=logger)

        # tmt wrapper filename *must* be "unique" - the plugin might be handling
        # the same `discover` phase for different guests at the same time, and
        # must keep them isolated. The wrapper script, while being prepared, is
        # a shared global state, and we must prevent race conditions.
        test_wrapper_filename = safe_filename(TEST_WRAPPER_FILENAME, self, guest)
        test_wrapper_filepath = workdir / test_wrapper_filename

        logger.debug('test wrapper', test_wrapper_filepath)

        # Prepare the test command
        test_command = test.test_framework.get_test_command(invocation, logger)
        self.debug('Test script', test_command, level=3)

        # Prepare the wrapper, push to guest
        self.write(test_wrapper_filepath, str(test_command), 'w')
        test_wrapper_filepath.chmod(0o755)
        guest.push(
            source=test_wrapper_filepath,
            destination=test_wrapper_filepath,
            options=["-s", "-p", "--chmod=755"])

        # Create topology files
        topology = tmt.steps.Topology(self.step.plan.provision.guests())
        topology.guest = tmt.steps.GuestTopology(guest)

        environment.update(topology.push(
            dirpath=invocation.data_path(full=True),
            guest=guest,
            logger=logger))

        command: str
        if guest.become and not guest.facts.is_superuser:
            command = f'sudo -E ./{test_wrapper_filename}'
        else:
            command = f'./{test_wrapper_filename}'
        # Prepare the actual remote command
        remote_command = ShellScript(TEST_WRAPPER_TEMPLATE.render(
            INTERACTIVE=self.get('interactive'),
            REMOTE_COMMAND=ShellScript(command)
            ).strip())

        def _test_output_logger(
                key: str,
                value: Optional[str] = None,
                color: Optional[str] = None,
                shift: int = 2,
                level: int = 3,
                topic: Optional[tmt.log.Topic] = None) -> None:
            logger.verbose(
                key=key,
                value=value,
                color=color,
                shift=shift,
                level=level,
                topic=topic)

        # TODO: do we want timestamps? Yes, we do, leaving that for refactoring later,
        # to use some reusable decorator.
        test_check_results += self.run_checks_before_test(
            invocation=invocation,
            environment=environment,
            logger=logger
            )

        # Execute the test, save the output and return code
        with Stopwatch() as timer:
            test.start_time = self.format_timestamp(timer.start_time)

            try:
                output = guest.execute(
                    remote_command,
                    cwd=workdir,
                    env=environment,
                    join=True,
                    interactive=self.get('interactive'),
                    log=_test_output_logger,
                    timeout=tmt.utils.duration_to_seconds(test.duration),
                    test_session=True,
                    friendly_command=str(test.test))
                test.return_code = 0
                stdout = output.stdout
            except tmt.utils.RunError as error:
                stdout = error.stdout

                test.return_code = error.returncode
                if test.return_code == tmt.utils.ProcessExitCodes.TIMEOUT:
                    logger.debug(f"Test duration '{test.duration}' exceeded.")

                elif tmt.utils.ProcessExitCodes.is_pidfile(test.return_code):
                    logger.warn('Test failed to manage its pidfile.')

        test.end_time = self.format_timestamp(timer.end_time)
        test.real_duration = self.format_duration(timer.duration)

        test.data_path = invocation.data_path("data")

        self.write(
            invocation.data_path(TEST_OUTPUT_FILENAME, full=True),
            stdout or '', mode='a', level=3)

        # TODO: do we want timestamps? Yes, we do, leaving that for refactoring later,
        # to use some reusable decorator.
        test_check_results += self.run_checks_after_test(
            invocation=invocation,
            environment=environment,
            logger=logger
            )

        return test_check_results

    def _will_reboot(self, invocation: 'TestInvocation') -> bool:
        """ True if reboot is requested """
        return self._reboot_request_path(invocation).exists()

    def _reboot_request_path(self, invocation: 'TestInvocation') -> Path:
        """ Return reboot_request """
        return invocation.data_path(full=True) \
            / tmt.steps.execute.TEST_DATA \
            / TMT_REBOOT_SCRIPT.created_file

    def _handle_reboot(self, invocation: 'TestInvocation') -> bool:
        """
        Reboot the guest if the test requested it.

        Check for presence of a file signalling reboot request
        and orchestrate the reboot if it was requested. Also increment
        REBOOTCOUNT variable, reset it to 0 if no reboot was requested
        (going forward to the next test). Return whether reboot was done.
        """
        if self._will_reboot(invocation):
            invocation.test._reboot_count += 1
            self.debug(f"Reboot during test '{invocation.test}' "
                       f"with reboot count {invocation.test._reboot_count}.")
            reboot_request_path = self._reboot_request_path(invocation)
            test_data = invocation.data_path(full=True) / tmt.steps.execute.TEST_DATA
            with open(reboot_request_path) as reboot_file:
                reboot_data = json.loads(reboot_file.read())
            reboot_command = None
            if reboot_data.get('command'):
                with suppress(TypeError):
                    reboot_command = ShellScript(reboot_data.get('command'))

            try:
                timeout = int(reboot_data.get('timeout'))
            except ValueError:
                timeout = None
            # Reset the file
            os.remove(reboot_request_path)
            invocation.guest.push(test_data)
            rebooted = False
            try:
                rebooted = invocation.guest.reboot(command=reboot_command, timeout=timeout)
            except tmt.utils.RunError:
                self.fail(
                    f"Failed to reboot guest using the "
                    f"custom command '{reboot_command}'.")
                raise
            except tmt.utils.ProvisionError:
                self.warn(
                    "Guest does not support soft reboot, "
                    "trying hard reboot.")
                rebooted = invocation.guest.reboot(hard=True, timeout=timeout)
            if not rebooted:
                raise tmt.utils.RebootTimeoutError("Reboot timed out.")
            return True
        return False

    def go(
            self,
            *,
            guest: 'Guest',
            environment: Optional[tmt.utils.EnvironmentType] = None,
            logger: tmt.log.Logger) -> None:
        """ Execute available tests """
        super().go(guest=guest, environment=environment, logger=logger)

        # Nothing to do in dry mode
        if self.is_dry_run:
            self._results = []
            return

        self._run_tests(guest=guest, extra_environment=environment, logger=logger)

    def _run_tests(
            self,
            *,
            guest: Guest,
            extra_environment: Optional[EnvironmentType] = None,
            logger: tmt.log.Logger) -> None:
        """ Execute tests on provided guest """

        # Prepare tests and helper scripts, check options
        test_invocations = self.prepare_tests(guest)

        # Prepare scripts, except localhost guest
        if not guest.localhost:
            self.prepare_scripts(guest)

        # Push workdir to guest and execute tests
        guest.push()
        # We cannot use enumerate here due to continue in the code
        index = 0

        with UpdatableMessage(self) as progress_bar:
            while index < len(test_invocations):
                invocation = test_invocations[index]

                test = invocation.test

                progress = f"{index + 1}/{len(test_invocations)}"
                progress_bar.update(progress, test.name)
                logger.verbose(
                    'test', test.summary or test.name, color='cyan', shift=1, level=2)

                test_check_results: list[CheckResult] = self.execute(
                    invocation=invocation,
                    extra_environment=extra_environment,
                    logger=logger)

                guest.pull(
                    source=invocation.data_path(full=True),
                    extend_options=test.test_framework.get_pull_options(invocation, logger))

                results = self.extract_results(invocation, logger)  # Produce list of results

                for result in results:
                    result.check = test_check_results

                assert test.real_duration is not None  # narrow type
                duration = click.style(test.real_duration, fg='cyan')
                shift = 1 if self.verbosity_level < 2 else 2

                # Handle reboot, abort, exit-first
                if self._will_reboot(invocation):
                    # Output before the reboot
                    logger.verbose(
                        f"{duration} {test.name} [{progress}]", shift=shift)
                    try:
                        if self._handle_reboot(invocation):
                            continue
                    except tmt.utils.RebootTimeoutError:
                        for result in results:
                            result.result = ResultOutcome.ERROR
                            result.note = 'reboot timeout'
                abort = self.check_abort_file(invocation)
                if abort:
                    for result in results:
                        # In case of aborted all results in list will be aborted
                        result.note = 'aborted'
                self._results.extend(results)

                # If test duration information is missing, print 8 spaces to keep indention
                def _format_duration(result: BaseResult) -> str:
                    return click.style(result.duration, fg='cyan') if result.duration else 8 * ' '

                for result in results:
                    logger.verbose(
                        f"{_format_duration(result)} {result.show()} [{progress}]",
                        shift=shift)

                    for check_result in result.check:
                        # Indent the check one extra level, to make it clear it belongs to
                        # a parent test.
                        logger.verbose(
                            f'{_format_duration(check_result)} '
                            f'{" " * tmt.utils.INDENT}'
                            f'{check_result.show()} '
                            f'({check_result.event.value} check)',
                            shift=shift)

                if (abort or self.data.exit_first and
                        result.result not in (ResultOutcome.PASS, ResultOutcome.INFO)):
                    # Clear the progress bar before outputting
                    progress_bar.clear()
                    what_happened = "aborted" if abort else "failed"
                    self.warn(
                        f'Test {test.name} {what_happened}, stopping execution.')
                    break
                index += 1

                # Log into the guest after each executed test if "login
                # --test" option is provided
                if self._login_after_test:
                    assert test.path is not None  # narrow type

                    if self.discover.workdir is None:
                        cwd = test.path.unrooted()
                    else:
                        cwd = self.discover.workdir / test.path.unrooted()
                    self._login_after_test.after_test(
                        result,
                        cwd=cwd,
                        env=self._test_environment(
                            invocation=invocation,
                            extra_environment=extra_environment,
                            logger=logger),
                        )

        # Pull artifacts created in the plan data directory
        self.debug("Pull the plan data directory.", level=2)
        guest.pull(source=self.step.plan.data_directory)

    def results(self) -> list[Result]:
        """ Return test results """
        return self._results

    def requires(self) -> list[tmt.base.Dependency]:
        """ All requirements of the plugin on the guest """
        return []
