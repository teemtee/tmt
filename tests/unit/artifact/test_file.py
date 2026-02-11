from unittest.mock import MagicMock

import pytest

from tmt.log import Logger
from tmt.steps.prepare.artifact.providers import RpmVersion
from tmt.steps.prepare.artifact.providers.file import (
    PackageAsFileArtifactProvider,
)
from tmt.utils import Path


@pytest.mark.parametrize(
    ("pattern", "expected_names"),
    [
        ("foo-1.0-1.fc43.x86_64.rpm", {"foo-1.0-1.fc43.x86_64"}),
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


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        (
            "bash-5.1.8-6.el9.x86_64.rpm",
            {
                "name": "bash",
                "epoch": 0,
                "version": "5.1.8",
                "release": "6.el9",
                "arch": "x86_64",
                "nvra": "bash-5.1.8-6.el9.x86_64",
            },
        ),
        (
            "tmt+export-polarion-1.61.0.dev17+gf29b2e83e-1.fc41.x86_64.rpm",
            {
                "name": "tmt+export-polarion",
                "epoch": 0,
                "version": "1.61.0.dev17+gf29b2e83e",
                "release": "1.fc41",
                "arch": "x86_64",
                "nvra": "tmt+export-polarion-1.61.0.dev17+gf29b2e83e-1.fc41.x86_64",
            },
        ),
    ],
)
def test_version_from_filename_parsing(filename, expected):
    version = RpmVersion.from_filename(filename)

    assert version.name == expected["name"]
    assert version.epoch == expected["epoch"]
    assert version.version == expected["version"]
    assert version.release == expected["release"]
    assert version.arch == expected["arch"]
    assert version.nvra == expected["nvra"]
    assert str(version) == expected["nvra"]
