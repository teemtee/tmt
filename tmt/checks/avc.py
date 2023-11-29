import datetime
from typing import TYPE_CHECKING, Optional, Union

import tmt.log
import tmt.steps.execute
import tmt.steps.provision
import tmt.utils
from tmt.checks import Check, CheckEvent, CheckPlugin, provides_check
from tmt.result import CheckResult, ResultOutcome
from tmt.utils import CommandOutput, Path, ShellScript, render_run_exception_streams

if TYPE_CHECKING:
    from tmt.steps.execute import TestInvocation

TEST_POST_AVC_FILENAME = 'avc-{event}.txt'


@provides_check('avc')
class AvcDenials(CheckPlugin[Check]):
    """
    Check for SELinux AVC denials raised during the test.

    The check collects SELinux AVC denials from the audit log,
    gathers details about them, and together with versions of
    the ``selinux-policy`` and related packages stores them in
    a file after the test.

    .. code-block:: yaml

        check:
          - name: avc

    .. versionadded:: 1.28
    """

    _check_class = Check

    @classmethod
    def _save_report(
            cls,
            invocation: 'TestInvocation',
            event: CheckEvent,
            logger: tmt.log.Logger) -> tuple[ResultOutcome, Path]:

        if invocation.start_time is None:
            raise tmt.utils.GeneralError(
                "Test does not have start time recorded, cannot run AVC check.")

        from tmt.steps.execute import ExecutePlugin
        report_timestamp = ExecutePlugin.format_timestamp(
            datetime.datetime.now(datetime.timezone.utc))

        assert invocation.phase.step.workdir is not None  # narrow type
        path = invocation.check_files_path / TEST_POST_AVC_FILENAME.format(event=event.value)

        def _output_logger(
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

        # Collect all report components
        report: list[str] = [
            f'# Acquired at {report_timestamp}'
            ]

        # Flags indicating whether we were able to successfully fetch report components
        got_sestatus, got_rpm, got_ausearch, got_denials = False, False, False, False

        def _run_script(
                script: ShellScript,
                needs_sudo: bool = False) -> Union[
                    tuple[CommandOutput, Optional[tmt.utils.RunError]],
                    tuple[Optional[CommandOutput], tmt.utils.RunError]
                ]:
            if needs_sudo and invocation.guest.facts.is_superuser is False:
                script = ShellScript(f'sudo {script.to_shell_command()}')

            try:
                output = invocation.guest.execute(script, log=_output_logger, silent=True)

                return output, None

            except tmt.utils.RunError as exc:
                return None, exc

        def _report_success(label: str, output: tmt.utils.CommandOutput) -> list[str]:
            return [
                f'# {label}',
                output.stdout or '',
                ''
                ]

        def _report_failure(label: str, exc: tmt.utils.RunError) -> list[str]:
            return [
                f'# {label}',
                "\n".join(render_run_exception_streams(exc.stdout, exc.stderr, verbose=1)),
                ''
                ]

        # Get the `sestatus` output.
        output, exc = _run_script(ShellScript('sestatus'))

        if exc is None:
            assert output is not None

            got_sestatus = True

            report += _report_success('sestatus', output)

        else:
            report += _report_failure('sestatus', exc)

        # Record selinux-policy NVR.
        output, exc = _run_script(ShellScript('rpm -q selinux-policy'))

        if exc is None:
            assert output is not None

            got_rpm = True

            report += _report_success('rpm -q selinux-policy', output)

        else:
            report += _report_failure('rpm -q selinux-policy', exc)

        # Finally, run `ausearch`, to list AVC denials from the time the test started.
        start_timestamp = datetime.datetime.fromisoformat(invocation.start_time).timestamp()

        script = ShellScript(f"""
set -x
export AVC_SINCE=$(LC_ALL=en_US.UTF-8 date "+%m/%d/%Y %H:%M:%S" --date="@{start_timestamp}")
echo "$AVC_SINCE"
ausearch -i --input-logs -m AVC -m USER_AVC -m SELINUX_ERR -ts $AVC_SINCE
""")
        output, exc = _run_script(script, needs_sudo=True)

        # `ausearch` outcome evaluation is a bit more complicated than the one for a simple
        # `rpm -q`, because not all non-zero exit codes mean error.
        if exc is None:
            assert output is not None

            got_ausearch = True
            got_denials = True

            report += [
                '# ausearch',
                "\n".join(render_run_exception_streams(output.stdout, output.stderr, verbose=1)),
                ''
                ]

        else:
            if exc.returncode == 1 and exc.stderr and '<no matches>' in exc.stderr.strip():
                got_ausearch = True

            report += _report_failure('ausearch', exc)

        # If we were able to fetch all components successfully, pick the result based on `ausearch`
        # output.
        if all([got_sestatus, got_rpm, got_ausearch]):
            outcome = ResultOutcome.FAIL if got_denials else ResultOutcome.PASS

        # Otherwise, it's an error - we already made all output part of the report.
        else:
            outcome = ResultOutcome.ERROR

        invocation.phase.write(path, '\n'.join(report))

        return outcome, path.relative_to(invocation.phase.step.workdir)

    @classmethod
    def after_test(
            cls,
            *,
            check: 'Check',
            invocation: 'TestInvocation',
            environment: Optional[tmt.utils.EnvironmentType] = None,
            logger: tmt.log.Logger) -> list[CheckResult]:
        outcome, path = cls._save_report(invocation, CheckEvent.AFTER_TEST, logger)

        return [CheckResult(name='avc', result=outcome, log=[path])]
