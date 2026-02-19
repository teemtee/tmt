from unittest.mock import MagicMock

import pytest

import tmt.utils
from tmt.checks import CheckEvent
from tmt.cli import TmtExitCode
from tmt.result import (
    CheckResult,
    CheckResultInterpret,
    Result,
    ResultInterpret,
    ResultOutcome,
    results_to_exit_code,
)
from tmt.utils import Common, Path


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
    (
        'result_outcome',
        'interpret',
        'interpret_checks',
        'expected_outcome',
        'expected_note_contains',
    ),
    [
        # Test RESPECT interpretation
        (
            ResultOutcome.PASS,
            ResultInterpret.RESPECT,
            {"check1": CheckResultInterpret.RESPECT},
            ResultOutcome.PASS,
            [],
        ),
        (
            ResultOutcome.FAIL,
            ResultInterpret.RESPECT,
            {"check1": CheckResultInterpret.RESPECT},
            ResultOutcome.FAIL,
            ["check 'check1' failed"],  # Note is set when check fails
        ),
        # Test XFAIL interpretation
        (
            ResultOutcome.FAIL,
            ResultInterpret.XFAIL,
            {"check1": CheckResultInterpret.RESPECT},
            ResultOutcome.PASS,
            ["check 'check1' failed", "test failed as expected", "original test result: fail"],
        ),
        (
            ResultOutcome.PASS,
            ResultInterpret.XFAIL,
            {"check1": CheckResultInterpret.RESPECT},
            ResultOutcome.FAIL,
            ["test was expected to fail", "original test result: pass"],
        ),
        # Test INFO interpretation
        (
            ResultOutcome.FAIL,
            ResultInterpret.INFO,
            {"check1": CheckResultInterpret.RESPECT},
            ResultOutcome.INFO,
            [
                "check 'check1' failed",
                "test result overridden: info",
                "original test result: fail",
            ],
        ),
        (
            ResultOutcome.PASS,
            ResultInterpret.INFO,
            {"check1": CheckResultInterpret.RESPECT},
            ResultOutcome.INFO,
            ["test result overridden: info", "original test result: pass"],
        ),
        # Test WARN interpretation
        (
            ResultOutcome.PASS,
            ResultInterpret.WARN,
            {"check1": CheckResultInterpret.RESPECT},
            ResultOutcome.WARN,
            ["test result overridden: warn", "original test result: pass"],
        ),
        # Test ERROR interpretation
        (
            ResultOutcome.PASS,
            ResultInterpret.ERROR,
            {"check1": CheckResultInterpret.RESPECT},
            ResultOutcome.ERROR,
            ["test result overridden: error", "original test result: pass"],
        ),
        # Test CUSTOM interpretation (should not modify result)
        (
            ResultOutcome.FAIL,
            ResultInterpret.CUSTOM,
            {"check1": CheckResultInterpret.RESPECT},
            ResultOutcome.FAIL,
            [],
        ),
    ],
    ids=[
        "respect-pass",
        "respect-fail",
        "xfail-fail",
        "xfail-pass",
        "info-fail",
        "info-pass",
        "warn-pass",
        "error-pass",
        "custom-fail",
    ],
)
def test_result_interpret_all_cases(
    result_outcome: ResultOutcome,
    interpret: ResultInterpret,
    interpret_checks: dict[str, CheckResultInterpret],
    expected_outcome: ResultOutcome,
    expected_note_contains: list[str],
) -> None:
    """
    Test all possible combinations of result interpretations
    """

    result = Result(
        name="test-case",
        result=result_outcome,
        check=[CheckResult(name="check1", result=result_outcome, event=CheckEvent.BEFORE_TEST)],
    )

    interpreted = result.interpret_result(interpret, interpret_checks)
    assert interpreted.result == expected_outcome

    if expected_note_contains:
        assert interpreted.note
        for expected_note in expected_note_contains:
            assert expected_note in interpreted.note
    else:
        assert not interpreted.note


def test_result_interpret_check_phases() -> None:
    """
    Test the interpretation of check results with different phases
    """

    result_before = Result(
        name="test-case-before",
        check=[
            CheckResult(name="check1", result=ResultOutcome.FAIL, event=CheckEvent.BEFORE_TEST),
            CheckResult(name="check1", result=ResultOutcome.PASS, event=CheckEvent.AFTER_TEST),
            CheckResult(name="check2", result=ResultOutcome.PASS, event=CheckEvent.BEFORE_TEST),
        ],
    )
    result_after = Result(
        name="test-case-after",
        check=[
            CheckResult(name="check1", result=ResultOutcome.PASS, event=CheckEvent.BEFORE_TEST),
            CheckResult(name="check1", result=ResultOutcome.FAIL, event=CheckEvent.AFTER_TEST),
            CheckResult(name="check2", result=ResultOutcome.PASS, event=CheckEvent.BEFORE_TEST),
        ],
    )
    result_both = Result(
        name="test-case-both",
        check=[
            CheckResult(name="check1", result=ResultOutcome.FAIL, event=CheckEvent.BEFORE_TEST),
            CheckResult(name="check1", result=ResultOutcome.FAIL, event=CheckEvent.AFTER_TEST),
            CheckResult(name="check2", result=ResultOutcome.PASS, event=CheckEvent.BEFORE_TEST),
        ],
    )

    # Test with mixed interpretations
    interpret_checks = {
        "check1": CheckResultInterpret.RESPECT,
        "check2": CheckResultInterpret.INFO,
    }

    interpreted_before = result_before.interpret_result(ResultInterpret.RESPECT, interpret_checks)
    interpreted_after = result_after.interpret_result(ResultInterpret.RESPECT, interpret_checks)
    interpreted_both = result_both.interpret_result(ResultInterpret.RESPECT, interpret_checks)

    for interpreted in [interpreted_before, interpreted_after, interpreted_both]:
        assert interpreted.note is not None
        assert "check 'check1' failed" in interpreted.note
        assert "check 'check2' is informational" in interpreted.note

    # Verify individual check results were interpreted
    assert interpreted_before.check[0].result == ResultOutcome.FAIL  # check1 BEFORE_TEST
    assert interpreted_before.check[1].result == ResultOutcome.PASS  # check1 AFTER_TEST
    assert interpreted_before.check[2].result == ResultOutcome.PASS  # check2 BEFORE_TEST (INFO)

    assert interpreted_after.check[0].result == ResultOutcome.PASS  # check1 BEFORE_TEST
    assert interpreted_after.check[1].result == ResultOutcome.FAIL  # check1 AFTER_TEST
    assert interpreted_after.check[2].result == ResultOutcome.PASS  # check2 BEFORE_TEST (INFO)

    assert interpreted_both.check[0].result == ResultOutcome.FAIL  # check1 BEFORE_TEST
    assert interpreted_both.check[1].result == ResultOutcome.FAIL  # check1 AFTER_TEST
    assert interpreted_both.check[2].result == ResultOutcome.PASS  # check2 BEFORE_TEST (INFO)


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
    (
        'result_outcome',
        'interpret',
        'check_result_outcome',
        'check_interpret',
        'expected_outcome',
        'expected_note_contains',
    ),
    [
        # Test interpret RESPECT:
        pytest.param(
            ResultOutcome.PASS,
            ResultInterpret.RESPECT,
            ResultOutcome.PASS,
            CheckResultInterpret.RESPECT,
            ResultOutcome.PASS,
            [],
            id="pass-respect-pass-respect",
        ),
        pytest.param(
            ResultOutcome.PASS,
            ResultInterpret.RESPECT,
            ResultOutcome.FAIL,
            CheckResultInterpret.RESPECT,
            ResultOutcome.FAIL,
            ["check 'check1' failed", "original test result: pass"],
            id="pass-respect-fail-respect",
        ),
        pytest.param(
            ResultOutcome.FAIL,
            ResultInterpret.RESPECT,
            ResultOutcome.PASS,
            CheckResultInterpret.RESPECT,
            ResultOutcome.FAIL,
            [],
            id="fail-respect-pass-respect",
        ),
        pytest.param(
            ResultOutcome.FAIL,
            ResultInterpret.RESPECT,
            ResultOutcome.FAIL,
            CheckResultInterpret.RESPECT,
            ResultOutcome.FAIL,
            ["check 'check1' failed"],
            id="fail-respect-fail-respect",
        ),
        pytest.param(
            ResultOutcome.PASS,
            ResultInterpret.RESPECT,
            ResultOutcome.WARN,
            CheckResultInterpret.RESPECT,
            ResultOutcome.WARN,
            ["original test result: pass"],
            id="pass-respect-warn-respect",
        ),
        pytest.param(
            ResultOutcome.FAIL,
            ResultInterpret.RESPECT,
            ResultOutcome.WARN,
            CheckResultInterpret.RESPECT,
            ResultOutcome.FAIL,
            [],
            id="fail-respect-warn-respect",
        ),
        pytest.param(
            ResultOutcome.PASS,
            ResultInterpret.RESPECT,
            ResultOutcome.ERROR,
            CheckResultInterpret.RESPECT,
            ResultOutcome.ERROR,
            ["original test result: pass"],
            id="pass-respect-error-respect",
        ),
        pytest.param(
            ResultOutcome.FAIL,
            ResultInterpret.RESPECT,
            ResultOutcome.ERROR,
            CheckResultInterpret.RESPECT,
            ResultOutcome.ERROR,
            ["original test result: fail"],
            id="fail-respect-error-respect",
        ),
        pytest.param(
            ResultOutcome.PASS,
            ResultInterpret.RESPECT,
            ResultOutcome.PASS,
            CheckResultInterpret.INFO,
            ResultOutcome.PASS,
            ["check 'check1' is informational"],
            id="pass-respect-pass-info",
        ),
        pytest.param(
            ResultOutcome.PASS,
            ResultInterpret.RESPECT,
            ResultOutcome.FAIL,
            CheckResultInterpret.INFO,
            ResultOutcome.PASS,
            ["check 'check1' is informational"],
            id="pass-respect-fail-info",
        ),
        pytest.param(
            ResultOutcome.PASS,
            ResultInterpret.RESPECT,
            ResultOutcome.WARN,
            CheckResultInterpret.INFO,
            ResultOutcome.PASS,
            ["check 'check1' is informational"],
            id="pass-respect-warn-info",
        ),
        pytest.param(
            ResultOutcome.FAIL,
            ResultInterpret.RESPECT,
            ResultOutcome.WARN,
            CheckResultInterpret.INFO,
            ResultOutcome.FAIL,
            ["check 'check1' is informational"],
            id="fail-respect-warn-info",
        ),
        pytest.param(
            ResultOutcome.PASS,
            ResultInterpret.RESPECT,
            ResultOutcome.ERROR,
            CheckResultInterpret.INFO,
            ResultOutcome.PASS,
            ["check 'check1' is informational"],
            id="pass-respect-error-info",
        ),
        pytest.param(
            ResultOutcome.FAIL,
            ResultInterpret.RESPECT,
            ResultOutcome.ERROR,
            CheckResultInterpret.INFO,
            ResultOutcome.FAIL,
            ["check 'check1' is informational"],
            id="fail-respect-error-info",
        ),
        pytest.param(
            ResultOutcome.PASS,
            ResultInterpret.RESPECT,
            ResultOutcome.INFO,
            CheckResultInterpret.RESPECT,
            ResultOutcome.PASS,
            [],
            id="pass-respect-info-respect",
        ),
        pytest.param(
            ResultOutcome.FAIL,
            ResultInterpret.RESPECT,
            ResultOutcome.INFO,
            CheckResultInterpret.RESPECT,
            ResultOutcome.FAIL,
            [],
            id="fail-respect-info-respect",
        ),
        pytest.param(
            ResultOutcome.PASS,
            ResultInterpret.RESPECT,
            ResultOutcome.INFO,
            CheckResultInterpret.INFO,
            ResultOutcome.PASS,
            ["check 'check1' is informational"],
            id="pass-respect-info-info",
        ),
        pytest.param(
            ResultOutcome.FAIL,
            ResultInterpret.RESPECT,
            ResultOutcome.INFO,
            CheckResultInterpret.INFO,
            ResultOutcome.FAIL,
            ["check 'check1' is informational"],
            id="fail-respect-info-info",
        ),
        pytest.param(
            ResultOutcome.PASS,
            ResultInterpret.RESPECT,
            ResultOutcome.INFO,
            CheckResultInterpret.XFAIL,
            ResultOutcome.FAIL,
            ["check 'check1' did not fail as expected"],
            id="pass-respect-info-xfail",
        ),
        pytest.param(
            ResultOutcome.FAIL,
            ResultInterpret.RESPECT,
            ResultOutcome.INFO,
            CheckResultInterpret.XFAIL,
            ResultOutcome.FAIL,
            ["check 'check1' did not fail as expected"],
            id="fail-respect-info-xfail",
        ),
        pytest.param(
            ResultOutcome.PASS,
            ResultInterpret.RESPECT,
            ResultOutcome.SKIP,
            CheckResultInterpret.RESPECT,
            ResultOutcome.PASS,
            [],
            id="pass-respect-skip-respect",
        ),
        pytest.param(
            ResultOutcome.FAIL,
            ResultInterpret.RESPECT,
            ResultOutcome.SKIP,
            CheckResultInterpret.RESPECT,
            ResultOutcome.FAIL,
            [],
            id="fail-respect-skip-respect",
        ),
        pytest.param(
            ResultOutcome.PASS,
            ResultInterpret.RESPECT,
            ResultOutcome.SKIP,
            CheckResultInterpret.INFO,
            ResultOutcome.PASS,
            ["check 'check1' is informational"],
            id="pass-respect-skip-info",
        ),
        pytest.param(
            ResultOutcome.FAIL,
            ResultInterpret.RESPECT,
            ResultOutcome.SKIP,
            CheckResultInterpret.INFO,
            ResultOutcome.FAIL,
            ["check 'check1' is informational"],
            id="fail-respect-skip-info",
        ),
        pytest.param(
            ResultOutcome.PASS,
            ResultInterpret.RESPECT,
            ResultOutcome.SKIP,
            CheckResultInterpret.XFAIL,
            ResultOutcome.FAIL,
            ["check 'check1' did not fail as expected"],
            id="pass-respect-skip-xfail",
        ),
        pytest.param(
            ResultOutcome.FAIL,
            ResultInterpret.RESPECT,
            ResultOutcome.SKIP,
            CheckResultInterpret.XFAIL,
            ResultOutcome.FAIL,
            ["check 'check1' did not fail as expected"],
            id="fail-respect-skip-xfail",
        ),
        pytest.param(
            ResultOutcome.PASS,
            ResultInterpret.RESPECT,
            ResultOutcome.PENDING,
            CheckResultInterpret.RESPECT,
            ResultOutcome.PASS,
            [],
            id="pass-respect-pending-respect",
        ),
        pytest.param(
            ResultOutcome.FAIL,
            ResultInterpret.RESPECT,
            ResultOutcome.PENDING,
            CheckResultInterpret.RESPECT,
            ResultOutcome.FAIL,
            [],
            id="fail-respect-pending-respect",
        ),
        pytest.param(
            ResultOutcome.PASS,
            ResultInterpret.RESPECT,
            ResultOutcome.PENDING,
            CheckResultInterpret.INFO,
            ResultOutcome.PASS,
            ["check 'check1' is informational"],
            id="pass-respect-pending-info",
        ),
        pytest.param(
            ResultOutcome.FAIL,
            ResultInterpret.RESPECT,
            ResultOutcome.PENDING,
            CheckResultInterpret.INFO,
            ResultOutcome.FAIL,
            ["check 'check1' is informational"],
            id="fail-respect-pending-info",
        ),
        pytest.param(
            ResultOutcome.PASS,
            ResultInterpret.RESPECT,
            ResultOutcome.PENDING,
            CheckResultInterpret.XFAIL,
            ResultOutcome.FAIL,
            ["check 'check1' did not fail as expected"],
            id="pass-respect-pending-xfail",
        ),
        pytest.param(
            ResultOutcome.FAIL,
            ResultInterpret.RESPECT,
            ResultOutcome.PENDING,
            CheckResultInterpret.XFAIL,
            ResultOutcome.FAIL,
            ["check 'check1' did not fail as expected"],
            id="fail-respect-pending-xfail",
        ),
        pytest.param(
            ResultOutcome.PASS,
            ResultInterpret.RESPECT,
            ResultOutcome.FAIL,
            CheckResultInterpret.XFAIL,
            ResultOutcome.PASS,
            ["check 'check1' failed as expected"],
            id="pass-respect-fail-xfail",
        ),
        pytest.param(
            ResultOutcome.PASS,
            ResultInterpret.RESPECT,
            ResultOutcome.PASS,
            CheckResultInterpret.XFAIL,
            ResultOutcome.FAIL,
            ["check 'check1' did not fail as expected", "original test result: pass"],
            id="pass-respect-pass-xfail",
        ),
        pytest.param(
            ResultOutcome.FAIL,
            ResultInterpret.RESPECT,
            ResultOutcome.FAIL,
            CheckResultInterpret.XFAIL,
            ResultOutcome.FAIL,
            ["check 'check1' failed as expected"],
            id="fail-respect-fail-xfail",
        ),
        pytest.param(
            ResultOutcome.FAIL,
            ResultInterpret.RESPECT,
            ResultOutcome.PASS,
            CheckResultInterpret.XFAIL,
            ResultOutcome.FAIL,
            ["check 'check1' did not fail as expected"],
            id="fail-respect-pass-xfail",
        ),
        pytest.param(
            ResultOutcome.PASS,
            ResultInterpret.RESPECT,
            ResultOutcome.WARN,
            CheckResultInterpret.XFAIL,
            ResultOutcome.WARN,
            ["original test result: pass"],
            id="pass-respect-warn-xfail",
        ),
        pytest.param(
            ResultOutcome.FAIL,
            ResultInterpret.RESPECT,
            ResultOutcome.WARN,
            CheckResultInterpret.XFAIL,
            ResultOutcome.FAIL,
            [],
            id="fail-respect-warn-xfail",
        ),
        pytest.param(
            ResultOutcome.PASS,
            ResultInterpret.RESPECT,
            ResultOutcome.ERROR,
            CheckResultInterpret.XFAIL,
            ResultOutcome.ERROR,
            ["original test result: pass"],
            id="pass-respect-error-xfail",
        ),
        pytest.param(
            ResultOutcome.FAIL,
            ResultInterpret.RESPECT,
            ResultOutcome.ERROR,
            CheckResultInterpret.XFAIL,
            ResultOutcome.ERROR,
            ["original test result: fail"],
            id="fail-respect-error-xfail",
        ),
        # Test interpret CUSTOM:
        pytest.param(
            ResultOutcome.PASS,
            ResultInterpret.CUSTOM,
            ResultOutcome.FAIL,
            CheckResultInterpret.RESPECT,
            ResultOutcome.PASS,
            [],
            id="pass-custom-fail-respect",
        ),
        # Test interpret XFAIL:
        pytest.param(
            ResultOutcome.PASS,
            ResultInterpret.XFAIL,
            ResultOutcome.FAIL,
            CheckResultInterpret.RESPECT,
            ResultOutcome.PASS,
            ["check 'check1' failed", "test failed as expected"],
            id="pass-xfail-fail-respect",
        ),
        pytest.param(
            ResultOutcome.PASS,
            ResultInterpret.XFAIL,
            ResultOutcome.PASS,
            CheckResultInterpret.RESPECT,
            ResultOutcome.FAIL,
            ["test was expected to fail", "original test result: pass"],
            id="pass-xfail-pass-respect",
        ),
        pytest.param(
            ResultOutcome.PASS,
            ResultInterpret.XFAIL,
            ResultOutcome.FAIL,
            CheckResultInterpret.XFAIL,
            ResultOutcome.FAIL,
            [
                "check 'check1' failed as expected",
                "test was expected to fail",
                "original test result: pass",
            ],
            id="pass-xfail-fail-xfail",
        ),
        # Test interpret WARN:
        pytest.param(
            ResultOutcome.PASS,
            ResultInterpret.WARN,
            ResultOutcome.PASS,
            CheckResultInterpret.RESPECT,
            ResultOutcome.WARN,
            ["test result overridden: warn", "original test result: pass"],
            id="pass-warn-pass-respect",
        ),
        pytest.param(
            ResultOutcome.PASS,
            ResultInterpret.WARN,
            ResultOutcome.FAIL,
            CheckResultInterpret.RESPECT,
            ResultOutcome.WARN,
            [
                "check 'check1' failed",
                "test result overridden: warn",
                "original test result: pass",
            ],
            id="pass-warn-fail-respect",
        ),
    ],
)
def test_check_phases_combinations(
    result_outcome: ResultOutcome,
    interpret: ResultInterpret,
    check_result_outcome: ResultOutcome,
    check_interpret: CheckResultInterpret,
    expected_outcome: ResultOutcome,
    expected_note_contains: list[str],
) -> None:
    result = Result(
        name="test-case",
        result=result_outcome,
        check=[
            CheckResult(name="check1", result=ResultOutcome.PASS, event=CheckEvent.BEFORE_TEST),
            CheckResult(name="check1", result=check_result_outcome, event=CheckEvent.AFTER_TEST),
            CheckResult(name="check2", result=ResultOutcome.PASS, event=CheckEvent.BEFORE_TEST),
        ],
    )

    interpret_checks = {
        "check1": check_interpret,
        "check2": CheckResultInterpret.RESPECT,
    }

    interpreted = result.interpret_result(interpret, interpret_checks)
    assert interpreted.result == expected_outcome
    if expected_note_contains:
        assert interpreted.note
        for expected_note in expected_note_contains:
            assert expected_note in interpreted.note
    else:
        assert not interpreted.note


@pytest.mark.parametrize(
    (
        'result_outcome',
        'interpret',
        'check_result_outcome1',
        'check_result_outcome2',
        'check_interpret',
        'expected_outcome',
        'expected_note_contains',
    ),
    [
        # check1 reduced from [PASS, outcome1, PASS, outcome2] -> worst wins
        pytest.param(
            ResultOutcome.PASS,
            ResultInterpret.RESPECT,
            ResultOutcome.PASS,
            ResultOutcome.PASS,
            CheckResultInterpret.RESPECT,
            ResultOutcome.PASS,
            [],
            id="pass-respect-pass-pass-respect",
        ),
        pytest.param(
            ResultOutcome.PASS,
            ResultInterpret.RESPECT,
            ResultOutcome.PASS,
            ResultOutcome.FAIL,
            CheckResultInterpret.RESPECT,
            ResultOutcome.FAIL,
            ["check 'check1' failed", "original test result: pass"],
            id="pass-respect-pass-fail-respect",
        ),
        pytest.param(
            ResultOutcome.PASS,
            ResultInterpret.RESPECT,
            ResultOutcome.FAIL,
            ResultOutcome.FAIL,
            CheckResultInterpret.RESPECT,
            ResultOutcome.FAIL,
            ["check 'check1' failed", "original test result: pass"],
            id="pass-respect-fail-fail-respect",
        ),
        pytest.param(
            ResultOutcome.PASS,
            ResultInterpret.RESPECT,
            ResultOutcome.WARN,
            ResultOutcome.PASS,
            CheckResultInterpret.RESPECT,
            ResultOutcome.WARN,
            ["original test result: pass"],
            id="pass-respect-warn-pass-respect",
        ),
        pytest.param(
            ResultOutcome.PASS,
            ResultInterpret.RESPECT,
            ResultOutcome.FAIL,
            ResultOutcome.WARN,
            CheckResultInterpret.RESPECT,
            ResultOutcome.FAIL,
            ["check 'check1' failed", "original test result: pass"],
            id="pass-respect-fail-warn-respect",
        ),
    ],
)
def test_check_phases_duplicate_phase(
    result_outcome: ResultOutcome,
    interpret: ResultInterpret,
    check_result_outcome1: ResultOutcome,
    check_result_outcome2: ResultOutcome,
    check_interpret: CheckResultInterpret,
    expected_outcome: ResultOutcome,
    expected_note_contains: list[str],
) -> None:
    result = Result(
        name="test-case",
        result=result_outcome,
        check=[
            CheckResult(name="check1", result=ResultOutcome.PASS, event=CheckEvent.BEFORE_TEST),
            CheckResult(name="check1", result=check_result_outcome1, event=CheckEvent.AFTER_TEST),
            CheckResult(name="check2", result=ResultOutcome.PASS, event=CheckEvent.BEFORE_TEST),
            CheckResult(name="check1", result=ResultOutcome.PASS, event=CheckEvent.BEFORE_TEST),
            CheckResult(name="check1", result=check_result_outcome2, event=CheckEvent.AFTER_TEST),
        ],
    )

    interpret_checks = {
        "check1": check_interpret,
        "check2": CheckResultInterpret.RESPECT,
    }

    interpreted = result.interpret_result(interpret, interpret_checks)
    assert interpreted.result == expected_outcome
    if expected_note_contains:
        assert interpreted.note
        for expected_note in expected_note_contains:
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
