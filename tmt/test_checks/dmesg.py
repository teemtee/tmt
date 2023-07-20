import datetime
from typing import TYPE_CHECKING, List, Optional

import tmt.log
import tmt.steps.execute
import tmt.steps.provision
import tmt.utils
from tmt.result import TestCheckResult
from tmt.test_checks import TestCheckPlugin
from tmt.utils import Path

if TYPE_CHECKING:
    from tmt.base import TestCheck


TEST_POST_DMESG_FILENAME = 'tmt-dmesg.txt'


@TestCheckPlugin.provides_check('dmesg')
class DmesgTestCheck(TestCheckPlugin):
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
            logger: tmt.log.Logger) -> Path:

        from tmt.steps.execute import ExecutePlugin

        assert plugin.step.workdir is not None  # narrow type

        timestamp = ExecutePlugin.format_timestamp(datetime.datetime.now(datetime.timezone.utc))

        dmesg_output = cls._fetch_dmesg(guest, logger)

        path = plugin.data_path(
            test,
            guest,
            filename=TEST_POST_DMESG_FILENAME,
            create=True,
            full=True)

        plugin.write(
            path,
            f'# Acquired at {timestamp}\n{dmesg_output.stdout or ""}')

        return path.relative_to(plugin.step.workdir)

    @classmethod
    def before_test(
            cls,
            *,
            check: 'TestCheck',
            plugin: tmt.steps.execute.ExecutePlugin,
            guest: tmt.steps.provision.Guest,
            test: 'tmt.base.Test',
            environment: Optional[tmt.utils.EnvironmentType] = None,
            logger: tmt.log.Logger) -> List[TestCheckResult]:
        return [
            TestCheckResult(
                name='dmesg',
                log=[
                    cls._save_dmesg(plugin, guest, test, logger)
                    ]
                )
            ]

    @classmethod
    def after_test(
            cls,
            *,
            check: 'TestCheck',
            plugin: tmt.steps.execute.ExecutePlugin,
            guest: tmt.steps.provision.Guest,
            test: 'tmt.base.Test',
            environment: Optional[tmt.utils.EnvironmentType] = None,
            logger: tmt.log.Logger) -> List[TestCheckResult]:
        return [
            TestCheckResult(
                name='dmesg',
                log=[
                    cls._save_dmesg(plugin, guest, test, logger)
                    ]
                )
            ]
