from unittest.mock import MagicMock

import pytest

from tmt.log import Logger
from tmt.steps.prepare.artifact.providers.file import (
    PackageAsFileArtifactInfo,
    PackageAsFileArtifactProvider,
)
from tmt.utils import Path


@pytest.mark.parametrize(
    ("pattern", "expected_names"),
    [
        ("foo.rpm", {"foo.rpm"}),
        ("package-*.rpm", {f"package-{i}.rpm" for i in range(3)}),
    ],
)
def test_file_artifact_provider_patterns(root_logger, tmp_path, pattern, expected_names):
    # Create test files
    for name in expected_names:
        (tmp_path / name).touch()

    provider = PackageAsFileArtifactProvider(f"file:{tmp_path}/{pattern}", root_logger)
    artifacts = provider.artifacts

    assert len(artifacts) == len(expected_names)
    assert {a.id for a in artifacts} == expected_names
    assert all(Path(a.location).exists() for a in artifacts)


def test_file_artifact_provider_deduplicates_globs(root_logger, tmp_path, caplog):
    # Create multiple subdirectories with identical files
    for dirname in ("foo", "bar"):
        subdir = tmp_path / dirname
        subdir.mkdir()
        (subdir / "baz.rpm").touch()

    provider = PackageAsFileArtifactProvider(f"file:{tmp_path}/*/baz.rpm", root_logger)
    artifacts = provider.artifacts

    assert len(artifacts) == 1
    assert artifacts[0].id == "baz.rpm"
    assert "Duplicate artifact" in caplog.text


def test_download_artifact(root_logger, tmp_path):
    # Test file download
    test_file = tmp_path / "foo.rpm"
    test_file.touch()
    file_provider = PackageAsFileArtifactProvider(f"file:{test_file}", root_logger)
    guest = MagicMock()
    file_provider._download_artifact(file_provider.artifacts[0], guest, Path("/remote/foo.rpm"))
    guest.push.assert_called_once()

    # Test URL download
    url_provider = PackageAsFileArtifactProvider("file:https://example.com/foo.rpm", root_logger)
    url_provider._download_artifact(url_provider.artifacts[0], guest, Path("/remote/foo.rpm"))
    guest.execute.assert_called_once()
