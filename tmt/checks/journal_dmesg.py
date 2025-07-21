import datetime
import re
import textwrap
from re import Pattern
from typing import TYPE_CHECKING, Optional, Union

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

#: The filename of the final check report file.
TEST_POST_JOURNAL_DMESG_FILENAME = 'journal-dmesg.txt'

#: The filename of the "mark" file ``journalctl`` on the guest.
JOURNALCTL_MARK_FILENAME = 'journal-mark.txt'

DEFAULT_FAILURE_PATTERNS = [
    re.compile(pattern)
    for pattern in [
        r'Call Trace:',
        r'\ssegfault\s',
    ]
]

SETUP_SCRIPT = jinja2.Template(
    textwrap.dedent("""
set -x
export LC_ALL=C

echo "export JOURNALCTL_SINCE=\\"$( date "+%Y-%m-%dT%H:%M:%S.%6N%:z")\\"" > {{ MARK_FILEPATH }}
cat {{ MARK_FILEPATH }}
""")
)

TEST_SCRIPT = jinja2.Template(
    textwrap.dedent(
        """
set -x
export LC_ALL=C

source {{ MARK_FILEPATH }}
journalctl _TRANSPORT=kernel -S $JOURNALCTL_SINCE
"""
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

    report_filepath = invocation.check_files_path / TEST_POST_JOURNAL_DMESG_FILENAME

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


@container
class JournalDmesgCheck(Check):
    failure_pattern: list[Pattern[str]] = field(
        default_factory=lambda: DEFAULT_FAILURE_PATTERNS[:],
        help="""
             List of regular expressions to look for in ``journal``
             log. If any of patterns is found, ``journal-dmesg`` check will
             report ``fail`` result.
             """,
        metavar='PATTERN',
        normalize=tmt.utils.normalize_pattern_list,
        exporter=lambda patterns: [pattern.pattern for pattern in patterns],
        serialize=lambda patterns: [pattern.pattern for pattern in patterns],
        unserialize=lambda serialized: [re.compile(pattern) for pattern in serialized],
    )

    # TODO: fix `to_spec` of `Check` to support nested serializables
    def to_spec(self) -> _RawCheck:
        spec = super().to_spec()

        spec['failure-pattern'] = [  # type: ignore[reportGeneralTypeIssues,typeddict-unknown-key,unused-ignore]
            pattern.pattern for pattern in self.failure_pattern
        ]

        return spec

    def to_minimal_spec(self) -> _RawCheck:
        return self.to_spec()

    def _extract_failures(self, text: str) -> list[str]:
        return [
            line
            for line in text.splitlines()
            if any(pattern.search(line) for pattern in self.failure_pattern)
        ]

    def _get_mark_file(self, invocation: 'TestInvocation') -> Path:
        return invocation.check_files_path / JOURNALCTL_MARK_FILENAME

    def _create_journalctl_mark(
        self, invocation: 'TestInvocation', logger: tmt.log.Logger
    ) -> None:
        """
        Save a mark for ``journalctl`` in a file on the guest
        """
        report_timestamp = datetime.datetime.now(datetime.timezone.utc)
        report: list[str] = []

        script = ShellScript(
            SETUP_SCRIPT.render(MARK_FILEPATH=self._get_mark_file(invocation)).strip()
        )

        output, exc = _run_script(invocation=invocation, script=script, logger=logger)

        if exc is None:
            assert output is not None
            report += _report_success('mark', output)
        else:
            report += _report_failure('mark', exc)

        _save_report(invocation, report, report_timestamp)

    def _save_journal_dmesg(
        self, invocation: 'TestInvocation', logger: tmt.log.Logger
    ) -> tuple[ResultOutcome, list[Path]]:
        assert invocation.phase.step.workdir is not None  # narrow type
        assert invocation.start_time is not None  # narrow type

        report_timestamp = datetime.datetime.now(datetime.timezone.utc)
        report: list[str] = []

        script = ShellScript(
            TEST_SCRIPT.render(MARK_FILEPATH=self._get_mark_file(invocation)).strip()
        )
        output, exc = _run_script(
            invocation=invocation, script=script, needs_sudo=True, logger=logger
        )

        if exc is None:
            assert output is not None
            report += _report_success('journalctl dmesg', output)
            outcome = ResultOutcome.PASS
        else:
            report += _report_failure('journalctl dmesg', exc)
            output = exc.output
            outcome = ResultOutcome.ERROR

        failures = self._extract_failures(output.stdout or '')
        if failures and outcome == ResultOutcome.PASS:
            outcome = ResultOutcome.FAIL

        report_filepath = _save_report(invocation, report, report_timestamp, append=True)
        log_paths = [
            report_filepath.relative_to(invocation.phase.step.workdir),
            save_failures(invocation, invocation.check_files_path, failures),
        ]

        return outcome, log_paths


@provides_check('journal-dmesg')
class JournalDmesg(CheckPlugin[JournalDmesgCheck]):
    #
    # This plugin docstring has been reviewed and updated to follow
    # our documentation best practices. When changing it, please make
    # sure new changes are following them as well.
    #
    # https://tmt.readthedocs.io/en/stable/contribute.html#docs
    #
    """
    Check kernel messages in journal log recorded during the test.

    .. code-block:: yaml

        check:
          - how: journal-dmesg

    Check will identify patterns that signal kernel crashes and
    core dumps, and when detected, it will report as failed result.
    It is possible to define custom patterns:

    .. code-block:: yaml

        check:
          - how: journal-dmesg
            failure-pattern:
              # These are default patterns
              - 'Call Trace:
              - '\\ssegfault\\s'

              # More patterns to look for
              - '\\[Firmware Bug\\]'

    .. versionadded:: 1.28
    """

    _check_class = JournalDmesgCheck

    @classmethod
    def essential_requires(
        cls,
        guest: 'Guest',
        test: 'tmt.base.Test',
        logger: tmt.log.Logger,
    ) -> list['tmt.base.DependencySimple']:
        if not guest.facts.has_systemd:
            return []

        # Avoid circular imports
        import tmt.base

        return [tmt.base.DependencySimple('/usr/bin/journalctl')]

    @classmethod
    def before_test(
        cls,
        *,
        check: 'JournalDmesgCheck',
        invocation: 'TestInvocation',
        environment: Optional[tmt.utils.Environment] = None,
        logger: tmt.log.Logger,
    ) -> list[CheckResult]:
        if invocation.guest.facts.has_systemd:
            check._create_journalctl_mark(invocation, logger)

        return []

    @classmethod
    def after_test(
        cls,
        *,
        check: 'JournalDmesgCheck',
        invocation: 'TestInvocation',
        environment: Optional[tmt.utils.Environment] = None,
        logger: tmt.log.Logger,
    ) -> list[CheckResult]:
        if not invocation.guest.facts.has_systemd:
            return [CheckResult(name='journal-dmesg', result=ResultOutcome.SKIP)]

        if not invocation.is_guest_healthy:
            return [CheckResult(name='journal-dmesg', result=ResultOutcome.SKIP)]

        outcome, paths = check._save_journal_dmesg(invocation, logger)
        return [CheckResult(name='journal-dmesg', result=outcome, log=paths)]
