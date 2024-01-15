import re
from typing import TYPE_CHECKING, Optional

import tmt.base
import tmt.log
import tmt.result
import tmt.steps.execute
import tmt.utils
from tmt.frameworks import TestFramework, provides_framework
from tmt.result import ResultOutcome
from tmt.utils import Environment, EnvVarValue, Path

if TYPE_CHECKING:
    from tmt.base import DependencySimple, Test
    from tmt.steps.execute import TestInvocation


@provides_framework('beakerlib')
class Beakerlib(TestFramework):
    @classmethod
    def get_requirements(
            cls,
            test: 'Test',
            logger: tmt.log.Logger) -> list['DependencySimple']:
        # Avoiding circular imports: `Test.test_framework` requires `tmt.frameworks`.
        from tmt.base import DependencySimple

        return [DependencySimple('beakerlib')]

    @classmethod
    def get_environment_variables(
            cls,
            invocation: 'TestInvocation',
            logger: tmt.log.Logger) -> tmt.utils.Environment:

        return Environment({
            'BEAKERLIB_DIR': EnvVarValue(invocation.path),
            'BEAKERLIB_COMMAND_SUBMIT_LOG': EnvVarValue(
                f'bash {tmt.steps.execute.TMT_FILE_SUBMIT_SCRIPT.path}')
            })

    @classmethod
    def get_pull_options(
            cls,
            invocation: 'TestInvocation',
            logger: tmt.log.Logger) -> list[str]:
        return [
            '--exclude',
            str(invocation.path / "backup*")
            ]

    @classmethod
    def extract_results(
            cls,
            invocation: 'TestInvocation',
            logger: tmt.log.Logger) -> list[tmt.result.Result]:
        """ Check result of a beakerlib test """
        # Initialize data, prepare log paths
        note: Optional[str] = None
        log: list[Path] = []
        for filename in [tmt.steps.execute.TEST_OUTPUT_FILENAME, 'journal.txt']:
            if (invocation.path / filename).is_file():
                log.append(invocation.relative_path / filename)

        # Check beakerlib log for the result
        beakerlib_results_filepath = invocation.path / 'TestResults'

        try:
            results = invocation.phase.read(beakerlib_results_filepath, level=3)
        except tmt.utils.FileError:
            logger.debug(f"Unable to read '{beakerlib_results_filepath}'.", level=3)
            note = 'beakerlib: TestResults FileError'

            return [tmt.Result.from_test_invocation(
                invocation=invocation,
                result=ResultOutcome.ERROR,
                note=note,
                log=log)]

        search_result = re.search('TESTRESULT_RESULT_STRING=(.*)', results)
        # States are: started, incomplete and complete
        # FIXME In quotes until beakerlib/beakerlib/pull/92 is merged
        search_state = re.search(r'TESTRESULT_STATE="?(\w+)"?', results)

        if search_result is None or search_state is None:
            # Same outcome but make it easier to debug
            if search_result is None:
                missing_piece = 'TESTRESULT_RESULT_STRING='
                hint = ''
            else:
                missing_piece = 'TESTRESULT_STATE='
                hint = ', possibly outdated beakerlib (requires 1.23+)'
            logger.debug(
                f"No '{missing_piece}' found in '{beakerlib_results_filepath}'{hint}.",
                level=3)
            note = 'beakerlib: Result/State missing'
            return [tmt.Result.from_test_invocation(
                invocation=invocation,
                result=ResultOutcome.ERROR,
                note=note,
                log=log)]

        result = search_result.group(1)
        state = search_state.group(1)

        # Check if it was killed by timeout (set by tmt executor)
        actual_result = ResultOutcome.ERROR
        if invocation.return_code == tmt.utils.ProcessExitCodes.TIMEOUT:
            note = 'timeout'
            invocation.phase.timeout_hint(invocation)

        elif tmt.utils.ProcessExitCodes.is_pidfile(invocation.return_code):
            note = 'pidfile locking'

        # Test results should be in complete state
        elif state != 'complete':
            note = f"beakerlib: State '{state}'"
        # Finally we have a valid result
        else:
            actual_result = ResultOutcome.from_spec(result.lower())
        return [tmt.Result.from_test_invocation(
            invocation=invocation,
            result=actual_result,
            note=note,
            log=log)]
