from unittest.mock import MagicMock

import pytest

from tmt.cli import TmtExitCode
from tmt.result import ResultOutcome, results_to_exit_code


@pytest.mark.parametrize(
    ('outcomes', 'expected_exit_code'),
    [
        # No test results found.
        (
            [],
            TmtExitCode.NO_RESULTS_FOUND
            ),
        # Errors occured during test execution.
        (
            [
                ResultOutcome.PASS,
                ResultOutcome.FAIL,
                ResultOutcome.INFO,
                ResultOutcome.SKIP,
                ResultOutcome.WARN,
                ResultOutcome.ERROR
                ],
            TmtExitCode.ERROR
            ),
        # There was a fail or warn identified, but no error.
        (
            [
                ResultOutcome.PASS,
                ResultOutcome.FAIL,
                ResultOutcome.INFO,
                ResultOutcome.SKIP,
                ResultOutcome.WARN,
                ],
            TmtExitCode.FAIL
            ),
        # Tests were executed, and all reported the ``skip`` result.
        (
            [
                ResultOutcome.SKIP,
                ResultOutcome.SKIP,
                ],
            TmtExitCode.ALL_TESTS_SKIPPED
            ),
        # At least one test passed, there was no fail, warn or error.
        (
            [
                ResultOutcome.PASS,
                ResultOutcome.INFO,
                ResultOutcome.SKIP,
                ],
            TmtExitCode.SUCCESS
            ),
        # An info is treated as a pass.
        (
            [
                ResultOutcome.INFO,
                ResultOutcome.SKIP,
                ],
            TmtExitCode.SUCCESS
            )
        ],
    # IDs copied from the specification:
    ids=(
        "No test results found",
        "Errors occured during test execution",
        "There was a fail or warn identified, but no error",
        "Tests were executed, and all reported the ``skip`` result",
        "At least one test passed, there was no fail, warn or error",
        "An info is treated as a pass"
        )
    )
def test_result_to_exit_code(outcomes: list[ResultOutcome], expected_exit_code: int) -> None:
    assert results_to_exit_code([MagicMock(result=outcome) for outcome in outcomes]) \
        == expected_exit_code
