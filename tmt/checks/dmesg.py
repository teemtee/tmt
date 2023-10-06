import datetime
import re
from typing import TYPE_CHECKING, Optional

import tmt.log
import tmt.steps.execute
import tmt.steps.provision
import tmt.utils
from tmt.checks import Check, CheckEvent, CheckPlugin, provides_check
from tmt.result import CheckResult, ResultOutcome
from tmt.steps.provision import GuestCapability
from tmt.utils import Path, render_run_exception_streams

if TYPE_CHECKING:
    import tmt.base
    from tmt.steps.execute import TestInvocation
    from tmt.steps.provision import Guest

TEST_POST_DMESG_FILENAME = 'dmesg-{event}.txt'
FAILURE_PATTERNS = [
    re.compile(pattern)
    for pattern in [
        r'Call Trace:',
        r'\ssegfault\s',
        ]
    ]


@provides_check('dmesg')
class DmesgCheck(CheckPlugin[Check]):
    """
    Save the content of kernel ring buffer (aka "console") into a file.

    The check saves one file before the test, and then again
    when test finishes.

    .. code-block:: yaml

        check:
          - name: dmesg

    .. versionadded:: 1.28
    """

    _check_class = Check

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

    @classmethod
    def _save_dmesg(
            cls,
            invocation: 'TestInvocation',
            event: CheckEvent,
            logger: tmt.log.Logger) -> tuple[ResultOutcome, Path]:

        from tmt.steps.execute import ExecutePlugin

        assert invocation.phase.step.workdir is not None  # narrow type

        timestamp = ExecutePlugin.format_timestamp(datetime.datetime.now(datetime.timezone.utc))

        path = invocation.check_files_path / TEST_POST_DMESG_FILENAME.format(event=event.value)

        try:
            dmesg_output = cls._fetch_dmesg(invocation.guest, logger)

        except tmt.utils.RunError as exc:
            outcome = ResultOutcome.ERROR
            output = "\n".join(render_run_exception_streams(exc.stdout, exc.stderr, verbose=1))

        else:
            outcome = ResultOutcome.PASS
            output = dmesg_output.stdout or ''
            if any(pattern.search(output) for pattern in FAILURE_PATTERNS):
                outcome = ResultOutcome.FAIL

        invocation.phase.write(
            path,
            f'# Acquired at {timestamp}\n{output}')

        return outcome, path.relative_to(invocation.phase.step.workdir)

    @classmethod
    def before_test(
            cls,
            *,
            check: 'Check',
            invocation: 'TestInvocation',
            environment: Optional[tmt.utils.Environment] = None,
            logger: tmt.log.Logger) -> list[CheckResult]:
        if not invocation.guest.facts.has_capability(GuestCapability.SYSLOG_ACTION_READ_ALL):
            return [CheckResult(name='dmesg', result=ResultOutcome.SKIP)]

        outcome, path = cls._save_dmesg(invocation, CheckEvent.BEFORE_TEST, logger)

        return [CheckResult(name='dmesg', result=outcome, log=[path])]

    @classmethod
    def after_test(
            cls,
            *,
            check: 'Check',
            invocation: 'TestInvocation',
            environment: Optional[tmt.utils.Environment] = None,
            logger: tmt.log.Logger) -> list[CheckResult]:
        if not invocation.guest.facts.has_capability(GuestCapability.SYSLOG_ACTION_READ_ALL):
            return [CheckResult(name='dmesg', result=ResultOutcome.SKIP)]

        if invocation.hard_reboot_requested:
            return [CheckResult(name='dmesg', result=ResultOutcome.SKIP)]

        outcome, path = cls._save_dmesg(invocation, CheckEvent.AFTER_TEST, logger)

        return [CheckResult(name='dmesg', result=outcome, log=[path])]
