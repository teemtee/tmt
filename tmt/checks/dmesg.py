import datetime
from typing import TYPE_CHECKING, Optional

import tmt.log
import tmt.steps.execute
import tmt.steps.provision
import tmt.utils
from tmt.checks import Check, CheckEvent, CheckPlugin, provides_check
from tmt.result import CheckResult, ResultOutcome
from tmt.utils import Path, render_run_exception_streams

if TYPE_CHECKING:
    from tmt.steps.execute import TestInvocation

TEST_POST_DMESG_FILENAME = 'tmt-dmesg-{event}.txt'


@provides_check('dmesg')
class DmesgCheck(CheckPlugin):
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

        return guest.execute(tmt.utils.ShellScript('dmesg'), log=_test_output_logger)

    @classmethod
    def _save_dmesg(
            cls,
            invocation: 'TestInvocation',
            event: CheckEvent,
            logger: tmt.log.Logger) -> tuple[ResultOutcome, Path]:

        from tmt.steps.execute import ExecutePlugin

        assert invocation.phase.step.workdir is not None  # narrow type

        timestamp = ExecutePlugin.format_timestamp(datetime.datetime.now(datetime.timezone.utc))

        path = invocation.data_path(
            filename=TEST_POST_DMESG_FILENAME.format(event=event.value),
            create=True,
            full=True)

        try:
            dmesg_output = cls._fetch_dmesg(invocation.guest, logger)

        except tmt.utils.RunError as exc:
            outcome = ResultOutcome.ERROR
            output = "\n".join(render_run_exception_streams(exc.stdout, exc.stderr, verbose=1))

        else:
            outcome = ResultOutcome.PASS
            output = dmesg_output.stdout or ''

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
            environment: Optional[tmt.utils.EnvironmentType] = None,
            logger: tmt.log.Logger) -> list[CheckResult]:
        outcome, path = cls._save_dmesg(invocation, CheckEvent.BEFORE_TEST, logger)

        return [CheckResult(name='dmesg', result=outcome, log=[path])]

    @classmethod
    def after_test(
            cls,
            *,
            check: 'Check',
            invocation: 'TestInvocation',
            environment: Optional[tmt.utils.EnvironmentType] = None,
            logger: tmt.log.Logger) -> list[CheckResult]:
        outcome, path = cls._save_dmesg(invocation, CheckEvent.AFTER_TEST, logger)

        return [CheckResult(name='dmesg', result=outcome, log=[path])]
