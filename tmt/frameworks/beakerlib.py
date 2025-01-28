import re
from typing import TYPE_CHECKING

import tmt.base
import tmt.log
import tmt.result
import tmt.steps.execute
import tmt.utils
from tmt.frameworks import TestFramework, provides_framework
from tmt.result import ResultOutcome
from tmt.utils import Environment, EnvVarValue, GeneralError, Path

if TYPE_CHECKING:
    from tmt.base import DependencySimple, Test
    from tmt.steps.execute import TestInvocation


BEAKERLIB_REPORT_RESULT_COMMAND = 'rhts-report-result'


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

        # The beakerlib calls the command in this variable in the following way:
        # $BEAKERLIB_COMMAND_REPORT_RESULT "$testname" "$result" "$logfile" "$score"
        # - https://github.com/beakerlib/beakerlib/blob/5a85937f557b735f32996eb55cd6b9a33f3fe653/src/testing.sh#L1076
        #
        # If we use the `tmt-report-result` value here, the script will not be compatible
        # with the third `$logfile` positional argument - it will just ignore it because it
        # accepts the logfile provided only by `-o/--outputFile` option be default.
        #
        # The reason the `rhts-report-result` alias is used here is a compatibility layer
        # implemented by the script itself. If the script gets called with this name, it
        # will *accept* the third positional argument as a `logfile`.
        # - https://github.com/teemtee/tmt/blob/e7cf41d1fe5a4dcbb3270758586f41313e9462ec/tmt/steps/execute/scripts/tmt-report-result#L101
        if BEAKERLIB_REPORT_RESULT_COMMAND not in [
                tmt.steps.execute.TMT_REPORT_RESULT_SCRIPT.source_filename,
                *tmt.steps.execute.TMT_REPORT_RESULT_SCRIPT.aliases]:
            raise GeneralError("Beakerlib framework requires the "
                               f"'{BEAKERLIB_REPORT_RESULT_COMMAND}' script to be available "
                               "on a guest.")

        return Environment({
            'BEAKERLIB_DIR': EnvVarValue(invocation.path),
            'BEAKERLIB_COMMAND_SUBMIT_LOG': EnvVarValue(
                invocation.guest.scripts_path /
                tmt.steps.execute.TMT_FILE_SUBMIT_SCRIPT.source_filename),

            # The command in this variable gets called with every `rlPhaseEnd` call in beakerlib.
            'BEAKERLIB_COMMAND_REPORT_RESULT': EnvVarValue(
                invocation.guest.scripts_path / BEAKERLIB_REPORT_RESULT_COMMAND),

            # This variables must be set explicitly, otherwise the beakerlib `rlPhaseEnd` macro
            # will not call the the command in `BEAKERLIB_COMMAND_REPORT_RESULT`.
            # - https://github.com/beakerlib/beakerlib/blob/cfa801fb175fef1e47b8552d6cf6efcb51df7227/src/testing.sh#L1074
            'TESTID': EnvVarValue(str(invocation.test.serial_number)),
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
            results: list[tmt.result.Result],
            logger: tmt.log.Logger) -> list[tmt.result.Result]:
        """ Check result of a beakerlib test """

        # The outcome of a main tmt result must be never modified based on subresults outcomes.
        # The main result outcome will be always set to outcome reported by a beakerlib. The
        # subresults are there just to provide more detail.
        subresults = [result.to_subresult() for result in results]

        # Initialize data, prepare log paths
        note: list[str] = []
        log: list[Path] = []
        for filename in [tmt.steps.execute.TEST_OUTPUT_FILENAME, 'journal.txt']:
            if (invocation.path / filename).is_file():
                log.append(invocation.relative_path / filename)

        # Check beakerlib log for the result
        beakerlib_results_filepath = invocation.path / 'TestResults'

        try:
            beakerlib_results = invocation.phase.read(beakerlib_results_filepath, level=3)
        except tmt.utils.FileError:
            logger.debug(f"Unable to read '{beakerlib_results_filepath}'.", level=3)
            note.append('beakerlib: TestResults FileError')

            return [tmt.Result.from_test_invocation(
                invocation=invocation,
                result=ResultOutcome.ERROR,
                note=note,
                log=log,
                subresult=subresults)]

        search_result = re.search('TESTRESULT_RESULT_STRING=(.*)', beakerlib_results)
        # States are: started, incomplete and complete
        # FIXME In quotes until beakerlib/beakerlib/pull/92 is merged
        search_state = re.search(r'TESTRESULT_STATE="?(\w+)"?', beakerlib_results)

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
            note.append('beakerlib: Result/State missing')
            return [tmt.Result.from_test_invocation(
                invocation=invocation,
                result=ResultOutcome.ERROR,
                note=note,
                log=log,
                subresult=subresults)]

        result = search_result.group(1)
        state = search_state.group(1)

        # Check if it was killed by timeout (set by tmt executor)
        actual_result = ResultOutcome.ERROR
        if invocation.return_code == tmt.utils.ProcessExitCodes.TIMEOUT:
            note.append('timeout')
            invocation.phase.timeout_hint(invocation)

        elif tmt.utils.ProcessExitCodes.is_pidfile(invocation.return_code):
            note.append('pidfile locking')

        # Test results should be in complete state
        elif state != 'complete':
            note.append(f"beakerlib: State '{state}'")
        # Finally we have a valid result
        else:
            actual_result = ResultOutcome.from_spec(result.lower())

        return [tmt.Result.from_test_invocation(
            invocation=invocation,
            result=actual_result,
            note=note,
            log=log,
            subresult=subresults)]
