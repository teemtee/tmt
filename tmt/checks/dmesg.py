import dataclasses
import datetime
import re
from re import Pattern
from typing import TYPE_CHECKING, Optional

import tmt.log
import tmt.steps.execute
import tmt.steps.provision
import tmt.utils
from tmt.checks import Check, CheckEvent, CheckPlugin, _RawCheck, provides_check
from tmt.result import CheckResult, ResultOutcome
from tmt.steps.provision import GuestCapability
from tmt.utils import (
    Path,
    field,
    format_timestamp,
    render_command_report,
    )

if TYPE_CHECKING:
    import tmt.base
    from tmt.steps.execute import TestInvocation
    from tmt.steps.provision import Guest

TEST_POST_DMESG_FILENAME = 'dmesg-{event}.txt'

DEFAULT_FAILURE_PATTERNS = [
    re.compile(pattern)
    for pattern in [
        r'Call Trace:',
        r'\ssegfault\s',
        ]
    ]


@dataclasses.dataclass
class DmesgCheck(Check):
    failure_pattern: list[Pattern[str]] = field(
        default_factory=lambda: DEFAULT_FAILURE_PATTERNS[:],
        help="""
             List of regular expressions to look for in ``dmesg``
             output. If any of patterns is found, ``dmesg`` check will
             report ``fail`` result.
             """,
        metavar='PATTERN',
        normalize=tmt.utils.normalize_pattern_list,
        exporter=lambda patterns: [pattern.pattern for pattern in patterns],
        serialize=lambda patterns: [pattern.pattern for pattern in patterns],
        unserialize=lambda serialized: [re.compile(pattern) for pattern in serialized]
        )

    # TODO: fix `to_spec` of `Check` to support nested serializables
    def to_spec(self) -> _RawCheck:
        spec = super().to_spec()

        spec['failure-pattern'] = [  # type: ignore[reportGeneralTypeIssues,typeddict-unknown-key,unused-ignore]
            pattern.pattern for pattern in self.failure_pattern]

        return spec

    def to_minimal_spec(self) -> _RawCheck:
        return self.to_spec()

    @classmethod
    def _fetch_dmesg(
            cls,
            guest: tmt.steps.provision.Guest,
            logger: tmt.log.Logger) -> tmt.utils.CommandOutput:

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

        if guest.facts.has_capability(GuestCapability.SYSLOG_ACTION_READ_CLEAR):
            script = tmt.utils.ShellScript('dmesg -c')

        else:
            script = tmt.utils.ShellScript('dmesg')

        if not guest.facts.is_superuser:
            script = tmt.utils.ShellScript(f'sudo {script.to_shell_command()}')

        return guest.execute(script, log=_test_output_logger)

    def _save_dmesg(
            self,
            invocation: 'TestInvocation',
            event: CheckEvent,
            logger: tmt.log.Logger) -> tuple[ResultOutcome, Path]:

        assert invocation.phase.step.workdir is not None  # narrow type

        timestamp = format_timestamp(datetime.datetime.now(datetime.timezone.utc))

        path = invocation.check_files_path / TEST_POST_DMESG_FILENAME.format(event=event.value)

        try:
            output = self._fetch_dmesg(invocation.guest, logger)

        except tmt.utils.RunError as exc:
            outcome = ResultOutcome.ERROR
            output = exc.output

        else:
            outcome = ResultOutcome.PASS

            if any(pattern.search(output.stdout or '') for pattern in self.failure_pattern):
                outcome = ResultOutcome.FAIL

        invocation.phase.write(
            path,
            '\n'.join(render_command_report(label=f'Acquired at {timestamp}', output=output)),
            mode='a')

        return outcome, path.relative_to(invocation.phase.step.workdir)


@provides_check('dmesg')
class Dmesg(CheckPlugin[DmesgCheck]):
    """
    Save the content of kernel ring buffer (aka "console") into a file.

    The check saves one file before the test, and then again
    when test finishes.

    .. code-block:: yaml

        check:
          - how: dmesg

    Check will identify patterns that signal kernel crashes and
    core dumps, and when detected, it will report as failed result.
    It is possible to define custom patterns:

    .. code-block:: yaml

        check:
          - how: dmesg
            failure-pattern:
              # These are default patterns
              - 'Call Trace:
              - '\\ssegfault\\s'

              # More patterns to look for
              - '\\[Firmware Bug\\]'

    .. versionadded:: 1.28

    .. versionchanged:: 1.33
       ``failure-pattern`` has been added.
    """

    _check_class = DmesgCheck

    @classmethod
    def essential_requires(
            cls,
            guest: 'Guest',
            test: 'tmt.base.Test',
            logger: tmt.log.Logger) -> list['tmt.base.DependencySimple']:
        if not guest.facts.has_capability(GuestCapability.SYSLOG_ACTION_READ_ALL):
            return []

        # Avoid circular imports
        import tmt.base

        return [tmt.base.DependencySimple('/usr/bin/dmesg')]

    @classmethod
    def before_test(
            cls,
            *,
            check: 'DmesgCheck',
            invocation: 'TestInvocation',
            environment: Optional[tmt.utils.Environment] = None,
            logger: tmt.log.Logger) -> list[CheckResult]:
        if not invocation.guest.facts.has_capability(GuestCapability.SYSLOG_ACTION_READ_ALL):
            return [CheckResult(name='dmesg', result=ResultOutcome.SKIP)]

        outcome, path = check._save_dmesg(invocation, CheckEvent.BEFORE_TEST, logger)

        return [CheckResult(name='dmesg', result=outcome, log=[path])]

    @classmethod
    def after_test(
            cls,
            *,
            check: 'DmesgCheck',
            invocation: 'TestInvocation',
            environment: Optional[tmt.utils.Environment] = None,
            logger: tmt.log.Logger) -> list[CheckResult]:
        if not invocation.guest.facts.has_capability(GuestCapability.SYSLOG_ACTION_READ_ALL):
            return [CheckResult(name='dmesg', result=ResultOutcome.SKIP)]

        if not invocation.is_guest_healthy:
            return [CheckResult(name='dmesg', result=ResultOutcome.SKIP)]

        outcome, path = check._save_dmesg(invocation, CheckEvent.AFTER_TEST, logger)

        return [CheckResult(name='dmesg', result=outcome, log=[path])]
