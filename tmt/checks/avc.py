import datetime
import time
from typing import TYPE_CHECKING, Optional, Union

import tmt.log
import tmt.steps.execute
import tmt.steps.provision
import tmt.utils
from tmt.checks import Check, CheckPlugin, provides_check
from tmt.result import CheckResult, ResultOutcome
from tmt.utils import (
    CommandOutput,
    Path,
    ShellScript,
    format_timestamp,
    render_run_exception_streams,
    )

if TYPE_CHECKING:
    import tmt.base
    from tmt.steps.execute import TestInvocation
    from tmt.steps.provision import Guest

#: The filename of the final check report file.
TEST_POST_AVC_FILENAME = 'avc.txt'

#: The filename of the file storing "since" timestamp for ``ausearch`` on the guest.
AUSEARCH_TIMESTAMP_FILENAME = 'avc-timestamp.sh'

#: Packages related to selinux and AVC reporting. Their versions would be made
#: part of the report.
INTERESTING_PACKAGES = [
    'audit',
    'selinux-policy'
    ]


def _save_report(
        invocation: 'TestInvocation',
        report: list[str],
        timestamp: datetime.datetime,
        append: bool = False) -> Path:
    """
    Save the given report into check's report file.

    :param invocation: test invocation to which the check belongs to.
        The report file path would be in this invocation's
        :py:attr:`check_files_path`.
    :param report: lines of the report.
    :param timestamp: time at which the report has been created. It will
        be saved in the report file, before the report itself.
    :param append: if set, the report would be appended to the report
        file instead of overwriting it.
    :returns: path to the report file.
    """

    report_filepath = invocation.check_files_path / TEST_POST_AVC_FILENAME

    report = [
        f'# Reported at {format_timestamp(timestamp)}',
        *report
        ]

    mode = 'a' if append else 'w'

    invocation.phase.write(report_filepath, '\n'.join(report), mode=mode)

    return report_filepath


def _run_script(
        *,
        invocation: 'TestInvocation',
        script: ShellScript,
        needs_sudo: bool = False,
        logger: tmt.log.Logger) -> Union[
            tuple[CommandOutput, None],
            tuple[None, tmt.utils.RunError]
        ]:
    """
    A helper to run a script on the guest.

    Instead of letting failed commands to interrupt execution by raising
    exceptions, this helper intercepts them and returns them together
    with command output. This let's us log them in the report file.

    :returns: a tuple of two items, either a command output and
        ``None``, or ``None`` and captured :py:class:`RunError`
        describing the command failure.
    """

    if needs_sudo and invocation.guest.facts.is_superuser is False:
        script = ShellScript(f'sudo {script.to_shell_command()}')

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

    try:
        output = invocation.guest.execute(script, log=_output_logger, silent=True)

        return output, None

    except tmt.utils.RunError as exc:
        return None, exc


def _report_success(label: str, output: tmt.utils.CommandOutput) -> list[str]:
    """ Format successful command output for the report """

    return [
        f'# {label}',
        output.stdout or '',
        ''
        ]


def _report_failure(label: str, exc: tmt.utils.RunError) -> list[str]:
    """ Format failed command output for the report """

    return [
        f'# {label}',
        "\n".join(render_run_exception_streams(exc.stdout, exc.stderr, verbose=1)),
        ''
        ]


def create_ausearch_timestamp(
        invocation: 'TestInvocation',
        logger: tmt.log.Logger) -> None:
    """ Save a timestamp for ``ausearch`` in a file on the guest """

    ausearch_timestamp_filepath = invocation.check_files_path / AUSEARCH_TIMESTAMP_FILENAME

    report_timestamp = datetime.datetime.now(datetime.timezone.utc)
    report: list[str] = []

    # Wait one second before storing the timestamp because ausearch
    # could catch denials from the previous test if they are executed
    # during the same second
    time.sleep(1)

    script = ShellScript(f"""
set -x
export LC_ALL=en_US.UTF-8
echo "export AVC_SINCE=\\"$( date "+%m/%d/%Y %H:%M:%S")\\"" > {ausearch_timestamp_filepath}
cat {ausearch_timestamp_filepath}
""")

    output, exc = _run_script(
        invocation=invocation,
        script=script,
        logger=logger)

    if exc is None:
        assert output is not None

        report += _report_success('timestamp', output)

    else:
        report += _report_failure('timestamp', exc)

    _save_report(invocation, report, report_timestamp)


def create_final_report(
        invocation: 'TestInvocation',
        logger: tmt.log.Logger) -> tuple[ResultOutcome, Path]:
    """ Collect the data, evaluate and create the final report """

    if invocation.start_time is None:
        raise tmt.utils.GeneralError(
            "Test does not have start time recorded, cannot run AVC check.")

    ausearch_timestamp_filepath = invocation.check_files_path / AUSEARCH_TIMESTAMP_FILENAME

    # Collect all report components
    report_timestamp = datetime.datetime.now(datetime.timezone.utc)
    report: list[str] = []

    # Flags indicating whether we were able to successfully fetch report components
    got_sestatus, got_rpm, got_ausearch, got_denials = False, False, False, False

    # Get the `sestatus` output.
    output, exc = _run_script(
        invocation=invocation,
        script=ShellScript('sestatus'),
        logger=logger)

    if exc is None:
        assert output is not None

        got_sestatus = True

        report += _report_success('sestatus', output)

    else:
        report += _report_failure('sestatus', exc)

    # Record NVRs of interesting packages.
    interesting_packages = ' '.join(INTERESTING_PACKAGES)
    output, exc = _run_script(
        invocation=invocation,
        script=ShellScript(f'rpm -q {interesting_packages}'),
        logger=logger)

    if exc is None:
        assert output is not None

        got_rpm = True

        report += _report_success(f'rpm -q {interesting_packages}', output)

    else:
        report += _report_failure(f'rpm -q {interesting_packages}', exc)

    # Finally, run `ausearch`, to list AVC denials from the time the test started.
    script = ShellScript(f"""
set -x
source {ausearch_timestamp_filepath}
ausearch -i --input-logs -m AVC -m USER_AVC -m SELINUX_ERR -ts $AVC_SINCE
""")
    output, exc = _run_script(
        invocation=invocation,
        script=script,
        needs_sudo=True,
        logger=logger)

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

    report_filepath = _save_report(invocation, report, report_timestamp, append=True)

    return outcome, report_filepath


@provides_check('avc')
class AvcDenials(CheckPlugin[Check]):
    """
    Check for SELinux AVC denials raised during the test.

    The check collects SELinux AVC denials from the audit log,
    gathers details about them, and together with versions of
    the ``selinux-policy`` and related packages stores them in
    a report file after the test.

    .. code-block:: yaml

        check:
          - name: avc

    .. note::

        To work correctly, the check requires SELinux to be enabled on the
        guest, and ``auditd`` must be running. Without SELinux, the
        check will turn into no-op, reporting
        :ref:`skip</spec/plans/results/outcomes>` result, and
        without ``auditd``, the check will discover no AVC denials,
        reporting :ref:`pass</spec/plans/results/outcomes>`.

        If the test manipulates ``auditd`` or SELinux in general, the
        check may report unexpected results.

    .. versionadded:: 1.28
    """

    _check_class = Check

    @classmethod
    def essential_requires(
            cls,
            guest: 'Guest',
            test: 'tmt.base.Test',
            logger: tmt.log.Logger) -> list['tmt.base.DependencySimple']:
        if not guest.facts.has_selinux:
            return []

        # Avoid circular imports
        import tmt.base

        return [
            tmt.base.DependencySimple('/usr/sbin/sestatus'),
            tmt.base.DependencySimple('/usr/sbin/ausearch')
            ]

    @classmethod
    def before_test(
            cls,
            *,
            check: 'Check',
            invocation: 'TestInvocation',
            environment: Optional[tmt.utils.Environment] = None,
            logger: tmt.log.Logger) -> list[CheckResult]:
        if invocation.guest.facts.has_selinux:
            create_ausearch_timestamp(invocation, logger)

        return []

    @classmethod
    def after_test(
            cls,
            *,
            check: 'Check',
            invocation: 'TestInvocation',
            environment: Optional[tmt.utils.Environment] = None,
            logger: tmt.log.Logger) -> list[CheckResult]:
        if not invocation.guest.facts.has_selinux:
            return [CheckResult(
                name='avc',
                result=ResultOutcome.SKIP)]

        if not invocation.is_guest_healthy:
            return [CheckResult(name='dmesg', result=ResultOutcome.SKIP)]

        assert invocation.phase.step.workdir is not None  # narrow type

        outcome, path = create_final_report(invocation, logger)

        return [CheckResult(
            name='avc',
            result=outcome,
            log=[path.relative_to(invocation.phase.step.workdir)])]
