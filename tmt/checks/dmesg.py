import datetime
from typing import List, Optional, Tuple

import tmt.log
import tmt.steps.execute
import tmt.steps.provision
import tmt.utils
from tmt.checks import Check, CheckEvent, CheckPlugin, provides_check
from tmt.result import CheckResult, ResultOutcome
from tmt.utils import Path, render_run_exception_streams

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
            plugin: tmt.steps.execute.ExecutePlugin,
            guest: tmt.steps.provision.Guest,
            test: 'tmt.base.Test',
            event: CheckEvent,
            logger: tmt.log.Logger) -> Tuple[ResultOutcome, Path]:

        from tmt.steps.execute import ExecutePlugin

        assert plugin.step.workdir is not None  # narrow type

        timestamp = ExecutePlugin.format_timestamp(datetime.datetime.now(datetime.timezone.utc))

        path = plugin.data_path(
            test,
            guest,
            filename=TEST_POST_DMESG_FILENAME.format(event=event.value),
            create=True,
            full=True)

        try:
            dmesg_output = cls._fetch_dmesg(guest, logger)

        except tmt.utils.RunError as exc:
            outcome = ResultOutcome.ERROR
            output = "\n".join(render_run_exception_streams(exc.stdout, exc.stderr, verbose=1))

        else:
            outcome = ResultOutcome.PASS
            output = dmesg_output.stdout or ''

        plugin.write(
            path,
            f'# Acquired at {timestamp}\n{output}')

        return outcome, path.relative_to(plugin.step.workdir)

    @classmethod
    def before_test(
            cls,
            *,
            check: 'Check',
            plugin: tmt.steps.execute.ExecutePlugin,
            guest: tmt.steps.provision.Guest,
            test: 'tmt.base.Test',
            environment: Optional[tmt.utils.EnvironmentType] = None,
            logger: tmt.log.Logger) -> List[CheckResult]:
        outcome, path = cls._save_dmesg(plugin, guest, test, CheckEvent.BEFORE_TEST, logger)

        return [CheckResult(name='dmesg', result=outcome, log=[path])]

    @classmethod
    def after_test(
            cls,
            *,
            check: 'Check',
            plugin: tmt.steps.execute.ExecutePlugin,
            guest: tmt.steps.provision.Guest,
            test: 'tmt.base.Test',
            environment: Optional[tmt.utils.EnvironmentType] = None,
            logger: tmt.log.Logger) -> List[CheckResult]:
        outcome, path = cls._save_dmesg(plugin, guest, test, CheckEvent.AFTER_TEST, logger)

        return [CheckResult(name='dmesg', result=outcome, log=[path])]
