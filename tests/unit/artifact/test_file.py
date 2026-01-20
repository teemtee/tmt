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
def test_file_artifact_provider_patterns(tmp_path, pattern, expected_names, artifact_provider):
    # Create test files
    for name in expected_names:
        (tmp_path / name).touch()

    provider = artifact_provider(f"file:{tmp_path}/{pattern}")
    artifacts = provider.artifacts

    assert len(artifacts) == len(expected_names)
    assert {a.id for a in artifacts} == expected_names
    assert all(Path(a.location).exists() for a in artifacts)


def test_file_artifact_provider_deduplicates_globs(tmp_path, caplog, artifact_provider):
    # Create multiple subdirectories with identical files
    for dirname in ("foo", "bar"):
        subdir = tmp_path / dirname
        subdir.mkdir()
        (subdir / "baz.rpm").touch()

    provider = artifact_provider(f"file:{tmp_path}/*/baz.rpm")
    artifacts = provider.artifacts

    assert len(artifacts) == 1
    assert artifacts[0].id == "baz.rpm"
    assert "Duplicate artifact" in caplog.text


def test_download_artifact(tmp_path, artifact_provider):
    # Test file download
    test_file = tmp_path / "foo.rpm"
    test_file.touch()
    file_provider = artifact_provider(f"file:{test_file}")
    guest = MagicMock()
    file_provider._download_artifact(file_provider.artifacts[0], guest, Path("/remote/foo.rpm"))
    guest.push.assert_called_once()

    # Test URL download
    url_provider = artifact_provider("file:https://example.com/foo.rpm")
    url_provider._download_artifact(url_provider.artifacts[0], guest, Path("/remote/foo.rpm"))
    guest.execute.assert_called_once()
