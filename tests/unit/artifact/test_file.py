import tempfile

import pytest

from tmt.log import Logger
from tmt.steps.prepare.artifact.providers.file import (
    PackageAsFileArtifactInfo,
    PackageAsFileArtifactProvider,
)
from tmt.utils import Path


@pytest.mark.parametrize(
    ("pattern", "expected_count", "expected_names"),
    [
        # Single file
        ("foo.rpm", 1, {"foo.rpm"}),
        # Glob pattern matching 3 files
        ("package-*.rpm", 3, {f"package-{i}.rpm" for i in range(3)}),
    ],
)
def test_file_artifact_provider_patterns(root_logger, pattern, expected_count, expected_names):
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create test files
        if "package-" in pattern:
            for i in range(3):
                (tmpdir / f"package-{i}.rpm").touch()
        else:
            (tmpdir / "foo.rpm").touch()

        provider = PackageAsFileArtifactProvider(f"file:{tmpdir}/{pattern}", root_logger)
        artifacts = provider.artifacts

        assert len(artifacts) == expected_count
        assert {a.id for a in artifacts} == expected_names
        assert all(Path(a.location).exists() for a in artifacts)


def test_file_artifact_provider_deduplicates_globs(root_logger):
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create multiple subdirectories with identical files
        for dirname in ("foo", "bar"):
            subdir = tmpdir / dirname
            subdir.mkdir()
            (subdir / "baz.rpm").touch()

        provider = PackageAsFileArtifactProvider(f"file:{tmpdir}/*/baz.rpm", root_logger)
        artifacts = provider.artifacts

        assert len(artifacts) == 1
        assert artifacts[0].id == "baz.rpm"
