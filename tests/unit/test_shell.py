import time
from unittest.mock import MagicMock

import pytest

import tmt.utils
from tmt.frameworks.shell import _extract_failures
from tmt.utils import Path


@pytest.fixture
def make_invocation():
    """Factory fixture creating a mock TestInvocation returning given log content."""

    def _factory(log_content: str) -> MagicMock:
        mock = MagicMock()
        mock.phase.step.plan.execute.read.return_value = log_content
        return mock

    return _factory


_FAILURE_MATCH_CASES: list[tuple[str, str, list[str]]] = [
    ('no failures', 'all good\nnothing wrong here\n', []),
    ('error keyword', 'line1\nsome error occurred\nline3\n', ['some error occurred']),
    ('fail keyword', 'test passed\ntest fail here\ndone\n', ['test fail here']),
    ('case insensitive', 'ERROR: something\nFAIL: test\n', ['ERROR: something', 'FAIL: test']),
    (
        'multiple matches',
        'ok\nerror one\npass\nfail two\nerror three\n',
        ['error one', 'fail two', 'error three'],
    ),
    ('word boundary - no false positives', 'errorless operation\nfailover complete\n', []),
]


@pytest.mark.parametrize(
    ('log_content', 'expected'),
    [(log, expected) for _, log, expected in _FAILURE_MATCH_CASES],
    ids=[name for name, _, _ in _FAILURE_MATCH_CASES],
)
def test_extract_failures(
    make_invocation,
    log_content: str,
    expected: list[str],
) -> None:
    """Verify _extract_failures matches the correct lines."""
    invocation = make_invocation(log_content)
    assert _extract_failures(invocation, Path('dummy.log')) == expected


def test_extract_failures_file_error() -> None:
    """Verify _extract_failures returns empty list when the log file cannot be read."""
    invocation = MagicMock()
    invocation.phase.step.plan.execute.read.side_effect = tmt.utils.FileError('not found')
    assert _extract_failures(invocation, Path('dummy.log')) == []


_LONG_LINE_CASES: list[tuple[str, str, list[str]]] = [
    (
        'long line without match followed by error line',
        'start\n{long}\nsome error here\nend\n',
        ['some error here'],
    ),
    (
        'error embedded in long line without newline separator',
        'start\n{long} error in the middle {long}\nend\n',
        ['{long} error in the middle {long}'],
    ),
    (
        'long line with word boundary - no false positive',
        'start\n{long}errorless{long}\nend\n',
        [],
    ),
]


@pytest.mark.parametrize(
    ('log_template', 'expected_template'),
    [(log, expected) for _, log, expected in _LONG_LINE_CASES],
    ids=[name for name, _, _ in _LONG_LINE_CASES],
)
def test_extract_failures_long_lines(
    make_invocation,
    log_template: str,
    expected_template: list[str],
) -> None:
    """
    Verify correct handling of very long lines.

    The original implementation used ``re.findall(r'.*\\b(?:error|fail)\\b.*', ...)``
    which caused catastrophic backtracking on long lines (O(n^2) or worse),
    hanging tmt processes for hours on 1M+ character lines (e.g. base64-encoded
    in-toto attestation payloads in container build logs).

    The current implementation uses ``str.splitlines()`` and per-line
    ``re.search()`` which processes each line in linear time.
    """
    long_segment = 'A' * 1_000_000
    log_content = log_template.replace('{long}', long_segment)
    expected = [line.replace('{long}', long_segment) for line in expected_template]

    invocation = make_invocation(log_content)

    # time.monotonic() is the correct choice for elapsed time measurement
    # as it is not affected by system clock adjustments.
    start = time.monotonic()
    result = _extract_failures(invocation, Path('dummy.log'))
    elapsed = time.monotonic() - start

    assert result == expected

    # The old regex would never complete on lines this long — it took 5+
    # seconds on just 10k characters. The splitlines approach finishes in
    # well under 1 second. Use 30 seconds as a generous ceiling to avoid
    # flakiness on slow CI while still catching catastrophic backtracking.
    assert elapsed < 30.0, (
        f'_extract_failures took {elapsed:.1f}s on a log with a 1M-char line; '
        f'likely catastrophic regex backtracking'
    )
