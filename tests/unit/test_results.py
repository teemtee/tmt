from unittest.mock import MagicMock

import pytest

import tmt.utils
from tmt.checks import CheckEvent
from tmt.cli import TmtExitCode
from tmt.container import container
from tmt.result import (
    CheckResult,
    CheckResultInterpret,
    Result,
    ResultInterpret,
    ResultOutcome,
    results_to_exit_code,
)
from tmt.utils import Common, Path


@container
class CheckPhasesCase:
    result_outcome: ResultOutcome
    result_interpret: ResultInterpret
    check_outcome: ResultOutcome
    check_interpret: CheckResultInterpret
    overall_outcome: ResultOutcome
    note_contains: list[str]


@container
class CheckPhasesDuplicateCase:
    result_outcome: ResultOutcome
    result_interpret: ResultInterpret
    check_outcome1: ResultOutcome
    check_outcome2: ResultOutcome
    check_interpret: CheckResultInterpret
    overall_outcome: ResultOutcome
    note_contains: list[str]


@pytest.mark.parametrize(
    ('outcomes', 'expected_exit_code'),
    [
        # No test results found.
        ([], TmtExitCode.NO_RESULTS_FOUND),
        # Errors occurred during test execution.
        (
            [
                ResultOutcome.PASS,
                ResultOutcome.FAIL,
                ResultOutcome.INFO,
                ResultOutcome.SKIP,
                ResultOutcome.WARN,
                ResultOutcome.ERROR,
                ResultOutcome.PENDING,
            ],
            TmtExitCode.ERROR,
        ),
        # There was a fail or warn identified, but no error.
        (
            [
                ResultOutcome.PASS,
                ResultOutcome.FAIL,
                ResultOutcome.INFO,
                ResultOutcome.SKIP,
                ResultOutcome.WARN,
                ResultOutcome.PENDING,
            ],
            TmtExitCode.FAIL,
        ),
        # Tests were executed, and all reported the ``skip`` result.
        (
            [
                ResultOutcome.SKIP,
                ResultOutcome.SKIP,
            ],
            TmtExitCode.ALL_TESTS_SKIPPED,
        ),
        # At least one test passed, there was no fail, warn or error.
        (
            [
                ResultOutcome.PASS,
                ResultOutcome.INFO,
                ResultOutcome.SKIP,
            ],
            TmtExitCode.SUCCESS,
        ),
        # An info is treated as a pass.
        (
            [
                ResultOutcome.INFO,
                ResultOutcome.SKIP,
            ],
            TmtExitCode.SUCCESS,
        ),
        # A pending without any fail or error is treated as an error.
        (
            [
                ResultOutcome.PASS,
                ResultOutcome.PENDING,
            ],
            TmtExitCode.ERROR,
        ),
    ],
    # IDs copied from the specification:
    ids=(
        "No test results found",
        "Errors occurred during test execution",
        "There was a fail or warn identified, but no error",
        "Tests were executed, and all reported the ``skip`` result",
        "At least one test passed, there was no fail, warn or error",
        "An info is treated as a pass",
        "A pending without any fail or error is treated as an error",
    ),
)
def test_result_to_exit_code(outcomes: list[ResultOutcome], expected_exit_code: int) -> None:
    assert (
        results_to_exit_code([MagicMock(result=outcome) for outcome in outcomes])
        == expected_exit_code
    )


@pytest.mark.parametrize(
    ("checks", "expected_check_results"),
    [
        pytest.param(
            [
                CheckResult(
                    name="check1", result=ResultOutcome.FAIL, event=CheckEvent.BEFORE_TEST
                ),
                CheckResult(name="check1", result=ResultOutcome.PASS, event=CheckEvent.AFTER_TEST),
                CheckResult(
                    name="check2", result=ResultOutcome.PASS, event=CheckEvent.BEFORE_TEST
                ),
            ],
            [ResultOutcome.FAIL, ResultOutcome.PASS, ResultOutcome.PASS],
            id="fail-before",
        ),
        pytest.param(
            [
                CheckResult(
                    name="check1", result=ResultOutcome.PASS, event=CheckEvent.BEFORE_TEST
                ),
                CheckResult(name="check1", result=ResultOutcome.FAIL, event=CheckEvent.AFTER_TEST),
                CheckResult(
                    name="check2", result=ResultOutcome.PASS, event=CheckEvent.BEFORE_TEST
                ),
            ],
            [ResultOutcome.PASS, ResultOutcome.FAIL, ResultOutcome.PASS],
            id="fail-after",
        ),
        pytest.param(
            [
                CheckResult(
                    name="check1", result=ResultOutcome.FAIL, event=CheckEvent.BEFORE_TEST
                ),
                CheckResult(name="check1", result=ResultOutcome.FAIL, event=CheckEvent.AFTER_TEST),
                CheckResult(
                    name="check2", result=ResultOutcome.PASS, event=CheckEvent.BEFORE_TEST
                ),
            ],
            [ResultOutcome.FAIL, ResultOutcome.FAIL, ResultOutcome.PASS],
            id="fail-both",
        ),
    ],
)
def test_result_interpret_check_phases(
    checks: list[CheckResult], expected_check_results: list[ResultOutcome]
) -> None:
    """
    Test the interpretation of check results with different phases
    """

    result = Result(
        name="test-case",
        check=checks,
    )

    # Test with mixed interpretations
    interpret_checks = {
        "check1": CheckResultInterpret.RESPECT,
        "check2": CheckResultInterpret.INFO,
    }

    interpreted = result.interpret_result(ResultInterpret.RESPECT, interpret_checks)
    assert interpreted.note is not None
    assert "check 'check1' failed" in interpreted.note
    assert "check 'check2' is informational" in interpreted.note

    # Verify individual check results were interpreted
    assert len(interpreted.check) == len(expected_check_results)
    for i, check in enumerate(interpreted.check):
        assert check.result == expected_check_results[i]


def test_result_interpret_edge_cases() -> None:
    """
    Test edge cases in result interpretation
    """

    # Test with no checks
    result = Result(name="test-case", result=ResultOutcome.FAIL)
    interpreted = result.interpret_result(ResultInterpret.RESPECT, {})
    assert interpreted.result == ResultOutcome.FAIL
    assert not interpreted.note

    # Test with empty check list
    result = Result(name="test-case", result=ResultOutcome.FAIL, check=[])
    interpreted = result.interpret_result(ResultInterpret.RESPECT, {})
    assert interpreted.result == ResultOutcome.FAIL
    assert not interpreted.note


@pytest.mark.parametrize(
    'case',
    [
        # Test interpret RESPECT:
        pytest.param(
            CheckPhasesCase(
                result_outcome=ResultOutcome.PASS,
                result_interpret=ResultInterpret.RESPECT,
                check_outcome=ResultOutcome.PASS,
                check_interpret=CheckResultInterpret.RESPECT,
                overall_outcome=ResultOutcome.PASS,
                note_contains=[],
            ),
            id="pass-respect-pass-respect",
        ),
        pytest.param(
            CheckPhasesCase(
                result_outcome=ResultOutcome.PASS,
                result_interpret=ResultInterpret.RESPECT,
                check_outcome=ResultOutcome.FAIL,
                check_interpret=CheckResultInterpret.RESPECT,
                overall_outcome=ResultOutcome.FAIL,
                note_contains=[
                    "check 'check1' failed",
                    "original test result: pass",
                ],
            ),
            id="pass-respect-fail-respect",
        ),
        pytest.param(
            CheckPhasesCase(
                result_outcome=ResultOutcome.FAIL,
                result_interpret=ResultInterpret.RESPECT,
                check_outcome=ResultOutcome.PASS,
                check_interpret=CheckResultInterpret.RESPECT,
                overall_outcome=ResultOutcome.FAIL,
                note_contains=[],
            ),
            id="fail-respect-pass-respect",
        ),
        pytest.param(
            CheckPhasesCase(
                result_outcome=ResultOutcome.FAIL,
                result_interpret=ResultInterpret.RESPECT,
                check_outcome=ResultOutcome.FAIL,
                check_interpret=CheckResultInterpret.RESPECT,
                overall_outcome=ResultOutcome.FAIL,
                note_contains=["check 'check1' failed"],
            ),
            id="fail-respect-fail-respect",
        ),
        pytest.param(
            CheckPhasesCase(
                result_outcome=ResultOutcome.PASS,
                result_interpret=ResultInterpret.RESPECT,
                check_outcome=ResultOutcome.WARN,
                check_interpret=CheckResultInterpret.RESPECT,
                overall_outcome=ResultOutcome.WARN,
                note_contains=["original test result: pass"],
            ),
            id="pass-respect-warn-respect",
        ),
        pytest.param(
            CheckPhasesCase(
                result_outcome=ResultOutcome.FAIL,
                result_interpret=ResultInterpret.RESPECT,
                check_outcome=ResultOutcome.WARN,
                check_interpret=CheckResultInterpret.RESPECT,
                overall_outcome=ResultOutcome.FAIL,
                note_contains=[],
            ),
            id="fail-respect-warn-respect",
        ),
        pytest.param(
            CheckPhasesCase(
                result_outcome=ResultOutcome.PASS,
                result_interpret=ResultInterpret.RESPECT,
                check_outcome=ResultOutcome.ERROR,
                check_interpret=CheckResultInterpret.RESPECT,
                overall_outcome=ResultOutcome.ERROR,
                note_contains=["original test result: pass"],
            ),
            id="pass-respect-error-respect",
        ),
        pytest.param(
            CheckPhasesCase(
                result_outcome=ResultOutcome.FAIL,
                result_interpret=ResultInterpret.RESPECT,
                check_outcome=ResultOutcome.ERROR,
                check_interpret=CheckResultInterpret.RESPECT,
                overall_outcome=ResultOutcome.ERROR,
                note_contains=["original test result: fail"],
            ),
            id="fail-respect-error-respect",
        ),
        # Test result outcome PENDING:
        pytest.param(
            CheckPhasesCase(
                result_outcome=ResultOutcome.PENDING,
                result_interpret=ResultInterpret.RESPECT,
                check_outcome=ResultOutcome.PASS,
                check_interpret=CheckResultInterpret.RESPECT,
                overall_outcome=ResultOutcome.PASS,
                note_contains=["original test result: pending"],
            ),
            id="pending-respect-pass-respect",
        ),
        pytest.param(
            CheckPhasesCase(
                result_outcome=ResultOutcome.PENDING,
                result_interpret=ResultInterpret.RESPECT,
                check_outcome=ResultOutcome.FAIL,
                check_interpret=CheckResultInterpret.RESPECT,
                overall_outcome=ResultOutcome.FAIL,
                note_contains=[
                    "check 'check1' failed",
                    "original test result: pending",
                ],
            ),
            id="pending-respect-fail-respect",
        ),
        pytest.param(
            CheckPhasesCase(
                result_outcome=ResultOutcome.PENDING,
                result_interpret=ResultInterpret.RESPECT,
                check_outcome=ResultOutcome.WARN,
                check_interpret=CheckResultInterpret.RESPECT,
                overall_outcome=ResultOutcome.WARN,
                note_contains=["original test result: pending"],
            ),
            id="pending-respect-warn-respect",
        ),
        pytest.param(
            CheckPhasesCase(
                result_outcome=ResultOutcome.PENDING,
                result_interpret=ResultInterpret.RESPECT,
                check_outcome=ResultOutcome.PENDING,
                check_interpret=CheckResultInterpret.RESPECT,
                overall_outcome=ResultOutcome.PASS,
                note_contains=["original test result: pending"],
            ),
            id="pending-respect-pending-respect",
        ),
        pytest.param(
            CheckPhasesCase(
                result_outcome=ResultOutcome.PASS,
                result_interpret=ResultInterpret.RESPECT,
                check_outcome=ResultOutcome.PASS,
                check_interpret=CheckResultInterpret.INFO,
                overall_outcome=ResultOutcome.PASS,
                note_contains=["check 'check1' is informational"],
            ),
            id="pass-respect-pass-info",
        ),
        pytest.param(
            CheckPhasesCase(
                result_outcome=ResultOutcome.PASS,
                result_interpret=ResultInterpret.RESPECT,
                check_outcome=ResultOutcome.FAIL,
                check_interpret=CheckResultInterpret.INFO,
                overall_outcome=ResultOutcome.PASS,
                note_contains=["check 'check1' is informational"],
            ),
            id="pass-respect-fail-info",
        ),
        pytest.param(
            CheckPhasesCase(
                result_outcome=ResultOutcome.PASS,
                result_interpret=ResultInterpret.RESPECT,
                check_outcome=ResultOutcome.WARN,
                check_interpret=CheckResultInterpret.INFO,
                overall_outcome=ResultOutcome.PASS,
                note_contains=["check 'check1' is informational"],
            ),
            id="pass-respect-warn-info",
        ),
        pytest.param(
            CheckPhasesCase(
                result_outcome=ResultOutcome.FAIL,
                result_interpret=ResultInterpret.RESPECT,
                check_outcome=ResultOutcome.WARN,
                check_interpret=CheckResultInterpret.INFO,
                overall_outcome=ResultOutcome.FAIL,
                note_contains=["check 'check1' is informational"],
            ),
            id="fail-respect-warn-info",
        ),
        pytest.param(
            CheckPhasesCase(
                result_outcome=ResultOutcome.PASS,
                result_interpret=ResultInterpret.RESPECT,
                check_outcome=ResultOutcome.ERROR,
                check_interpret=CheckResultInterpret.INFO,
                overall_outcome=ResultOutcome.PASS,
                note_contains=["check 'check1' is informational"],
            ),
            id="pass-respect-error-info",
        ),
        pytest.param(
            CheckPhasesCase(
                result_outcome=ResultOutcome.FAIL,
                result_interpret=ResultInterpret.RESPECT,
                check_outcome=ResultOutcome.ERROR,
                check_interpret=CheckResultInterpret.INFO,
                overall_outcome=ResultOutcome.FAIL,
                note_contains=["check 'check1' is informational"],
            ),
            id="fail-respect-error-info",
        ),
        pytest.param(
            CheckPhasesCase(
                result_outcome=ResultOutcome.PASS,
                result_interpret=ResultInterpret.RESPECT,
                check_outcome=ResultOutcome.INFO,
                check_interpret=CheckResultInterpret.RESPECT,
                overall_outcome=ResultOutcome.PASS,
                note_contains=[],
            ),
            id="pass-respect-info-respect",
        ),
        pytest.param(
            CheckPhasesCase(
                result_outcome=ResultOutcome.FAIL,
                result_interpret=ResultInterpret.RESPECT,
                check_outcome=ResultOutcome.INFO,
                check_interpret=CheckResultInterpret.RESPECT,
                overall_outcome=ResultOutcome.FAIL,
                note_contains=[],
            ),
            id="fail-respect-info-respect",
        ),
        pytest.param(
            CheckPhasesCase(
                result_outcome=ResultOutcome.PASS,
                result_interpret=ResultInterpret.RESPECT,
                check_outcome=ResultOutcome.INFO,
                check_interpret=CheckResultInterpret.INFO,
                overall_outcome=ResultOutcome.PASS,
                note_contains=["check 'check1' is informational"],
            ),
            id="pass-respect-info-info",
        ),
        pytest.param(
            CheckPhasesCase(
                result_outcome=ResultOutcome.FAIL,
                result_interpret=ResultInterpret.RESPECT,
                check_outcome=ResultOutcome.INFO,
                check_interpret=CheckResultInterpret.INFO,
                overall_outcome=ResultOutcome.FAIL,
                note_contains=["check 'check1' is informational"],
            ),
            id="fail-respect-info-info",
        ),
        pytest.param(
            CheckPhasesCase(
                result_outcome=ResultOutcome.PASS,
                result_interpret=ResultInterpret.RESPECT,
                check_outcome=ResultOutcome.INFO,
                check_interpret=CheckResultInterpret.XFAIL,
                overall_outcome=ResultOutcome.FAIL,
                note_contains=["check 'check1' did not fail as expected"],
            ),
            id="pass-respect-info-xfail",
        ),
        pytest.param(
            CheckPhasesCase(
                result_outcome=ResultOutcome.FAIL,
                result_interpret=ResultInterpret.RESPECT,
                check_outcome=ResultOutcome.INFO,
                check_interpret=CheckResultInterpret.XFAIL,
                overall_outcome=ResultOutcome.FAIL,
                note_contains=["check 'check1' did not fail as expected"],
            ),
            id="fail-respect-info-xfail",
        ),
        pytest.param(
            CheckPhasesCase(
                result_outcome=ResultOutcome.PASS,
                result_interpret=ResultInterpret.RESPECT,
                check_outcome=ResultOutcome.SKIP,
                check_interpret=CheckResultInterpret.RESPECT,
                overall_outcome=ResultOutcome.PASS,
                note_contains=[],
            ),
            id="pass-respect-skip-respect",
        ),
        pytest.param(
            CheckPhasesCase(
                result_outcome=ResultOutcome.FAIL,
                result_interpret=ResultInterpret.RESPECT,
                check_outcome=ResultOutcome.SKIP,
                check_interpret=CheckResultInterpret.RESPECT,
                overall_outcome=ResultOutcome.FAIL,
                note_contains=[],
            ),
            id="fail-respect-skip-respect",
        ),
        pytest.param(
            CheckPhasesCase(
                result_outcome=ResultOutcome.PASS,
                result_interpret=ResultInterpret.RESPECT,
                check_outcome=ResultOutcome.SKIP,
                check_interpret=CheckResultInterpret.INFO,
                overall_outcome=ResultOutcome.PASS,
                note_contains=["check 'check1' is informational"],
            ),
            id="pass-respect-skip-info",
        ),
        pytest.param(
            CheckPhasesCase(
                result_outcome=ResultOutcome.FAIL,
                result_interpret=ResultInterpret.RESPECT,
                check_outcome=ResultOutcome.SKIP,
                check_interpret=CheckResultInterpret.INFO,
                overall_outcome=ResultOutcome.FAIL,
                note_contains=["check 'check1' is informational"],
            ),
            id="fail-respect-skip-info",
        ),
        pytest.param(
            CheckPhasesCase(
                result_outcome=ResultOutcome.PASS,
                result_interpret=ResultInterpret.RESPECT,
                check_outcome=ResultOutcome.SKIP,
                check_interpret=CheckResultInterpret.XFAIL,
                overall_outcome=ResultOutcome.FAIL,
                note_contains=["check 'check1' did not fail as expected"],
            ),
            id="pass-respect-skip-xfail",
        ),
        pytest.param(
            CheckPhasesCase(
                result_outcome=ResultOutcome.FAIL,
                result_interpret=ResultInterpret.RESPECT,
                check_outcome=ResultOutcome.SKIP,
                check_interpret=CheckResultInterpret.XFAIL,
                overall_outcome=ResultOutcome.FAIL,
                note_contains=["check 'check1' did not fail as expected"],
            ),
            id="fail-respect-skip-xfail",
        ),
        pytest.param(
            CheckPhasesCase(
                result_outcome=ResultOutcome.PASS,
                result_interpret=ResultInterpret.RESPECT,
                check_outcome=ResultOutcome.PENDING,
                check_interpret=CheckResultInterpret.RESPECT,
                overall_outcome=ResultOutcome.PASS,
                note_contains=[],
            ),
            id="pass-respect-pending-respect",
        ),
        pytest.param(
            CheckPhasesCase(
                result_outcome=ResultOutcome.FAIL,
                result_interpret=ResultInterpret.RESPECT,
                check_outcome=ResultOutcome.PENDING,
                check_interpret=CheckResultInterpret.RESPECT,
                overall_outcome=ResultOutcome.FAIL,
                note_contains=[],
            ),
            id="fail-respect-pending-respect",
        ),
        pytest.param(
            CheckPhasesCase(
                result_outcome=ResultOutcome.PASS,
                result_interpret=ResultInterpret.RESPECT,
                check_outcome=ResultOutcome.PENDING,
                check_interpret=CheckResultInterpret.INFO,
                overall_outcome=ResultOutcome.PASS,
                note_contains=["check 'check1' is informational"],
            ),
            id="pass-respect-pending-info",
        ),
        pytest.param(
            CheckPhasesCase(
                result_outcome=ResultOutcome.FAIL,
                result_interpret=ResultInterpret.RESPECT,
                check_outcome=ResultOutcome.PENDING,
                check_interpret=CheckResultInterpret.INFO,
                overall_outcome=ResultOutcome.FAIL,
                note_contains=["check 'check1' is informational"],
            ),
            id="fail-respect-pending-info",
        ),
        pytest.param(
            CheckPhasesCase(
                result_outcome=ResultOutcome.PASS,
                result_interpret=ResultInterpret.RESPECT,
                check_outcome=ResultOutcome.PENDING,
                check_interpret=CheckResultInterpret.XFAIL,
                overall_outcome=ResultOutcome.FAIL,
                note_contains=["check 'check1' did not fail as expected"],
            ),
            id="pass-respect-pending-xfail",
        ),
        pytest.param(
            CheckPhasesCase(
                result_outcome=ResultOutcome.FAIL,
                result_interpret=ResultInterpret.RESPECT,
                check_outcome=ResultOutcome.PENDING,
                check_interpret=CheckResultInterpret.XFAIL,
                overall_outcome=ResultOutcome.FAIL,
                note_contains=["check 'check1' did not fail as expected"],
            ),
            id="fail-respect-pending-xfail",
        ),
        pytest.param(
            CheckPhasesCase(
                result_outcome=ResultOutcome.PASS,
                result_interpret=ResultInterpret.RESPECT,
                check_outcome=ResultOutcome.FAIL,
                check_interpret=CheckResultInterpret.XFAIL,
                overall_outcome=ResultOutcome.PASS,
                note_contains=["check 'check1' failed as expected"],
            ),
            id="pass-respect-fail-xfail",
        ),
        pytest.param(
            CheckPhasesCase(
                result_outcome=ResultOutcome.PASS,
                result_interpret=ResultInterpret.RESPECT,
                check_outcome=ResultOutcome.PASS,
                check_interpret=CheckResultInterpret.XFAIL,
                overall_outcome=ResultOutcome.FAIL,
                note_contains=[
                    "check 'check1' did not fail as expected",
                    "original test result: pass",
                ],
            ),
            id="pass-respect-pass-xfail",
        ),
        pytest.param(
            CheckPhasesCase(
                result_outcome=ResultOutcome.FAIL,
                result_interpret=ResultInterpret.RESPECT,
                check_outcome=ResultOutcome.FAIL,
                check_interpret=CheckResultInterpret.XFAIL,
                overall_outcome=ResultOutcome.FAIL,
                note_contains=["check 'check1' failed as expected"],
            ),
            id="fail-respect-fail-xfail",
        ),
        pytest.param(
            CheckPhasesCase(
                result_outcome=ResultOutcome.FAIL,
                result_interpret=ResultInterpret.RESPECT,
                check_outcome=ResultOutcome.PASS,
                check_interpret=CheckResultInterpret.XFAIL,
                overall_outcome=ResultOutcome.FAIL,
                note_contains=["check 'check1' did not fail as expected"],
            ),
            id="fail-respect-pass-xfail",
        ),
        pytest.param(
            CheckPhasesCase(
                result_outcome=ResultOutcome.PASS,
                result_interpret=ResultInterpret.RESPECT,
                check_outcome=ResultOutcome.WARN,
                check_interpret=CheckResultInterpret.XFAIL,
                overall_outcome=ResultOutcome.WARN,
                note_contains=["original test result: pass"],
            ),
            id="pass-respect-warn-xfail",
        ),
        pytest.param(
            CheckPhasesCase(
                result_outcome=ResultOutcome.FAIL,
                result_interpret=ResultInterpret.RESPECT,
                check_outcome=ResultOutcome.WARN,
                check_interpret=CheckResultInterpret.XFAIL,
                overall_outcome=ResultOutcome.FAIL,
                note_contains=[],
            ),
            id="fail-respect-warn-xfail",
        ),
        pytest.param(
            CheckPhasesCase(
                result_outcome=ResultOutcome.PASS,
                result_interpret=ResultInterpret.RESPECT,
                check_outcome=ResultOutcome.ERROR,
                check_interpret=CheckResultInterpret.XFAIL,
                overall_outcome=ResultOutcome.ERROR,
                note_contains=["original test result: pass"],
            ),
            id="pass-respect-error-xfail",
        ),
        pytest.param(
            CheckPhasesCase(
                result_outcome=ResultOutcome.FAIL,
                result_interpret=ResultInterpret.RESPECT,
                check_outcome=ResultOutcome.ERROR,
                check_interpret=CheckResultInterpret.XFAIL,
                overall_outcome=ResultOutcome.ERROR,
                note_contains=["original test result: fail"],
            ),
            id="fail-respect-error-xfail",
        ),
        # Test interpret CUSTOM:
        pytest.param(
            CheckPhasesCase(
                result_outcome=ResultOutcome.PASS,
                result_interpret=ResultInterpret.CUSTOM,
                check_outcome=ResultOutcome.FAIL,
                check_interpret=CheckResultInterpret.RESPECT,
                overall_outcome=ResultOutcome.PASS,
                note_contains=[],
            ),
            id="pass-custom-fail-respect",
        ),
        pytest.param(
            CheckPhasesCase(
                result_outcome=ResultOutcome.FAIL,
                result_interpret=ResultInterpret.CUSTOM,
                check_outcome=ResultOutcome.FAIL,
                check_interpret=CheckResultInterpret.RESPECT,
                overall_outcome=ResultOutcome.FAIL,
                note_contains=[],
            ),
            id="fail-custom-fail-respect",
        ),
        # Test interpret INFO:
        pytest.param(
            CheckPhasesCase(
                result_outcome=ResultOutcome.PASS,
                result_interpret=ResultInterpret.INFO,
                check_outcome=ResultOutcome.PASS,
                check_interpret=CheckResultInterpret.RESPECT,
                overall_outcome=ResultOutcome.INFO,
                note_contains=[
                    "test result overridden: info",
                    "original test result: pass",
                ],
            ),
            id="pass-info-pass-respect",
        ),
        pytest.param(
            CheckPhasesCase(
                result_outcome=ResultOutcome.FAIL,
                result_interpret=ResultInterpret.INFO,
                check_outcome=ResultOutcome.FAIL,
                check_interpret=CheckResultInterpret.RESPECT,
                overall_outcome=ResultOutcome.INFO,
                note_contains=[
                    "check 'check1' failed",
                    "test result overridden: info",
                    "original test result: fail",
                ],
            ),
            id="fail-info-fail-respect",
        ),
        pytest.param(
            CheckPhasesCase(
                result_outcome=ResultOutcome.PENDING,
                result_interpret=ResultInterpret.INFO,
                check_outcome=ResultOutcome.PASS,
                check_interpret=CheckResultInterpret.RESPECT,
                overall_outcome=ResultOutcome.INFO,
                note_contains=[
                    "test result overridden: info",
                    "original test result: pending",
                ],
            ),
            id="pending-info-pass-respect",
        ),
        # Test interpret ERROR:
        pytest.param(
            CheckPhasesCase(
                result_outcome=ResultOutcome.PASS,
                result_interpret=ResultInterpret.ERROR,
                check_outcome=ResultOutcome.PASS,
                check_interpret=CheckResultInterpret.RESPECT,
                overall_outcome=ResultOutcome.ERROR,
                note_contains=[
                    "test result overridden: error",
                    "original test result: pass",
                ],
            ),
            id="pass-error-pass-respect",
        ),
        # Test interpret XFAIL:
        pytest.param(
            CheckPhasesCase(
                result_outcome=ResultOutcome.PASS,
                result_interpret=ResultInterpret.XFAIL,
                check_outcome=ResultOutcome.FAIL,
                check_interpret=CheckResultInterpret.RESPECT,
                overall_outcome=ResultOutcome.PASS,
                note_contains=[
                    "check 'check1' failed",
                    "test failed as expected",
                ],
            ),
            id="pass-xfail-fail-respect",
        ),
        pytest.param(
            CheckPhasesCase(
                result_outcome=ResultOutcome.PASS,
                result_interpret=ResultInterpret.XFAIL,
                check_outcome=ResultOutcome.PASS,
                check_interpret=CheckResultInterpret.RESPECT,
                overall_outcome=ResultOutcome.FAIL,
                note_contains=[
                    "test was expected to fail",
                    "original test result: pass",
                ],
            ),
            id="pass-xfail-pass-respect",
        ),
        pytest.param(
            CheckPhasesCase(
                result_outcome=ResultOutcome.PASS,
                result_interpret=ResultInterpret.XFAIL,
                check_outcome=ResultOutcome.FAIL,
                check_interpret=CheckResultInterpret.XFAIL,
                overall_outcome=ResultOutcome.FAIL,
                note_contains=[
                    "check 'check1' failed as expected",
                    "test was expected to fail",
                    "original test result: pass",
                ],
            ),
            id="pass-xfail-fail-xfail",
        ),
        # Test interpret WARN:
        pytest.param(
            CheckPhasesCase(
                result_outcome=ResultOutcome.PASS,
                result_interpret=ResultInterpret.WARN,
                check_outcome=ResultOutcome.PASS,
                check_interpret=CheckResultInterpret.RESPECT,
                overall_outcome=ResultOutcome.WARN,
                note_contains=[
                    "test result overridden: warn",
                    "original test result: pass",
                ],
            ),
            id="pass-warn-pass-respect",
        ),
        pytest.param(
            CheckPhasesCase(
                result_outcome=ResultOutcome.PASS,
                result_interpret=ResultInterpret.WARN,
                check_outcome=ResultOutcome.FAIL,
                check_interpret=CheckResultInterpret.RESPECT,
                overall_outcome=ResultOutcome.WARN,
                note_contains=[
                    "check 'check1' failed",
                    "test result overridden: warn",
                    "original test result: pass",
                ],
            ),
            id="pass-warn-fail-respect",
        ),
    ],
)
def test_result_interpret_with_checks(case: CheckPhasesCase) -> None:
    """
    Test result and check interpretation across outcome and interpret combinations.
    """
    result = Result(
        name="test-case",
        result=case.result_outcome,
        check=[
            CheckResult(name="check1", result=ResultOutcome.PASS, event=CheckEvent.BEFORE_TEST),
            CheckResult(
                name="check1",
                result=case.check_outcome,
                event=CheckEvent.AFTER_TEST,
            ),
            CheckResult(name="check2", result=ResultOutcome.PASS, event=CheckEvent.BEFORE_TEST),
        ],
    )

    interpret_checks = {
        "check1": case.check_interpret,
        "check2": CheckResultInterpret.RESPECT,
    }

    interpreted = result.interpret_result(case.result_interpret, interpret_checks)
    assert interpreted.result == case.overall_outcome
    if case.note_contains:
        assert interpreted.note
        for expected_note in case.note_contains:
            assert expected_note in interpreted.note
    else:
        assert not interpreted.note


@pytest.mark.parametrize(
    'case',
    [
        # check1 reduced from [PASS, outcome1, PASS, outcome2] -> worst wins
        pytest.param(
            CheckPhasesDuplicateCase(
                result_outcome=ResultOutcome.PASS,
                result_interpret=ResultInterpret.RESPECT,
                check_outcome1=ResultOutcome.PASS,
                check_outcome2=ResultOutcome.PASS,
                check_interpret=CheckResultInterpret.RESPECT,
                overall_outcome=ResultOutcome.PASS,
                note_contains=[],
            ),
            id="pass-respect-pass-pass-respect",
        ),
        pytest.param(
            CheckPhasesDuplicateCase(
                result_outcome=ResultOutcome.PASS,
                result_interpret=ResultInterpret.RESPECT,
                check_outcome1=ResultOutcome.PASS,
                check_outcome2=ResultOutcome.FAIL,
                check_interpret=CheckResultInterpret.RESPECT,
                overall_outcome=ResultOutcome.FAIL,
                note_contains=[
                    "check 'check1' failed",
                    "original test result: pass",
                ],
            ),
            id="pass-respect-pass-fail-respect",
        ),
        pytest.param(
            CheckPhasesDuplicateCase(
                result_outcome=ResultOutcome.PASS,
                result_interpret=ResultInterpret.RESPECT,
                check_outcome1=ResultOutcome.FAIL,
                check_outcome2=ResultOutcome.FAIL,
                check_interpret=CheckResultInterpret.RESPECT,
                overall_outcome=ResultOutcome.FAIL,
                note_contains=[
                    "check 'check1' failed",
                    "original test result: pass",
                ],
            ),
            id="pass-respect-fail-fail-respect",
        ),
        pytest.param(
            CheckPhasesDuplicateCase(
                result_outcome=ResultOutcome.PASS,
                result_interpret=ResultInterpret.RESPECT,
                check_outcome1=ResultOutcome.WARN,
                check_outcome2=ResultOutcome.PASS,
                check_interpret=CheckResultInterpret.RESPECT,
                overall_outcome=ResultOutcome.WARN,
                note_contains=["original test result: pass"],
            ),
            id="pass-respect-warn-pass-respect",
        ),
        pytest.param(
            CheckPhasesDuplicateCase(
                result_outcome=ResultOutcome.PASS,
                result_interpret=ResultInterpret.RESPECT,
                check_outcome1=ResultOutcome.FAIL,
                check_outcome2=ResultOutcome.WARN,
                check_interpret=CheckResultInterpret.RESPECT,
                overall_outcome=ResultOutcome.FAIL,
                note_contains=[
                    "check 'check1' failed",
                    "original test result: pass",
                ],
            ),
            id="pass-respect-fail-warn-respect",
        ),
    ],
)
def test_check_phases_duplicate_phase(case: CheckPhasesDuplicateCase) -> None:
    """
    Test the interpretation of check results with duplicate phases.
    """
    result = Result(
        name="test-case",
        result=case.result_outcome,
        check=[
            CheckResult(name="check1", result=ResultOutcome.PASS, event=CheckEvent.BEFORE_TEST),
            CheckResult(name="check1", result=case.check_outcome1, event=CheckEvent.AFTER_TEST),
            CheckResult(name="check2", result=ResultOutcome.PASS, event=CheckEvent.BEFORE_TEST),
            # Duplicate phases of check1
            CheckResult(name="check1", result=ResultOutcome.PASS, event=CheckEvent.BEFORE_TEST),
            CheckResult(name="check1", result=case.check_outcome2, event=CheckEvent.AFTER_TEST),
        ],
    )

    interpret_checks = {
        "check1": case.check_interpret,
        "check2": CheckResultInterpret.RESPECT,
    }

    interpreted = result.interpret_result(case.result_interpret, interpret_checks)
    assert interpreted.result == case.overall_outcome
    if case.note_contains:
        assert interpreted.note
        for expected_note in case.note_contains:
            assert expected_note in interpreted.note
    else:
        assert not interpreted.note


# Weird control characters in failures.yaml
#
# https://github.com/teemtee/tmt/issues/3805
_BAD_STRING = """
    :: [  \x1b[1;31mFAIL\x1b[0m  ] :: Command './test_progs -a atomics'
    bpf_testmod.ko is already unloaded."""

_GOOD_STRING = """
    :: [  #{1b}[1;31mFAIL#{1b}[0m  ] :: Command './test_progs -a atomics'
    bpf_testmod.ko is already unloaded."""


def test_save_failures(tmppath: Path, root_logger) -> None:
    from tmt.result import save_failures
    from tmt.steps.execute import TestInvocation

    phase = Common(workdir=tmppath, logger=root_logger)
    phase.step = MagicMock(workdir=tmppath)
    phase.step_workdir = tmppath
    invocation = TestInvocation(root_logger, phase, None, None)

    (tmppath / 'data').mkdir()

    save_failures(invocation, Path('data'), ['foo', _BAD_STRING, 'bar'])

    read_yaml = (tmppath / 'data/failures.yaml').read_text()

    assert tmt.utils.from_yaml(read_yaml) == ['foo', _GOOD_STRING, 'bar']
    assert tmt.utils.from_yaml(read_yaml, yaml_type='safe') == ['foo', _GOOD_STRING, 'bar']
    assert tmt.utils.yaml_to_list(read_yaml) == ['foo', _GOOD_STRING, 'bar']
