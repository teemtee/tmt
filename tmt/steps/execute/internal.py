import os
import textwrap
from typing import Any, Optional, cast

import jinja2

import tmt
import tmt.base
import tmt.log
import tmt.options
import tmt.steps
import tmt.steps.execute
import tmt.steps.scripts
import tmt.utils
import tmt.utils.signals
import tmt.utils.themes
from tmt.checks import CheckPlugin
from tmt.container import container, field
from tmt.result import Result, ResultOutcome
from tmt.steps import safe_filename
from tmt.steps.execute import (
    TEST_OUTPUT_FILENAME,
    AbortExecute,
    TestInvocation,
)
from tmt.steps.provision import Guest
from tmt.steps.report.display import ResultRenderer
from tmt.utils import (
    Environment,
    EnvVarValue,
    Path,
    ShellScript,
)
from tmt.utils.themes import style

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


#
# Shell wrappers for the test script.
#
# tmt must make sure running a test must allow for multiple external
# factors: the test timeout, interactivity, reboots and `tmt-reboot`
# invocations. tmt must present consistent info on what is the PID to
# kill from `tmt-reboot`, and where to save additional reboot info.
#
# To achieve these goals, tmt uses two wrappers, the inner and the outer
# one. The inner one wraps the actual test script as defined in test
# metadata, the outer one then runs the inner wrapper while performing
# other necessary steps. tmt invokes the outer wrapper which then
# invokes the inner wrapper which then invokes the test script.
#
# The inner wrapper exists to give tmt a single command to run to invoke
# the test. Test script may be a single command, but also a multiline,
# complicated shell script. To avoid issues with quotes and escaping
# things here and there, tmt saves the test script into the inner
# wrapper, and then the outer wrapper can work with just a single
# executable shell script.
#
# For the duration of the test, the outer wrapper creates so-called
# "test pidfile". The pidfile contains outer wrapper PID and path to the
# reboot-request file corresponding to the test being run. All actions
# against the pidfile must be taken while holding the pidfile lock,
# to serialize access between the wrapper and `tmt-reboot`. The file
# might be missing, that's allowed, but if it exists, it must contain
# correct info.
#
# Before quitting the outer wrapper, the pidfile is removed. There seems
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
# The outer wrapper handles 3 execution modes for the test command:
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

#: A template for the inner test wrapper filename.
#:
#: .. note::
#:
#:    It is passed to :py:func:`tmt.utils.safe_filename`, but includes
#:    also test name and serial number to make it unique even among all
#:    test wrappers. See #2997 for issue motivating the inclusion, it
#:    seems to be a good idea to prevent accidental reuse in general.
TEST_INNER_WRAPPER_FILENAME_TEMPLATE = 'tmt-test-wrapper-inner.sh-{{ INVOCATION.test.pathless_safe_name }}-{{ INVOCATION.test.serial_number }}'  # noqa: E501

#: A template for the outer test wrapper filename.
#:
#: .. note::
#:
#:    It is passed to :py:func:`tmt.utils.safe_filename`, but includes
#:    also test name and serial number to make it unique even among all
#:    test wrappers. See #2997 for issue motivating the inclusion, it
#:    seems to be a good idea to prevent accidental reuse in general.
TEST_OUTER_WRAPPER_FILENAME_TEMPLATE = 'tmt-test-wrapper-outer.sh-{{ INVOCATION.test.pathless_safe_name }}-{{ INVOCATION.test.serial_number }}'  # noqa: E501

#: A template for the inner test wrapper which invokes the test script.
TEST_INNER_WRAPPER_TEMPLATE = jinja2.Template(
    textwrap.dedent("""
{{ INVOCATION.test.test_framework.get_test_command(INVOCATION, LOGGER) }}
""")
)

#: A template for the outer test wrapper which handles most of the
#: orchestration and invokes the inner wrapper.
TEST_OUTER_WRAPPER_TEMPLATE = jinja2.Template(
    textwrap.dedent(
        """
{% macro log_to_dmesg(msg) %}
    {%- if not INVOCATION.guest.facts.is_superuser %}
        {%- if INVOCATION.guest.become %}
# Logging test into kernel log
sudo bash -c "echo \\\"{{ msg }}\\\" > /dev/kmsg"
        {%- else %}
# Not logging into kernel log: not a superuser, 'become' not enabled
# echo \"{{ msg }}\" > /dev/kmsg
        {%- endif %}
    {%- else %}
# Logging test into kernel log
echo "{{ msg }}" > /dev/kmsg
    {%- endif %}
{% endmacro %}

{% macro enter() %}
# Updating the tmt test pid file
mkdir -p "$(dirname $TMT_TEST_PIDFILE_LOCK)"
flock "$TMT_TEST_PIDFILE_LOCK" -c "echo '${test_pid} ${TMT_REBOOT_REQUEST}' > ${TMT_TEST_PIDFILE}" || exit 122

{{
    log_to_dmesg(
      "Running test '%s' (serial number %d) with reboot count %d and test restart count %d. (Be aware the test name is sanitized!)"
      | format(INVOCATION.test.safe_name, INVOCATION.test.serial_number, INVOCATION._reboot_count, INVOCATION._restart_count)
    )
}}
{%- endmacro %}

{% macro exit() %}
{{
    log_to_dmesg(
        "Leaving test '%s' (serial number %d). (Be aware the test name is sanitized!)"
        | format(INVOCATION.test.safe_name, INVOCATION.test.serial_number)
    )
}}

# Updating the tmt test pid file
mkdir -p "$(dirname $TMT_TEST_PIDFILE_LOCK)"
flock "$TMT_TEST_PIDFILE_LOCK" -c "rm -f ${TMT_TEST_PIDFILE}" || exit 123
{%- endmacro %}

# Make sure guest scripts path is searched by shell
if ! grep -q "{{ INVOCATION.guest.scripts_path }}" <<< "${PATH}"; then
    export PATH={{ INVOCATION.guest.scripts_path }}:${PATH}
fi

[ ! -z "$TMT_DEBUG" ] && set -x

test_pid="$$"

{% if INVOCATION.phase.data.interactive %}
{{ enter() }}

{{ TEST_COMMAND }}
_exit_code="$?"

{{ exit() }}

{% elif INVOCATION.test.tty %}
set -o pipefail

{{ enter() }}

{{ TEST_COMMAND }} 2>&1
_exit_code="$?"

{{ exit () }}

{% else %}
set -o pipefail

{{ enter() }}

{{ TEST_COMMAND }} </dev/null |& cat
_exit_code="$?"

{{ exit () }}
{% endif %}

# Return the original exit code of the test script
exit $_exit_code
"""  # noqa: E501
    )
)


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
            clear_on_exit=True,
        )

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


@container
class ExecuteInternalData(tmt.steps.execute.ExecuteStepData):
    script: list[ShellScript] = field(
        default_factory=list,
        option=('-s', '--script'),
        metavar='SCRIPT',
        multiple=True,
        help="""
            Execute arbitrary shell commands and check their exit
            code which is used as a test result. The ``script`` field
            is provided to cover simple test use cases only and must
            not be combined with the :ref:`/spec/plans/discover` step
            which is more suitable for more complex test scenarios.

            Default shell options are applied to the script, see
            :ref:`/spec/tests/test` for more details. The default
            :ref:`/spec/tests/duration` for tests defined directly
            under the execute step is ``1h``. Use the ``duration``
            attribute to modify the default limit.
            """,
        normalize=tmt.utils.normalize_shell_script_list,
        serialize=lambda scripts: [str(script) for script in scripts],
        unserialize=lambda serialized: [ShellScript(script) for script in serialized],
    )
    interactive: bool = field(
        default=False,
        option=('-i', '--interactive'),
        is_flag=True,
        help="""
             Run tests in interactive mode, i.e. with input and output streams
             shared with tmt itself. This allows input to be passed to tests
             via stdin, e.g. responding to password prompts. Test output in this
             mode is not captured, and ``duration`` has no effect.
             """,
    )
    restraint_compatible: bool = field(
        default=False,
        option=('--restraint-compatible / --no-restraint-compatible'),
        is_flag=True,
        help="""
             Run tests in the restraint-compatible mode. Enable this if
             your tests depend on the restraint scripts such as
             ``rstrnt-report-result`` or ``rstrnt-report-log``.
             Currently this option only affects whether the
             ``$OUTPUTFILE`` variable is respected, but in the future it
             will be used to enable/disable all restraint compatibility
             features.
             """,
    )
    no_progress_bar: bool = field(
        default=False,
        option='--no-progress-bar',
        is_flag=True,
        help='Disable interactive progress bar showing the current test.',
    )

    # ignore[override] & cast: two base classes define to_spec(), with conflicting
    # formal types.
    def to_spec(self) -> dict[str, Any]:  # type: ignore[override]
        data = cast(dict[str, Any], super().to_spec())
        data['script'] = [str(script) for script in self.script]

        return data


@tmt.steps.provides_method('tmt')
class ExecuteInternal(tmt.steps.execute.ExecutePlugin[ExecuteInternalData]):
    """
    Use the internal tmt executor to execute tests.

    The internal tmt executor runs tests on the guest one by one directly
    from the tmt code which shows testing :ref:`/stories/cli/steps/execute/progress`
    and supports :ref:`/stories/cli/steps/execute/interactive` debugging as well.
    This is the default execute step implementation. Test result is based on the
    script exit code (for shell tests) or the results file (for beakerlib tests).

    The executor provides the following shell scripts which can be used by the tests
    for certain operations.

    ``tmt-file-submit`` - archive the given file in the tmt test data directory.
    See the :ref:`/stories/features/report-log` section for more details.

    ``tmt-reboot`` - soft reboot the machine from inside the test. After reboot
    the execution starts from the test which rebooted the machine.
    An environment variable ``TMT_REBOOT_COUNT`` is provided which
    the test can use to handle the reboot. The variable holds the
    number of reboots performed by the test. For more information
    see the :ref:`/stories/features/reboot` feature documentation.

    ``tmt-report-result`` - generate a result report file from inside the test.
    Can be called multiple times by the test. The generated report
    file will be overwritten if a higher hierarchical result is
    reported by the test. The hierarchy is as follows:
    SKIP, PASS, WARN, FAIL. For more information see the
    :ref:`/stories/features/report-result` feature documentation.

    ``tmt-abort`` - generate an abort file from inside the test. This will
    set the current test result to failed and terminate
    the execution of subsequent tests. For more information see the
    :ref:`/stories/features/abort` feature documentation.

    The scripts are hosted by default in the ``/usr/local/bin`` directory, except
    for guests using ``rpm-ostree``, where ``/var/lib/tmt/scripts`` is used.
    The directory can be forced using the ``TMT_SCRIPTS_DIR`` environment variable.
    Note that for guests using ``rpm-ostree``, the directory is added to
    executable paths using the system-wide ``/etc/profile.d/tmt.sh`` profile script.

    .. warning::

        Please be aware that for guests using ``rpm-ostree``
        the provided scripts will only be available in a shell that
        loads the profile scripts. This is the default for
        ``bash``-like shells, but might not work for others.
    """

    _data_class = ExecuteInternalData
    data: ExecuteInternalData

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        self._previous_progress_message = ""

    def _test_environment(
        self,
        *,
        invocation: TestInvocation,
        extra_environment: Optional[Environment] = None,
        logger: tmt.log.Logger,
    ) -> Environment:
        """
        Return test environment
        """

        extra_environment = extra_environment or Environment()

        environment = extra_environment.copy()
        environment.update(invocation.test.environment)
        assert self.parent is not None
        assert isinstance(self.parent, tmt.steps.execute.Execute)
        assert self.parent.plan.my_run is not None

        environment['TMT_TEST_PIDFILE'] = EnvVarValue(
            effective_pidfile_root() / TEST_PIDFILE_FILENAME
        )
        environment['TMT_TEST_PIDFILE_LOCK'] = EnvVarValue(
            effective_pidfile_root() / TEST_PIDFILE_LOCK_FILENAME
        )
        environment["TMT_TEST_NAME"] = EnvVarValue(invocation.test.name)
        environment["TMT_TEST_DATA"] = EnvVarValue(invocation.test_data_path)
        environment['TMT_TEST_SERIAL_NUMBER'] = EnvVarValue(str(invocation.test.serial_number))
        environment['TMT_TEST_ITERATION_ID'] = EnvVarValue(
            f"{self.parent.plan.my_run.unique_id}-{invocation.test.serial_number}"
        )
        environment["TMT_TEST_METADATA"] = EnvVarValue(
            invocation.path / tmt.steps.execute.TEST_METADATA_FILENAME
        )
        environment["TMT_REBOOT_REQUEST"] = EnvVarValue(
            invocation.test_data_path / tmt.steps.scripts.TMT_REBOOT_SCRIPT.created_file
        )

        # Set the restraint-compatible mode if enabled
        environment["TMT_RESTRAINT_COMPATIBLE"] = EnvVarValue(
            str(int(self.data.restraint_compatible))
        )

        # Set all supported reboot variables
        for reboot_variable in tmt.steps.scripts.TMT_REBOOT_SCRIPT.related_variables:
            environment[reboot_variable] = EnvVarValue(str(invocation._reboot_count))
        environment['TMT_TEST_RESTART_COUNT'] = EnvVarValue(str(invocation._restart_count))

        # Add variables the framework wants to expose
        environment.update(
            invocation.test.test_framework.get_environment_variables(invocation, logger)
        )

        return environment

    def _test_output_logger(
        self,
        key: str,
        value: Optional[str] = None,
        color: tmt.utils.themes.Style = None,
        shift: int = 2,
        level: int = 3,
        topic: Optional[tmt.log.Topic] = None,
    ) -> None:
        """
        Custom logger for test output with shift 2 and level 3 defaults
        """

        self.verbose(key=key, value=value, color=color, shift=shift, level=level)

    def execute(
        self,
        *,
        invocation: TestInvocation,
        extra_environment: Optional[Environment] = None,
        logger: tmt.log.Logger,
    ) -> list[Result]:
        """
        Run test on the guest
        """

        test, guest = invocation.test, invocation.guest

        logger.debug(f"Execute '{test.name}' as a '{test.framework}' test.")

        # Test will be executed in it's own directory, relative to the workdir
        assert self.discover.workdir is not None  # narrow type
        assert test.path is not None  # narrow type
        workdir = self.discover.workdir / test.path.unrooted()
        logger.debug(f"Use workdir '{workdir}'.", level=3)

        # Create data directory, prepare test environment
        environment = self._test_environment(
            invocation=invocation, extra_environment=extra_environment, logger=logger
        )

        def _prepare_test_wrapper(
            label: str, filename_template: str, template: jinja2.Template, **variables: Any
        ) -> Path:
            # tmt wrapper filenames *must* be "unique" - the plugin might be handling
            # the same `discover` phase for different guests at the same time, and
            # must keep them isolated. The wrapper scripts, while being prepared, are
            # a shared global state, and we must prevent race conditions.
            test_wrapper_filename = safe_filename(
                filename_template, self, guest, INVOCATION=invocation
            )

            test_wrapper_filepath = workdir / test_wrapper_filename
            logger.debug(f'test {label} wrapper', test_wrapper_filepath)

            test_wrapper = ShellScript(
                template.render(LOGGER=logger, INVOCATION=invocation, **variables).strip()
            )
            self.debug(f'Test {label} wrapper', test_wrapper, level=3)

            self.write(test_wrapper_filepath, str(test_wrapper), 'w')
            test_wrapper_filepath.chmod(0o755)
            guest.push(
                source=test_wrapper_filepath,
                destination=test_wrapper_filepath,
                options=["-s", "-p", "--chmod=755"],
            )

            return test_wrapper_filepath

        # The inner test wrapper envelops the test script...
        test_inner_wrapper_filepath = _prepare_test_wrapper(
            'inner', TEST_INNER_WRAPPER_FILENAME_TEMPLATE, TEST_INNER_WRAPPER_TEMPLATE
        )

        # ... and it's a command the outer plugin invoke execute.
        test_outer_wrapper_filepath = _prepare_test_wrapper(
            'outer',
            TEST_OUTER_WRAPPER_FILENAME_TEMPLATE,
            TEST_OUTER_WRAPPER_TEMPLATE,
            TEST_COMMAND=ShellScript(f'./{test_inner_wrapper_filepath.name}'),
        )

        # Create topology files
        topology = tmt.steps.Topology(self.step.plan.provision.ready_guests)
        topology.guest = tmt.steps.GuestTopology(guest)

        environment.update(topology.push(dirpath=invocation.path, guest=guest, logger=logger))

        # Prepare the actual remote command
        remote_command: ShellScript
        if guest.become and not guest.facts.is_superuser:
            remote_command = ShellScript(f'sudo -E ./{test_outer_wrapper_filepath.name}')
        else:
            remote_command = ShellScript(f'./{test_outer_wrapper_filepath.name}')

        def _test_output_logger(
            key: str,
            value: Optional[str] = None,
            color: tmt.utils.themes.Style = None,
            shift: int = 2,
            level: int = 3,
            topic: Optional[tmt.log.Topic] = None,
        ) -> None:
            logger.verbose(
                key=key, value=value, color=color, shift=shift, level=level, topic=topic
            )

        # Insert internal checks
        invocation.test.check += CheckPlugin.internal_checks(logger)

        # TODO: do we want timestamps? Yes, we do, leaving that for refactoring later,
        # to use some reusable decorator.
        invocation.check_results = self.run_checks_before_test(
            invocation=invocation, environment=environment, logger=logger
        )

        # Pick the proper timeout for the test
        timeout: Optional[int]

        if self.data.interactive:
            if test.duration:
                logger.warning('Ignoring requested duration, not supported in interactive mode.')

            timeout = None

        elif self.data.ignore_duration:
            logger.debug("Test duration is not effective due to ignore-duration option.")
            timeout = None

        else:
            timeout = tmt.utils.duration_to_seconds(
                test.duration, tmt.base.DEFAULT_TEST_DURATION_L1
            )

        # And invoke the test process.
        output = invocation.invoke_test(
            remote_command,
            cwd=workdir,
            env=environment,
            interactive=self.data.interactive,
            log=_test_output_logger,
            timeout=timeout,
        )

        # Save the captured output. Do not let the follow-up pulls
        # overwrite it.
        self.write(invocation.path / TEST_OUTPUT_FILENAME, output.stdout or '', mode='a', level=3)

        def pull_from_guest() -> None:
            if not invocation.is_guest_healthy:
                return

            try:
                guest.pull(
                    source=invocation.path,
                    extend_options=[
                        *test.test_framework.get_pull_options(invocation, logger),
                        '--exclude',
                        str(invocation.path / TEST_OUTPUT_FILENAME),
                    ],
                )

                # Fetch plan data content as well in order to prevent
                # losing logs if the guest becomes later unresponsive.
                guest.pull(source=self.step.plan.data_directory)

            # Handle failing to pull test artifacts after guest becoming
            # unresponsive. If not handled test would stay in 'pending' state.
            # See issue https://github.com/teemtee/tmt/issues/3647.
            except tmt.utils.RunError:
                # TODO: We rely here on the traceback to print a reasonable
                # failure message, should be improved later.
                pass

        # Fetch #1: we need logs and everything the test produced so we could
        # collect its results.
        pull_from_guest()

        # Run after-test checks before extracting results
        invocation.check_results += self.run_checks_after_test(
            invocation=invocation, environment=environment, logger=logger
        )

        # Extract test results and store them in the invocation. Note
        # that these results will be overwritten with a fresh set of
        # results after a successful reboot in the middle of a test.
        invocation.results = self.extract_results(invocation, logger)

        # Fetch #2: after-test checks might have produced remote files as well,
        # we need to fetch them too.
        pull_from_guest()

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
        logger: tmt.log.Logger,
    ) -> None:
        """
        Execute available tests
        """

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
        logger: tmt.log.Logger,
    ) -> None:
        """
        Execute tests on provided guest
        """

        assert self.workdir is not None  # narrow type

        # Prepare tests, check options
        test_invocations = self.prepare_tests(guest, logger)

        # Push workdir to guest and execute tests
        guest.push()
        # We cannot use enumerate here due to continue in the code
        index = 0

        # TODO: plugin does not return any value. Results are exchanged
        # via `self.results`, to signal abort we need a bigger gun. Once
        # we get back to refactoring the plugin, this would turn into a
        # better way of transporting "plugin outcome" back to the step.
        abort_execute_exception: Optional[AbortExecute] = None

        with UpdatableMessage(self) as progress_bar:
            while index < len(test_invocations):
                invocation = test_invocations[index]

                test = invocation.test

                progress = f"{index + 1}/{len(test_invocations)}"
                progress_bar.update(progress, test.name)
                logger.verbose('test', test.summary or test.name, color='cyan', shift=1, level=2)

                self.execute(
                    invocation=invocation, extra_environment=extra_environment, logger=logger
                )

                assert invocation.real_duration is not None  # narrow type
                duration = style(invocation.real_duration, fg='cyan')
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
                            result.note.append('reboot timeout')

                    except tmt.utils.ReconnectTimeoutError:
                        for result in invocation.results:
                            result.result = ResultOutcome.ERROR
                            result.note.append('reconnect timeout')

                    else:
                        for result in invocation.results:
                            result.result = ResultOutcome.ERROR
                            result.note.append(
                                'crashed too many times, '
                                'you may want to set restart-max-count larger'
                            )

                # Handle reboot
                if invocation.reboot_requested:
                    # Output before the reboot
                    logger.verbose(f"{duration} {test.name} [{progress}]", shift=shift)
                    try:
                        if invocation.handle_reboot():
                            continue
                    except tmt.utils.RebootTimeoutError:
                        for result in invocation.results:
                            result.result = ResultOutcome.ERROR
                            result.note.append('reboot timeout')

                if invocation.abort_requested:
                    for result in invocation.results:
                        # In case of aborted all results in list will be aborted
                        result.note.append('aborted')

                self._results.extend(invocation.results)
                self.step.plan.execute.update_results(self.results())
                self.step.plan.execute.save()

                ResultRenderer(
                    basepath=self.workdir,
                    logger=logger,
                    shift=shift,
                    variables={'PROGRESS': f'[{progress}]'},
                ).print_results(invocation.results)

                abort_execute = invocation.abort_requested or (
                    self.data.exit_first
                    and any(
                        result.result in (ResultOutcome.FAIL, ResultOutcome.ERROR)
                        for result in invocation.results
                    )
                )

                if abort_execute:
                    if invocation.abort_requested:
                        abort_message = f'Test {test.name} aborted, stopping execution.'

                    else:
                        abort_message = f'Test {test.name} failed, stopping execution.'

                    abort_execute_exception = AbortExecute(abort_message)

                    progress_bar.clear()

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
                        invocation.results,
                        cwd=cwd,
                        env=self._test_environment(
                            invocation=invocation,
                            extra_environment=extra_environment,
                            logger=logger,
                        ),
                    )

        # Pull artifacts created in the plan data directory
        self.debug("Pull the plan data directory.", level=2)
        guest.pull(source=self.step.plan.data_directory)

        if abort_execute_exception:
            raise abort_execute_exception

    def results(self) -> list[Result]:
        """
        Return test results
        """

        return self._results

    def essential_requires(self) -> list[tmt.base.Dependency]:
        """
        Collect all essential requirements of the plugin.

        Essential requirements of a plugin are necessary for the plugin to
        perform its basic functionality.

        :returns: a list of requirements.
        """

        return [
            tmt.base.DependencySimple('/usr/bin/awk'),
            tmt.base.DependencySimple('/usr/bin/flock'),
        ]
