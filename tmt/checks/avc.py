import datetime
import enum
import textwrap
import time
from typing import TYPE_CHECKING, Any, Optional, Union

import jinja2

import tmt.log
import tmt.utils
import tmt.utils.themes
from tmt.checks import Check, CheckPlugin, _RawCheck, provides_check
from tmt.container import container, field
from tmt.result import CheckResult, ResultOutcome, save_failures
from tmt.utils import (
    CommandOutput,
    Path,
    ShellScript,
    format_timestamp,
    render_command_report,
)

if TYPE_CHECKING:
    import tmt.base
    from tmt.steps.execute import TestInvocation
    from tmt.steps.provision import Guest


class TestMethod(enum.Enum):
    TIMESTAMP = 'timestamp'
    CHECKPOINT = 'checkpoint'

    @classmethod
    def from_spec(cls, spec: str) -> 'TestMethod':
        try:
            return TestMethod(spec)
        except ValueError:
            raise tmt.utils.SpecificationError(f"Invalid AVC check method '{spec}'.")

    @classmethod
    def normalize(
        cls,
        key_address: str,
        value: Any,
        logger: tmt.log.Logger,
    ) -> 'TestMethod':
        if isinstance(value, TestMethod):
            return value

        if isinstance(value, str):
            return cls.from_spec(value)

        raise tmt.utils.SpecificationError(f"Invalid AVC check method '{value}' at {key_address}.")


#: The filename of the final check report file.
TEST_POST_AVC_FILENAME = 'avc.txt'

#: The filename of the "mark" file ``ausearch`` on the guest.
AUSEARCH_MARK_FILENAME = 'avc-mark.txt'

#: Packages related to selinux and AVC reporting. Their versions would be made
#: part of the report.
INTERESTING_PACKAGES = ['audit', 'selinux-policy']


SETUP_SCRIPT = jinja2.Template(
    textwrap.dedent("""
set -x
export LC_ALL=C

{% if CHECK.test_method.value == 'timestamp' %}
echo "export AVC_SINCE=\\"$( date "+%x %H:%M:%S")\\"" > {{ MARK_FILEPATH }}
{% else %}
ausearch --input-logs --checkpoint {{ MARK_FILEPATH }} -m AVC -m USER_AVC -m SELINUX_ERR
{% endif %}

cat {{ MARK_FILEPATH }}
""")
)

TEST_SCRIPT = jinja2.Template(
    textwrap.dedent(
        """
set -x
export LC_ALL=C

{% if CHECK.test_method.value == 'timestamp' %}
source {{ MARK_FILEPATH }}
ausearch -i --input-logs -m AVC -m USER_AVC -m SELINUX_ERR -ts $AVC_SINCE
{% else %}
cat {{ MARK_FILEPATH }}
ausearch --input-logs --checkpoint {{ MARK_FILEPATH }} -m AVC -m USER_AVC -m SELINUX_ERR -i -ts checkpoint
{% endif %}
"""  # noqa: E501
    )
)


def _save_report(
    invocation: 'TestInvocation',
    report: list[str],
    timestamp: datetime.datetime,
    append: bool = False,
) -> Path:
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

    full_report = [''] if append else []

    full_report += [
        f'# Reported at {format_timestamp(timestamp)}',
        *report,
    ]

    invocation.phase.write(report_filepath, '\n'.join(full_report), mode='a' if append else 'w')

    return report_filepath


def _run_script(
    *,
    invocation: 'TestInvocation',
    script: ShellScript,
    needs_sudo: bool = False,
    logger: tmt.log.Logger,
) -> Union[tuple[CommandOutput, None], tuple[None, tmt.utils.RunError]]:
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
        color: tmt.utils.themes.Style = None,
        shift: int = 2,
        level: int = 3,
        topic: Optional[tmt.log.Topic] = None,
    ) -> None:
        logger.verbose(key=key, value=value, color=color, shift=shift, level=level, topic=topic)

    try:
        output = invocation.guest.execute(script, log=_output_logger, silent=True)

        return output, None

    except tmt.utils.RunError as exc:
        return None, exc


def _report_success(label: str, output: tmt.utils.CommandOutput) -> list[str]:
    """
    Format successful command output for the report
    """

    return list(render_command_report(label=label, output=output))


def _report_failure(label: str, exc: tmt.utils.RunError) -> list[str]:
    """
    Format failed command output for the report
    """

    return list(render_command_report(label=label, exc=exc))


def create_ausearch_mark(
    invocation: 'TestInvocation', check: 'AvcCheck', logger: tmt.log.Logger
) -> None:
    """
    Save a mark for ``ausearch`` in a file on the guest
    """

    ausearch_mark_filepath = invocation.check_files_path / AUSEARCH_MARK_FILENAME

    # Wait one second before storing the mark because ausearch
    # could catch denials from the previous test if they are executed
    # during the same second
    time.sleep(check.delay_before_report)

    report_timestamp = datetime.datetime.now(datetime.timezone.utc)
    report: list[str] = []

    script = ShellScript(
        SETUP_SCRIPT.render(CHECK=check, MARK_FILEPATH=ausearch_mark_filepath).strip()
    )

    output, exc = _run_script(invocation=invocation, script=script, logger=logger)

    if exc is None:
        assert output is not None

        report += _report_success('mark', output)

    else:
        report += _report_failure('mark', exc)

    _save_report(invocation, report, report_timestamp)


def create_final_report(
    invocation: 'TestInvocation',
    check: 'AvcCheck',
    logger: tmt.log.Logger,
) -> tuple[ResultOutcome, list[Path]]:
    """
    Collect the data, evaluate and create the final report
    """

    if invocation.start_time is None:
        raise tmt.utils.GeneralError(
            "Test does not have start time recorded, cannot run AVC check."
        )

    ausearch_mark_filepath = invocation.check_files_path / AUSEARCH_MARK_FILENAME

    # Wait one second before storing the mark because ausearch
    # could catch denials from the previous test if they are executed
    # during the same second
    time.sleep(check.delay_before_report)

    # Collect all report components
    report_timestamp = datetime.datetime.now(datetime.timezone.utc)
    report: list[str] = []
    failures: list[str] = []

    # Flags indicating whether we were able to successfully fetch report components
    got_sestatus, got_rpm, got_ausearch, got_denials = False, False, False, False

    # Get the `sestatus` output.
    output, exc = _run_script(invocation=invocation, script=ShellScript('sestatus'), logger=logger)

    if exc is None:
        assert output is not None

        got_sestatus = True

        report += _report_success('sestatus', output)

    else:
        failure = _report_failure('sestatus', exc)
        report += failure
        failures.append('\n'.join(failure))

    # Record NVRs of interesting packages.
    interesting_packages = ' '.join(INTERESTING_PACKAGES)
    output, exc = _run_script(
        invocation=invocation, script=ShellScript(f'rpm -q {interesting_packages}'), logger=logger
    )

    if exc is None:
        assert output is not None

        got_rpm = True

        report += _report_success(f'rpm -q {interesting_packages}', output)

    else:
        failure = _report_failure(f'rpm -q {interesting_packages}', exc)
        report += failure
        failures.append('\n'.join(failure))

    # Finally, run `ausearch`, to list AVC denials from the time the test started.
    script = ShellScript(
        TEST_SCRIPT.render(CHECK=check, MARK_FILEPATH=ausearch_mark_filepath).strip()
    )

    output, exc = _run_script(invocation=invocation, script=script, needs_sudo=True, logger=logger)

    # `ausearch` outcome evaluation is a bit more complicated than the one for a simple
    # `rpm -q`, because not all non-zero exit codes mean error.
    if exc is None:
        assert output is not None

        got_ausearch = True
        got_denials = True

        failure = list(render_command_report(label='ausearch', output=output))
        report += failure
        failures.append('\n'.join(failure))

    else:
        failure = _report_failure('ausearch', exc)
        report += failure

        if exc.returncode == 1 and exc.stderr and '<no matches>' in exc.stderr.strip():
            got_ausearch = True
        else:
            failures.append('\n'.join(failure))

    # If we were able to fetch all components successfully, pick the result based on `ausearch`
    # output.
    if all([got_sestatus, got_rpm, got_ausearch]):
        outcome = ResultOutcome.FAIL if got_denials else ResultOutcome.PASS

    # Otherwise, it's an error - we already made all output part of the report.
    else:
        outcome = ResultOutcome.ERROR

    assert invocation.phase.step.workdir is not None  # narrow type
    report_filepath = _save_report(invocation, report, report_timestamp, append=True)
    paths = [
        report_filepath.relative_to(invocation.phase.step.workdir),
        save_failures(invocation, invocation.check_files_path, failures),
    ]

    return outcome, paths


@container
class AvcCheck(Check):
    test_method: TestMethod = field(
        default=TestMethod.TIMESTAMP,
        choices=[method.value for method in TestMethod],
        help="""
             Which method to use when calling ``ausearch`` to report new
             AVC denials. With ``checkpoint``, native ``--checkpoint``
             option of ``ausearch`` is used, while ``timestamp`` will
             depend on ``--ts`` option and a date/time recorded before
             the test.
             """,
        normalize=TestMethod.normalize,
        serialize=lambda method: method.value,
        unserialize=lambda serialized: TestMethod.from_spec(serialized),
        exporter=lambda method: method.value,
    )

    delay_before_report: int = field(
        default=5,
        metavar='SECONDS',
        help="""
             How many seconds to wait before running ``ausearch`` after
             the test. Increasing it may help when events do reach logs
             fast enough for ``ausearch`` report them.
             """,
        normalize=tmt.utils.normalize_int,
    )

    # TODO: fix `to_spec` of `Check` to support nested serializables
    def to_spec(self) -> _RawCheck:
        spec = super().to_spec()

        spec['test-method'] = self.test_method.value  # type: ignore[reportGeneralTypeIssues,typeddict-unknown-key,unused-ignore]

        return spec


@provides_check('avc')
class AvcDenials(CheckPlugin[AvcCheck]):
    #
    # This plugin docstring has been reviewed and updated to follow
    # our documentation best practices. When changing it, please make
    # sure new changes are following them as well.
    #
    # https://tmt.readthedocs.io/en/stable/contribute.html#docs
    #
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
        :ref:`skip</spec/results/outcomes>` result, and
        without ``auditd``, the check will discover no AVC denials,
        reporting :ref:`pass</spec/results/outcomes>`.

        If the test manipulates ``auditd`` or SELinux in general, the
        check may report unexpected results.

    .. versionadded:: 1.28
    """

    _check_class = AvcCheck

    @classmethod
    def essential_requires(
        cls,
        guest: 'Guest',
        test: 'tmt.base.Test',
        logger: tmt.log.Logger,
    ) -> list['tmt.base.DependencySimple']:
        if not guest.facts.has_selinux:
            return []

        # Avoid circular imports
        import tmt.base

        # Note: yes, this will most likely explode in any distro outside
        # of Fedora, CentOS and RHEL.
        return [tmt.base.DependencySimple('audit'), tmt.base.DependencySimple('policycoreutils')]

    @classmethod
    def before_test(
        cls,
        *,
        check: 'AvcCheck',
        invocation: 'TestInvocation',
        environment: Optional[tmt.utils.Environment] = None,
        logger: tmt.log.Logger,
    ) -> list[CheckResult]:
        if invocation.guest.facts.has_selinux:
            create_ausearch_mark(invocation, check, logger)

        return []

    @classmethod
    def after_test(
        cls,
        *,
        check: 'AvcCheck',
        invocation: 'TestInvocation',
        environment: Optional[tmt.utils.Environment] = None,
        logger: tmt.log.Logger,
    ) -> list[CheckResult]:
        if not invocation.guest.facts.has_selinux:
            return [CheckResult(name='avc', result=ResultOutcome.SKIP)]

        if not invocation.is_guest_healthy:
            return [CheckResult(name='dmesg', result=ResultOutcome.SKIP)]

        assert invocation.phase.step.workdir is not None  # narrow type

        outcome, paths = create_final_report(invocation, check, logger)

        return [CheckResult(name='avc', result=outcome, log=paths)]
