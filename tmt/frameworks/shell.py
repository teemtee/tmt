from typing import TYPE_CHECKING, List

import tmt.base
import tmt.log
import tmt.result
import tmt.steps.execute
import tmt.utils
from tmt.frameworks import TestFramework, provides_framework
from tmt.result import ResultOutcome

if TYPE_CHECKING:
    from tmt.base import Test
    from tmt.steps.execute import ExecutePlugin, ExecuteStepDataT
    from tmt.steps.provision import Guest


@provides_framework('shell')
class Shell(TestFramework):
    @classmethod
    def get_test_command(
            cls,
            parent: 'ExecutePlugin[ExecuteStepDataT]',
            test: 'Test',
            guest: 'Guest',
            logger: tmt.log.Logger) -> tmt.utils.ShellScript:

        # Use default options for shell tests
        return tmt.utils.ShellScript(f"{tmt.utils.SHELL_OPTIONS}; {test.test}")

    @classmethod
    def extract_results(
            cls,
            parent: 'ExecutePlugin[ExecuteStepDataT]',
            test: 'Test',
            guest: 'Guest',
            logger: tmt.log.Logger) -> List[tmt.result.Result]:
        """ Check result of a shell test """
        assert test.return_code is not None
        note = None

        try:
            # Process the exit code and prepare the log path
            result = {0: ResultOutcome.PASS, 1: ResultOutcome.FAIL}[test.return_code]
        except KeyError:
            result = ResultOutcome.ERROR
            # Add note about the exceeded duration
            if test.return_code == tmt.utils.ProcessExitCodes.TIMEOUT:
                note = 'timeout'
                parent.timeout_hint(test, guest)

            elif tmt.utils.ProcessExitCodes.is_pidfile(test.return_code):
                note = 'pidfile locking'

        return [tmt.Result.from_test(
            test=test,
            result=result,
            log=[parent.data_path(test, guest, tmt.steps.execute.TEST_OUTPUT_FILENAME)],
            note=note,
            guest=guest)]
