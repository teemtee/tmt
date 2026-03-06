import time
from unittest.mock import MagicMock

from tmt.frameworks.shell import _extract_failures
from tmt.utils import Path


def _make_invocation(log_content: str) -> MagicMock:
    """Create a mock TestInvocation that returns given log content on read."""
    mock = MagicMock()
    mock.phase.step.plan.execute.read.return_value = log_content
    return mock


class TestExtractFailures:
    def test_no_failures(self) -> None:
        invocation = _make_invocation("all good\nnothing wrong here\n")
        assert _extract_failures(invocation, Path("dummy.log")) == []

    def test_error_match(self) -> None:
        invocation = _make_invocation("line1\nsome error occurred\nline3\n")
        result = _extract_failures(invocation, Path("dummy.log"))
        assert result == ["some error occurred"]

    def test_fail_match(self) -> None:
        invocation = _make_invocation("test passed\ntest fail here\ndone\n")
        result = _extract_failures(invocation, Path("dummy.log"))
        assert result == ["test fail here"]

    def test_case_insensitive(self) -> None:
        invocation = _make_invocation("ERROR: something\nFAIL: test\n")
        result = _extract_failures(invocation, Path("dummy.log"))
        assert result == ["ERROR: something", "FAIL: test"]

    def test_multiple_matches(self) -> None:
        invocation = _make_invocation("ok\nerror one\npass\nfail two\nerror three\n")
        result = _extract_failures(invocation, Path("dummy.log"))
        assert result == ["error one", "fail two", "error three"]

    def test_word_boundary(self) -> None:
        """Words like 'errorless' or 'failover' should not match."""
        invocation = _make_invocation("errorless operation\nfailover complete\n")
        assert _extract_failures(invocation, Path("dummy.log")) == []

    def test_file_error(self) -> None:
        import tmt.utils

        invocation = MagicMock()
        invocation.phase.step.plan.execute.read.side_effect = tmt.utils.FileError("not found")
        assert _extract_failures(invocation, Path("dummy.log")) == []

    def test_long_lines_performance(self) -> None:
        """
        Regression test: regex must not cause catastrophic backtracking
        on very long lines.

        The original implementation used re.findall(r'.*\\b(?:error|fail)\\b.*', ...)
        which caused O(n^2) or worse backtracking on long lines without matches,
        hanging tmt processes for hours on 1M+ character lines (e.g. base64-encoded
        in-toto attestation payloads in container build logs).
        """
        # Build a log with a 1M-character line (similar to base64 attestation data)
        long_line = "A" * 1_000_000
        log_content = f"start\n{long_line}\nsome error here\nend\n"

        invocation = _make_invocation(log_content)

        start = time.monotonic()
        result = _extract_failures(invocation, Path("dummy.log"))
        elapsed = time.monotonic() - start

        # Must complete in under 5 seconds (the old regex took 5+ seconds
        # on just 10k characters, and would never complete on 1M characters)
        assert elapsed < 5.0, (
            f"_extract_failures took {elapsed:.1f}s on a log with a 1M-char line; "
            f"likely catastrophic regex backtracking"
        )
        assert result == ["some error here"]
