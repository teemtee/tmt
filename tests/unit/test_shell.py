import time
from unittest.mock import MagicMock

import pytest

import tmt.utils
from tmt.container import container
from tmt.frameworks.shell import _extract_failures
from tmt.utils import Path


@container
class FailureCase:
    """A test case for _extract_failures: input log content and expected matched lines."""

    log_content: str
    expected: list[str]


@pytest.fixture
def invocation():
    """Provide a mock TestInvocation."""
    return MagicMock()


# ~50k chars of lorem-ipsum text with word boundaries for regex benchmarking.
_LONG_SEGMENT = (
    'Lorem ipsum dolor sit amet consectetur adipiscing elit '
    'sed do eiusmod tempor incididunt ut labore et dolore magna aliqua '
    'Ut enim ad minim veniam quis nostrud exercitation ullamco laboris '
    'nisi ut aliquip ex ea commodo consequat Duis aute irure dolor in '
    'reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla '
    'pariatur Excepteur sint occaecat cupidatat non proident sunt in '
    'culpa qui officia deserunt mollit anim id est laborum '
) * 140  # ~50k characters


@pytest.mark.parametrize(
    'case',
    [
        pytest.param(
            FailureCase(
                log_content='all good\nnothing wrong here\n',
                expected=[],
            ),
            id='no-failures',
        ),
        pytest.param(
            FailureCase(
                log_content='line1\nsome error occurred\nline3\n',
                expected=['some error occurred'],
            ),
            id='error-keyword',
        ),
        pytest.param(
            FailureCase(
                log_content='test passed\ntest fail here\ndone\n',
                expected=['test fail here'],
            ),
            id='fail-keyword',
        ),
        pytest.param(
            FailureCase(
                log_content='ERROR: something\nFAIL: test\n',
                expected=['ERROR: something', 'FAIL: test'],
            ),
            id='case-insensitive',
        ),
        pytest.param(
            FailureCase(
                log_content='ok\nerror one\npass\nfail two\nerror three\n',
                expected=['error one', 'fail two', 'error three'],
            ),
            id='multiple-matches',
        ),
        pytest.param(
            FailureCase(
                log_content='errorless operation\nfailover complete\n',
                expected=[],
            ),
            id='word-boundary-no-false-positives',
        ),
    ],
)
def test_extract_failures(invocation: MagicMock, case: FailureCase) -> None:
    """Verify _extract_failures matches the correct lines."""
    invocation.phase.step.plan.execute.read.return_value = case.log_content
    assert _extract_failures(invocation, Path('dummy.log')) == case.expected


def test_extract_failures_file_error(invocation: MagicMock) -> None:
    """Verify _extract_failures returns empty list when the log file cannot be read."""
    invocation.phase.step.plan.execute.read.side_effect = tmt.utils.FileError('not found')
    assert _extract_failures(invocation, Path('dummy.log')) == []


@pytest.mark.parametrize(
    'case',
    [
        pytest.param(
            FailureCase(
                log_content=f'start\n{_LONG_SEGMENT}\nsome error here\nend\n',
                expected=['some error here'],
            ),
            id='long-line-no-match-followed-by-error',
        ),
        pytest.param(
            FailureCase(
                log_content=f'start\n{_LONG_SEGMENT} error in the middle {_LONG_SEGMENT}\nend\n',
                expected=[f'{_LONG_SEGMENT} error in the middle {_LONG_SEGMENT}'],
            ),
            id='error-embedded-in-long-line',
        ),
        pytest.param(
            FailureCase(
                log_content=f'start\n{_LONG_SEGMENT}errorless{_LONG_SEGMENT}\nend\n',
                expected=[],
            ),
            id='long-line-word-boundary-no-false-positive',
        ),
        pytest.param(
            FailureCase(
                log_content=(
                    f'start\n{_LONG_SEGMENT} a b c d e f g h i j k l m n o p '
                    f'{_LONG_SEGMENT}\nend\n'
                ),
                expected=[],
            ),
            id='long-line-many-word-boundaries-no-match',
        ),
    ],
)
@pytest.mark.timeout(10)
def test_extract_failures_long_lines(invocation: MagicMock, case: FailureCase) -> None:
    """
    Verify correct handling of very long lines (~50k characters).

    The original ``re.findall(r'.*\\b(?:error|fail)\\b.*', ...)`` caused
    catastrophic backtracking on long lines, hanging tmt processes for hours
    on 1M+ character lines (e.g. base64-encoded in-toto attestation payloads).

    Benchmarks with 50k-character lines:

    ====================================  ===========  ===========
    Case                                  Old regex    New method
    ====================================  ===========  ===========
    long line, no match + error line      11.335 s     < 0.001 s
    error embedded in long line           0.001 s      < 0.001 s
    word boundary, no false positive      49.290 s     < 0.001 s
    many word boundaries, no match        133.628 s    < 0.003 s
    ====================================  ===========  ===========

    The new ``splitlines()`` + per-line ``re.search()`` runs in < 0.001 s
    for all cases. A 0.1 s threshold sits well between the two methods:
    any result above 0.1 s indicates a regression toward the old behavior.
    The ``@pytest.mark.timeout(10)`` serves as an additional safety net
    to prevent CI from hanging if a regression is catastrophic.
    """
    invocation.phase.step.plan.execute.read.return_value = case.log_content

    start = time.time()
    result = _extract_failures(invocation, Path('dummy.log'))
    elapsed = time.time() - start

    assert result == case.expected
    assert elapsed < 0.1, (
        f'_extract_failures took {elapsed:.3f}s on a log with a ~50k-char line; '
        f'expected < 0.001s (old regex took 11-49s at this size)'
    )
