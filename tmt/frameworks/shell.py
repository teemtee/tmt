import re
from typing import Optional

import tmt.log
import tmt.result
import tmt.steps.execute
import tmt.utils
from tmt.frameworks import TestFramework, provides_framework
from tmt.result import ResultOutcome, save_failures
from tmt.steps.execute import TEST_OUTPUT_FILENAME, TestInvocation
from tmt.utils import Path


def _extract_failures(invocation: 'TestInvocation', log_path: Path) -> list[str]:
    try:
        log = invocation.phase.step.plan.execute.read(log_path)
    except tmt.utils.FileError:
        return []

    return re.findall(r'.*\b(?:error|fail)\b.*', log, re.IGNORECASE | re.MULTILINE)


@provides_framework('shell')
class Shell(TestFramework):
    @classmethod
    def get_test_command(
        cls, invocation: 'TestInvocation', logger: tmt.log.Logger
    ) -> tmt.utils.ShellScript:
        # Use default options for shell tests
        return tmt.utils.ShellScript(f"{tmt.utils.SHELL_OPTIONS}; {invocation.test.test}")

    @classmethod
    def _process_results_reduce(
        cls,
        invocation: TestInvocation,
        results: list['tmt.result.RawResult'],
        logger: tmt.log.Logger,
    ) -> list['tmt.result.Result']:
        """
        Reduce given results to one outcome.

        This is the default behavior applied to given test results: all results will be reduced to
        the worst outcome possible.

        Also, convert the ``results`` into the :py:class:`SubResult` instances, and return them as
        part of returned :py:class:`Result` instance.

        :param invocation: test invocation to which the results belong to.
        :param results: results to reduce and save as tmt subresults.
        :returns: list of results.
        """

        # The worst result outcome we can find among loaded results...
        original_outcome: Optional[ResultOutcome] = None
        # ... and the actual outcome we decided is the best representing
        # the results.
        # The original one may be left unset - malformed results file,
        # for example, provides no usable original outcome.
        actual_outcome: ResultOutcome
        note: Optional[str] = None

        try:
            outcomes = [result.result for result in results]
        except tmt.utils.SpecificationError as exc:
            actual_outcome = ResultOutcome.ERROR
            note = exc.message
        else:
            hierarchy = [
                ResultOutcome.SKIP,
                ResultOutcome.PASS,
                ResultOutcome.WARN,
                ResultOutcome.FAIL,
            ]

            outcome_indices = [hierarchy.index(outcome) for outcome in outcomes]
            actual_outcome = original_outcome = hierarchy[max(outcome_indices)]

        # Find a usable log - the first one matching our "interim" outcome.
        # We cannot use the "actual" outcome, because that one may not even
        # exist in the results file - tmt might have conjured it based on
        # provided results, or set it to "error" because of errors. Only
        # the "interim" is guaranteed to be found among the results.
        test_logs = [invocation.relative_path / TEST_OUTPUT_FILENAME]

        if original_outcome is not None:
            for result in results:
                if result.result != original_outcome.value:
                    continue

                if result.log:
                    test_logs.append(invocation.relative_test_data_path / result.log[0])

                break

        failures: list[str] = []
        for test_log in test_logs:
            failures += _extract_failures(invocation, test_log)

        # Save failures to the file
        test_logs.append(save_failures(invocation, invocation.test_data_path, failures))

        return [
            tmt.Result.from_test_invocation(
                invocation=invocation,
                result=actual_outcome,
                log=test_logs,
                note=[note] if note else [],
                subresult=[result.to_subresult() for result in results],
            )
        ]

    @classmethod
    def extract_results(
        cls,
        invocation: 'TestInvocation',
        results: list[tmt.result.Result],
        logger: tmt.log.Logger,
    ) -> list[tmt.result.Result]:
        """
        Check result of a shell test.

        If there are no extra results (e.g. extracted from the tmt-report-results.yaml), continue
        normally - set the main result outcome according to test exit status.

        Otherwise, process given results, reduce their outcomes into a single one and set these
        results as tmt subresults.

        :param invocation: test invocation to which the results belong to.
        :param results: results to reduce and save as tmt subresults.
        :returns: list of results.
        """
        assert invocation.return_code is not None
        note: list[str] = []

        # Handle the `tmt-report-result` command results as a single test with assigned tmt
        # subresults.
        if results:
            return cls._process_results_reduce(invocation, results, logger)

        # If no extra results were passed (e.g. `tmt-report-result` was not called during the
        # test), just process the exit code of a shell test and return the result.
        try:
            # Process the exit code and prepare the log path
            result = {0: ResultOutcome.PASS, 1: ResultOutcome.FAIL}[invocation.return_code]
        except KeyError:
            result = ResultOutcome.ERROR
            if invocation.return_code == tmt.utils.ProcessExitCodes.TIMEOUT:
                invocation.phase.timeout_hint(invocation)

        log_path = invocation.relative_path / tmt.steps.execute.TEST_OUTPUT_FILENAME
        paths = [
            log_path,
            save_failures(invocation, invocation.path, _extract_failures(invocation, log_path)),
        ]

        return [
            tmt.Result.from_test_invocation(
                invocation=invocation,
                result=result,
                log=paths,
                note=note,
            )
        ]
