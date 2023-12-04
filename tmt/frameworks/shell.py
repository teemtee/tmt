from typing import TYPE_CHECKING

import tmt.base
import tmt.log
import tmt.result
import tmt.steps.execute
import tmt.utils
from tmt.frameworks import TestFramework, provides_framework
from tmt.result import ResultOutcome

if TYPE_CHECKING:
    from tmt.steps.execute import TestInvocation


@provides_framework('shell')
class Shell(TestFramework):
    @classmethod
    def get_test_command(
            cls,
            invocation: 'TestInvocation',
            logger: tmt.log.Logger) -> tmt.utils.ShellScript:

        # Use default options for shell tests
        return tmt.utils.ShellScript(f"{tmt.utils.SHELL_OPTIONS}; {invocation.test.test}")

    @classmethod
    def extract_results(
            cls,
            invocation: 'TestInvocation',
            logger: tmt.log.Logger) -> list[tmt.result.Result]:
        """ Check result of a shell test """
        assert invocation.return_code is not None
        note = None

        try:
            # Process the exit code and prepare the log path
            result = {0: ResultOutcome.PASS, 1: ResultOutcome.FAIL}[invocation.return_code]
        except KeyError:
            result = ResultOutcome.ERROR
            # Add note about the exceeded duration
            if invocation.return_code == tmt.utils.ProcessExitCodes.TIMEOUT:
                note = 'timeout'
                invocation.phase.timeout_hint(invocation)

            elif tmt.utils.ProcessExitCodes.is_pidfile(invocation.return_code):
                note = 'pidfile locking'

        return [tmt.Result.from_test_invocation(
            invocation=invocation,
            result=result,
            log=[invocation.relative_path / tmt.steps.execute.TEST_OUTPUT_FILENAME],
            note=note)]
