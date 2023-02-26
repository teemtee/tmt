import re
from typing import TYPE_CHECKING, List, Optional

import tmt.base
import tmt.log
import tmt.result
import tmt.steps.execute
import tmt.utils
from tmt.frameworks import TestFramework, provides_framework
from tmt.result import ResultOutcome
from tmt.utils import Path

if TYPE_CHECKING:
    from tmt.base import Test
    from tmt.steps.execute import ExecutePlugin
    from tmt.steps.provision import Guest


@provides_framework('beakerlib')
class Beakerlib(TestFramework):
    @classmethod
    def get_environment_variables(
            cls,
            parent: 'ExecutePlugin',
            test: 'Test',
            guest: 'Guest',
            logger: tmt.log.Logger) -> tmt.utils.EnvironmentType:

        return {
            'BEAKERLIB_DIR': str(parent.data_path(test, guest, full=True)),
            'BEAKERLIB_COMMAND_SUBMIT_LOG': f'bash {tmt.steps.execute.TMT_FILE_SUBMIT_SCRIPT.path}'
            }

    @classmethod
    def get_pull_options(
            cls,
            parent: 'ExecutePlugin',
            test: 'Test',
            guest: 'Guest',
            logger: tmt.log.Logger) -> List[str]:
        return [
            '--exclude',
            str(parent.data_path(test, guest, "backup*", full=True))
            ]

    @classmethod
    def extract_results(
            cls,
            parent: 'ExecutePlugin',
            test: 'Test',
            guest: 'Guest',
            logger: tmt.log.Logger) -> List[tmt.result.Result]:
        """ Check result of a beakerlib test """
        # Initialize data, prepare log paths
        note: Optional[str] = None
        log: List[Path] = []
        for filename in [tmt.steps.execute.TEST_OUTPUT_FILENAME, 'journal.txt']:
            if parent.data_path(test, guest, filename, full=True).is_file():
                log.append(parent.data_path(test, guest, filename))

        # Check beakerlib log for the result
        try:
            beakerlib_results_file = parent.data_path(test, guest, 'TestResults', full=True)
            results = parent.read(beakerlib_results_file, level=3)
        except tmt.utils.FileError:
            logger.debug(f"Unable to read '{beakerlib_results_file}'.", level=3)
            note = 'beakerlib: TestResults FileError'

            return [tmt.Result.from_test(
                test=test,
                result=ResultOutcome.ERROR,
                note=note,
                log=log,
                guest=guest)]

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
                f"No '{missing_piece}' found in '{beakerlib_results_file}'{hint}.",
                level=3)
            note = 'beakerlib: Result/State missing'
            return [tmt.Result.from_test(
                test=test,
                result=ResultOutcome.ERROR,
                note=note,
                log=log,
                guest=guest)]

        result = search_result.group(1)
        state = search_state.group(1)

        # Check if it was killed by timeout (set by tmt executor)
        actual_result = ResultOutcome.ERROR
        if test.returncode == tmt.utils.PROCESS_TIMEOUT:
            note = 'timeout'
            parent.timeout_hint(test, guest)
        # Test results should be in complete state
        elif state != 'complete':
            note = f"beakerlib: State '{state}'"
        # Finally we have a valid result
        else:
            actual_result = ResultOutcome.from_spec(result.lower())
        return [tmt.Result.from_test(
            test=test,
            result=actual_result,
            note=note,
            log=log,
            guest=guest)]
