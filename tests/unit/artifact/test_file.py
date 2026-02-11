from unittest.mock import MagicMock

import pytest

from tmt.log import Logger
from tmt.steps.prepare.artifact.providers.file import (
    PackageAsFileArtifactProvider,
)
from tmt.utils import Path


@pytest.mark.parametrize(
    ("pattern", "expected_names"),
    [
        ("foo-1.0-1.fc43.x86_64.rpm", {"foo-1.0-1.fc43.x86_64"}),
        ("docker-ce-1:20.10.7-3.el8.x86_64.rpm", {"docker-ce-1:20.10.7-3.el8.x86_64"}),
        ("bash-5.1.8-6.el9.x86_64.rpm", {"bash-5.1.8-6.el9.x86_64"}),
        (
            "tmt+export-polarion-1.61.0.dev17+gf29b2e83e-1.fc41.x86_64.rpm",
            {"tmt+export-polarion-1.61.0.dev17+gf29b2e83e-1.fc41.x86_64"},
        ),
        (
            "keylime-agent-rust-push-debuginfo-0.2.3-1.fc41.x86_64.rpm",
            {"keylime-agent-rust-push-debuginfo-0.2.3-1.fc41.x86_64"},
        ),
        ("example-0:1.0-1.noarch.rpm", {"example-0:1.0-1.noarch"}),
        ("example-5.1.8-6.el9.src.rpm", {"example-5.1.8-6.el9.src"}),
        ("package-*.rpm", {f"package-{i}-1.0-1.fc43.x86_64" for i in range(3)}),
    ],
)
def test_file_artifact_provider_patterns(tmp_path, pattern, expected_names, artifact_provider):
    if "*" in pattern:
        for i in range(3):
            (tmp_path / f"package-{i}-1.0-1.fc43.x86_64.rpm").touch()
    else:
        (tmp_path / pattern).touch()

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
        (subdir / "baz-1.0-1.fc43.x86_64.rpm").touch()

    provider = artifact_provider(f"file:{tmp_path}/*/baz-1.0-1.fc43.x86_64.rpm")
    artifacts = provider.artifacts

    assert len(artifacts) == 1
    assert artifacts[0].id == "baz-1.0-1.fc43.x86_64"
    assert "Duplicate artifact" in caplog.text


def test_download_artifact(tmp_path, artifact_provider):
    # Test file download
    test_file = tmp_path / "foo-1.0-1.fc43.x86_64.rpm"
    test_file.touch()
    file_provider = artifact_provider(f"file:{test_file}")
    guest = MagicMock()
    file_provider._download_artifact(
        file_provider.artifacts[0],
        guest,
        Path("/remote/foo-1.0-1.fc43.x86_64.rpm"),
    )
    guest.push.assert_called_once()

    # Test URL download
    url_provider = artifact_provider("file:https://example.com/foo-1.0-1.fc43.x86_64.rpm")
    url_provider._download_artifact(
        url_provider.artifacts[0],
        guest,
        Path("/remote/foo-1.0-1.fc43.x86_64.rpm"),
    )
    guest.execute.assert_called_once()
