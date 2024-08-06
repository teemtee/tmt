import dataclasses
import os
import subprocess
import textwrap
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
from tmt.result import BaseResult, Result, ResultOutcome
from tmt.steps import safe_filename
from tmt.steps.execute import SCRIPTS, TEST_OUTPUT_FILENAME, TMT_REBOOT_SCRIPT, TestInvocation
from tmt.steps.provision import Guest
from tmt.utils import (
    Command,
    Environment,
    EnvVarValue,
    Path,
    ShellScript,
    Stopwatch,
    field,
    format_duration,
    format_timestamp,
    )

TEST_PIDFILE_FILENAME = 'tmt-test.pid'
TEST_PIDFILE_LOCK_FILENAME = f'{TEST_PIDFILE_FILENAME}.lock'

#: The default directory for storing test pid file.
TEST_PIDFILE_ROOT = Path('/var/tmp')  # noqa: S108 insecure usage of temporary dir


def effective_pidfile_root() -> Path:
    """
    Find out what the actual pidfile directory is.

    If ``TMT_TEST_PIDFILE_ROOT`` variable is set, it is used. Otherwise,
    :py:const:`TEST_PIDFILE_ROOT` is picked.
    """

    if 'TMT_TEST_PIDFILE_ROOT' in os.environ:
        return Path(os.environ['TMT_TEST_PIDFILE_ROOT'])

    return TEST_PIDFILE_ROOT


#: A template for the shell wrapper in which the test script is
#: saved.
#:
#: It is passed to :py:func:`tmt.utils.safe_filename`, but
#: includes also test name and serial number to make it unique
#: even among all test wrappers. See https://github.com/teemtee/tmt/issues/2997
#: for issue motivating the inclusion, it seems to be a good idea
#: to prevent accidental reuse in general.
TEST_WRAPPER_FILENAME_TEMPLATE = \
    'tmt-test-wrapper.sh-{{ INVOCATION.test.pathless_safe_name }}-{{ INVOCATION.test.serial_number }}'  # noqa: E501

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
#
# The ssh client always allocates a tty, so test timeout handling
# works (#1387). Because the allocated tty is generally not suitable
# for test execution, the wrapper uses `|& cat` to emulate execution
# without a tty. In certain cases, where test execution with available
# tty is required (#2381), the tty can be kept on request with
# the `tty: true` test attribute.
#
# The wrapper script handles 3 execution modes for REMOTE_COMMAND:
#
# * In `tmt` interactive mode, stdin and stdout are unhandled, it is expected
#   user interacts with the executed command.
#
# * In non-interactive mode without a tty, stdin is fed with /dev/null (EOF)
#   and `|& cat` is used to simulate no tty available for script output.
#
# * In non-interactive mode with a tty, stdin is available to the tests
#   and simulation of tty not available for output is not run.
#
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
    _exit_code="$?";
    {{ exit() }};
{% elif TTY %}
    set -o pipefail;
    {{ enter() }};
    {{ REMOTE_COMMAND }} 2>&1;
    _exit_code="$?";
    {{ exit () }};
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
        help="""
             Run tests in interactive mode, i.e. with input and output streams
             shared with tmt itself. This allows input to be passed to tests
             via stdin, e.g. responding to password prompts. Test output in this
             mode is not captured, and ``duration`` has no effect.
             """)
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
            extra_environment: Optional[Environment] = None,
            logger: tmt.log.Logger) -> Environment:
        """ Return test environment """

        extra_environment = extra_environment or Environment()

        environment = extra_environment.copy()
        environment.update(invocation.test.environment)
        assert self.parent is not None
        assert isinstance(self.parent, tmt.steps.execute.Execute)
        assert self.parent.plan.my_run is not None

        environment['TMT_TEST_PIDFILE'] = EnvVarValue(
            effective_pidfile_root() / TEST_PIDFILE_FILENAME)
        environment['TMT_TEST_PIDFILE_LOCK'] = EnvVarValue(
            effective_pidfile_root() / TEST_PIDFILE_LOCK_FILENAME)
        environment["TMT_TEST_NAME"] = EnvVarValue(invocation.test.name)
        environment["TMT_TEST_DATA"] = EnvVarValue(invocation.test_data_path)
        environment['TMT_TEST_SERIAL_NUMBER'] = EnvVarValue(str(invocation.test.serial_number))
        environment['TMT_TEST_ITERATION_ID'] = EnvVarValue(
            f"{self.parent.plan.my_run.unique_id}-{invocation.test.serial_number}")
        environment["TMT_TEST_METADATA"] = EnvVarValue(
            invocation.path / tmt.steps.execute.TEST_METADATA_FILENAME)
        environment["TMT_REBOOT_REQUEST"] = EnvVarValue(
            invocation.test_data_path / TMT_REBOOT_SCRIPT.created_file)
        # Set all supported reboot variables
        for reboot_variable in TMT_REBOOT_SCRIPT.related_variables:
            environment[reboot_variable] = EnvVarValue(str(invocation._reboot_count))
        environment['TMT_TEST_RESTART_COUNT'] = EnvVarValue(str(invocation._restart_count))

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
            extra_environment: Optional[Environment] = None,
            logger: tmt.log.Logger) -> list[Result]:
        """ Run test on the guest """

        test, guest = invocation.test, invocation.guest

        logger.debug(f"Execute '{test.name}' as a '{test.framework}' test.")

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
        test_wrapper_filename = safe_filename(
            TEST_WRAPPER_FILENAME_TEMPLATE, self, guest, INVOCATION=invocation)
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
            dirpath=invocation.path,
            guest=guest,
            logger=logger))

        command: str
        if guest.become and not guest.facts.is_superuser:
            command = f'sudo -E ./{test_wrapper_filename}'
        else:
            command = f'./{test_wrapper_filename}'
        # Prepare the actual remote command
        remote_command = ShellScript(TEST_WRAPPER_TEMPLATE.render(
            INTERACTIVE=self.data.interactive,
            TTY=test.tty,
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

        def _save_process(
                command: Command,
                process: subprocess.Popen[bytes],
                logger: tmt.log.Logger) -> None:
            with invocation.process_lock:
                invocation.process = process

        # TODO: do we want timestamps? Yes, we do, leaving that for refactoring later,
        # to use some reusable decorator.
        invocation.check_results = self.run_checks_before_test(
            invocation=invocation,
            environment=environment,
            logger=logger
            )

        # Execute the test, save the output and return code
        with Stopwatch() as timer:
            invocation.start_time = format_timestamp(timer.start_time)

            timeout: Optional[int]

            if self.data.interactive:
                if test.duration:
                    logger.warning(
                        'Ignoring requested duration, not supported in interactive mode.')

                timeout = None

            else:
                timeout = tmt.utils.duration_to_seconds(test.duration)

            try:
                output = guest.execute(
                    remote_command,
                    cwd=workdir,
                    env=environment,
                    join=True,
                    interactive=self.data.interactive,
                    tty=test.tty,
                    log=_test_output_logger,
                    timeout=timeout,
                    on_process_start=_save_process,
                    test_session=True,
                    friendly_command=str(test.test))
                invocation.return_code = 0
                stdout = output.stdout
            except tmt.utils.RunError as error:
                stdout = error.stdout

                invocation.return_code = error.returncode
                if invocation.return_code == tmt.utils.ProcessExitCodes.TIMEOUT:
                    logger.debug(f"Test duration '{test.duration}' exceeded.")

                elif tmt.utils.ProcessExitCodes.is_pidfile(invocation.return_code):
                    logger.warning('Test failed to manage its pidfile.')

        with invocation.process_lock:
            invocation.process = None

        invocation.end_time = format_timestamp(timer.end_time)
        invocation.real_duration = format_duration(timer.duration)

        # Save the captured output. Do not let the follow-up pulls
        # overwrite it.
        self.write(
            invocation.path / TEST_OUTPUT_FILENAME,
            stdout or '', mode='a', level=3)

        # Fetch #1: we need logs and everything the test produced so we could
        # collect its results.
        if invocation.is_guest_healthy:
            guest.pull(
                source=invocation.path,
                extend_options=[
                    *test.test_framework.get_pull_options(invocation, logger),
                    '--exclude', str(invocation.path / TEST_OUTPUT_FILENAME)
                    ])
            # Fetch plan data content as well in order to prevent
            # losing logs if the guest becomes later unresponsive.
            guest.pull(source=self.step.plan.data_directory)

        # Extract test results and store them in the invocation. Note
        # that these results will be overwritten with a fresh set of
        # results after a successful reboot in the middle of a test.
        invocation.results = self.extract_results(invocation, logger)

        invocation.check_results += self.run_checks_after_test(
            invocation=invocation,
            environment=environment,
            logger=logger
            )

        if invocation.is_guest_healthy:
            # Fetch #2: after-test checks might have produced remote files as well,
            # we need to fetch them too.
            guest.pull(
                source=invocation.path,
                extend_options=[
                    *test.test_framework.get_pull_options(invocation, logger),
                    '--exclude', str(invocation.path / TEST_OUTPUT_FILENAME)
                    ])
            # Fetch plan data content as well in order to prevent
            # losing logs if the guest becomes later unresponsive.
            guest.pull(source=self.step.plan.data_directory)

        # Attach check results to every test result. There might be more than one,
        # and it's hard to pick the main one, who knows what custom results might
        # cover, so let's make sure every single result can lead to check results
        # related to its lifetime.
        for result in invocation.results:
            result.check = invocation.check_results

        return invocation.results

    def go(
            self,
            *,
            guest: 'Guest',
            environment: Optional[tmt.utils.Environment] = None,
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
            extra_environment: Optional[Environment] = None,
            logger: tmt.log.Logger) -> None:
        """ Execute tests on provided guest """

        # Prepare tests and helper scripts, check options
        test_invocations = self.prepare_tests(guest, logger)

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

                self.execute(
                    invocation=invocation,
                    extra_environment=extra_environment,
                    logger=logger)

                assert invocation.real_duration is not None  # narrow type
                duration = click.style(invocation.real_duration, fg='cyan')
                shift = 1 if self.verbosity_level < 2 else 2

                # Handle test restart. May include guest reboot too.
                if invocation.restart_requested:
                    # Output before the restart
                    logger.verbose(f"{duration} {test.name} [{progress}]", shift=shift)

                    try:
                        if invocation.handle_restart():
                            continue

                    except tmt.utils.RebootTimeoutError:
                        for result in invocation.results:
                            result.result = ResultOutcome.ERROR
                            result.note = 'reboot timeout'

                    else:
                        for result in invocation.results:
                            result.result = ResultOutcome.ERROR
                            result.note = 'crashed too many times'

                # Handle reboot, abort, exit-first
                if invocation.reboot_requested:
                    # Output before the reboot
                    logger.verbose(
                        f"{duration} {test.name} [{progress}]", shift=shift)
                    try:
                        if invocation.handle_reboot():
                            continue
                    except tmt.utils.RebootTimeoutError:
                        for result in invocation.results:
                            result.result = ResultOutcome.ERROR
                            result.note = 'reboot timeout'

                if invocation.abort_requested:
                    for result in invocation.results:
                        # In case of aborted all results in list will be aborted
                        result.note = 'aborted'

                self._results.extend(invocation.results)

                # If test duration information is missing, print 8 spaces to keep indentation
                def _format_duration(result: BaseResult) -> str:
                    return click.style(result.duration, fg='cyan') if result.duration else 8 * ' '

                for result in invocation.results:
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

                if invocation.abort_requested or (
                    self.data.exit_first and any(
                        result.result not in (
                            ResultOutcome.PASS,
                            ResultOutcome.INFO) for result in invocation.results)):
                    # Clear the progress bar before outputting
                    progress_bar.clear()
                    what_happened = "aborted" if invocation.abort_requested else "failed"
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

    def essential_requires(self) -> list[tmt.base.Dependency]:
        """
        Collect all essential requirements of the plugin.

        Essential requirements of a plugin are necessary for the plugin to
        perform its basic functionality.

        :returns: a list of requirements.
        """

        return [
            tmt.base.DependencySimple('/usr/bin/flock')
            ]
