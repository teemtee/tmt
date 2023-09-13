import dataclasses
import json
import os
import sys
from contextlib import suppress
from typing import Any, Dict, List, Optional, cast

import click

import tmt
import tmt.base
import tmt.log
import tmt.options
import tmt.steps
import tmt.steps.execute
import tmt.utils
from tmt.base import Test
from tmt.result import BaseResult, CheckResult, Result, ResultOutcome
from tmt.steps.execute import SCRIPTS, TEST_OUTPUT_FILENAME, TMT_REBOOT_SCRIPT
from tmt.steps.provision import Guest
from tmt.utils import EnvironmentType, Path, ShellScript, Stopwatch, field

TEST_WRAPPER_FILENAME = 'tmt-test-wrapper.sh'

TEST_WRAPPER_INTERACTIVE = '{remote_command}'
TEST_WRAPPER_NONINTERACTIVE = 'set -eo pipefail; {remote_command} </dev/null |& cat'


@dataclasses.dataclass
class ExecuteInternalData(tmt.steps.execute.ExecuteStepData):
    script: List[ShellScript] = field(
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
    def to_spec(self) -> Dict[str, Any]:  # type: ignore[override]
        data = cast(Dict[str, Any], super().to_spec())
        data['script'] = [str(script) for script in self.script]

        return data


@tmt.steps.provides_method('tmt')
class ExecuteInternal(tmt.steps.execute.ExecutePlugin):
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

    # TODO: consider switching to utils.updatable_message() - might need more
    # work, since use of _show_progress is split over several methods.
    def _show_progress(self, progress: str, test_name: str,
                       finish: bool = False) -> None:
        """
        Show an interactive progress bar in non-verbose mode.

        If the output is not an interactive terminal, or progress bar is
        disabled using an option, just output the message as info without
        utilising \r. If finish is True, overwrite the previous progress bar.
        """
        # Verbose mode outputs other information, using \r to
        # create a status bar wouldn't work.
        if self.verbosity_level:
            return

        # No progress if terminal not attached or explicitly disabled
        if not sys.stdout.isatty() or self.data.no_progress_bar:
            return

        # For debug mode show just an info message (unless finishing)
        message = f"{test_name} [{progress}]" if not finish else ""
        if self.debug_level:
            if not finish:
                self.info(message, shift=1)
            return

        # Show progress bar in an interactive shell.
        # We need to completely override the previous message, add
        # spaces if necessary.
        message = message.ljust(len(self._previous_progress_message))
        self._previous_progress_message = message
        message = self._indent('progress', message, color='cyan')
        sys.stdout.write(f"\r{message}")
        if finish:
            # The progress has been overwritten, return back to the start
            sys.stdout.write("\r")
            self._previous_progress_message = ""
        sys.stdout.flush()

    def _test_environment(
            self,
            *,
            test: Test,
            guest: Guest,
            extra_environment: Optional[EnvironmentType] = None,
            logger: tmt.log.Logger) -> EnvironmentType:
        """ Return test environment """

        extra_environment = extra_environment or {}

        data_directory = self.data_path(test, guest, full=True, create=True)

        environment = extra_environment.copy()
        environment.update(test.environment)
        assert self.parent is not None
        assert isinstance(self.parent, tmt.steps.execute.Execute)

        environment["TMT_TEST_NAME"] = test.name
        environment["TMT_TEST_DATA"] = str(data_directory / tmt.steps.execute.TEST_DATA)
        environment['TMT_TEST_SERIAL_NUMBER'] = str(test.serialnumber)
        environment["TMT_TEST_METADATA"] = str(
            data_directory / tmt.steps.execute.TEST_METADATA_FILENAME)
        environment["TMT_REBOOT_REQUEST"] = str(
            data_directory / tmt.steps.execute.TEST_DATA / TMT_REBOOT_SCRIPT.created_file)
        # Set all supported reboot variables
        for reboot_variable in TMT_REBOOT_SCRIPT.related_variables:
            environment[reboot_variable] = str(test._reboot_count)

        # Add variables the framework wants to expose
        environment.update(test.test_framework.get_environment_variables(
            self, test, guest, logger))

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
            test: Test,
            guest: Guest,
            extra_environment: Optional[EnvironmentType] = None,
            logger: tmt.log.Logger) -> List[CheckResult]:
        """ Run test on the guest """
        logger.debug(f"Execute '{test.name}' as a '{test.framework}' test.")

        test_check_results: List[CheckResult] = []

        # Test will be executed in it's own directory, relative to the workdir
        assert self.discover.workdir is not None  # narrow type
        assert test.path is not None  # narrow type
        workdir = self.discover.workdir / test.path.unrooted()
        logger.debug(f"Use workdir '{workdir}'.", level=3)

        # Create data directory, prepare test environment
        environment = self._test_environment(
            test=test,
            guest=guest,
            extra_environment=extra_environment,
            logger=logger)

        # tmt wrapper filename *must* be "unique" - the plugin might be handling
        # the same `discover` phase for different guests at the same time, and
        # must keep them isolated. The wrapper script, while being prepared, is
        # a shared global state, and we must prevent race conditions.
        test_wrapper_filename = f'{TEST_WRAPPER_FILENAME}.{guest.name}'
        test_wrapper_filepath = workdir / test_wrapper_filename

        logger.debug('test wrapper', test_wrapper_filepath)

        # Prepare the test command
        test_command = test.test_framework.get_test_command(self, test, guest, logger)
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
            dirpath=self.data_path(test, guest, full=True),
            guest=guest,
            logger=logger))

        # Prepare the actual remote command
        remote_command = ShellScript(f'./{test_wrapper_filename}')
        if self.get('interactive'):
            remote_command = ShellScript(
                TEST_WRAPPER_INTERACTIVE.format(
                    remote_command=remote_command))
        else:
            remote_command = ShellScript(
                TEST_WRAPPER_NONINTERACTIVE.format(
                    remote_command=remote_command))

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
            guest=guest,
            test=test,
            environment=environment,
            logger=logger
            )

        # Execute the test, save the output and return code
        with Stopwatch() as timer:
            test.starttime = self.format_timestamp(timer.starttime)

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
                test.returncode = 0
                stdout = output.stdout
            except tmt.utils.RunError as error:
                stdout = error.stdout
                test.returncode = error.returncode
                if test.returncode == tmt.utils.PROCESS_TIMEOUT:
                    logger.debug(f"Test duration '{test.duration}' exceeded.")

        test.endtime = self.format_timestamp(timer.endtime)
        test.real_duration = self.format_duration(timer.duration)

        test.data_path = self.data_path(test, guest, "data")

        self.write(
            self.data_path(test, guest, TEST_OUTPUT_FILENAME, full=True),
            stdout or '', mode='a', level=3)

        # TODO: do we want timestamps? Yes, we do, leaving that for refactoring later,
        # to use some reusable decorator.
        test_check_results += self.run_checks_after_test(
            guest=guest,
            test=test,
            environment=environment,
            logger=logger
            )

        return test_check_results

    def _will_reboot(self, test: Test, guest: Guest) -> bool:
        """ True if reboot is requested """
        return self._reboot_request_path(test, guest).exists()

    def _reboot_request_path(self, test: Test, guest: Guest) -> Path:
        """ Return reboot_request """
        return self.data_path(test, guest, full=True) \
            / tmt.steps.execute.TEST_DATA \
            / TMT_REBOOT_SCRIPT.created_file

    def _handle_reboot(self, test: Test, guest: Guest) -> bool:
        """
        Reboot the guest if the test requested it.

        Check for presence of a file signalling reboot request
        and orchestrate the reboot if it was requested. Also increment
        REBOOTCOUNT variable, reset it to 0 if no reboot was requested
        (going forward to the next test). Return whether reboot was done.
        """
        if self._will_reboot(test, guest):
            test._reboot_count += 1
            self.debug(f"Reboot during test '{test}' "
                       f"with reboot count {test._reboot_count}.")
            reboot_request_path = self._reboot_request_path(test, guest)
            test_data = self.data_path(test, guest, full=True) / tmt.steps.execute.TEST_DATA
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
            guest.push(test_data)
            rebooted = False
            try:
                rebooted = guest.reboot(command=reboot_command, timeout=timeout)
            except tmt.utils.RunError:
                self.fail(
                    f"Failed to reboot guest using the "
                    f"custom command '{reboot_command}'.")
                raise
            except tmt.utils.ProvisionError:
                self.warn(
                    "Guest does not support soft reboot, "
                    "trying hard reboot.")
                rebooted = guest.reboot(hard=True, timeout=timeout)
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
        tests = self.prepare_tests(guest)

        # Prepare scripts, except localhost guest
        if not guest.localhost:
            self.prepare_scripts(guest)

        # Push workdir to guest and execute tests
        guest.push()
        # We cannot use enumerate here due to continue in the code
        index = 0
        while index < len(tests):
            test = tests[index]

            progress = f"{index + 1}/{len(tests)}"
            self._show_progress(progress, test.name)
            logger.verbose(
                'test', test.summary or test.name, color='cyan', shift=1, level=2)

            test_check_results: List[CheckResult] = self.execute(
                test=test,
                guest=guest,
                extra_environment=extra_environment,
                logger=logger)

            guest.pull(
                source=self.data_path(test, guest, full=True),
                extend_options=test.test_framework.get_pull_options(self, test, guest, logger))

            results = self.extract_results(test, guest, logger)  # Produce list of results

            for result in results:
                result.check = test_check_results

            assert test.real_duration is not None  # narrow type
            duration = click.style(test.real_duration, fg='cyan')
            shift = 1 if self.verbosity_level < 2 else 2

            # Handle reboot, abort, exit-first
            if self._will_reboot(test, guest):
                # Output before the reboot
                logger.verbose(
                    f"{duration} {test.name} [{progress}]", shift=shift)
                try:
                    if self._handle_reboot(test, guest):
                        continue
                except tmt.utils.RebootTimeoutError:
                    for result in results:
                        result.result = ResultOutcome.ERROR
                        result.note = 'reboot timeout'
            abort = self.check_abort_file(test, guest)
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
                self._show_progress('', '', True)
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
                        test=test,
                        guest=guest,
                        extra_environment=extra_environment,
                        logger=logger),
                    )
        # Overwrite the progress bar, the test data is irrelevant
        self._show_progress('', '', True)

        # Pull artifacts created in the plan data directory
        self.debug("Pull the plan data directory.", level=2)
        guest.pull(source=self.step.plan.data_directory)

    def results(self) -> List[Result]:
        """ Return test results """
        return self._results

    def requires(self) -> List[tmt.base.Dependency]:
        """ All requirements of the plugin on the guest """
        return []
