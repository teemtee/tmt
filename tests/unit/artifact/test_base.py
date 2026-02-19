import re
from unittest.mock import MagicMock

import pytest

import tmt.utils
from tmt.steps.prepare.artifact import PrepareArtifact
from tmt.steps.prepare.artifact.providers import ArtifactInfo, ArtifactProvider, Version


class MockProvider(ArtifactProvider):
    def _extract_provider_id(self, raw_provider_id: str) -> str:
        return raw_provider_id.split(":", 1)[1]

    @property
    def artifacts(self):
        return [
            ArtifactInfo(
                version=Version(name="mock", version="1.0", release="1", arch="x86_64"),
                location="http://example.com/mock-1.0-1.x86_64.rpm",
                provider=self,
            )
        ]

    def _download_artifact(self, artifact, guest, destination):
        destination.write_text("ok")

    def contribute_to_shared_repo(
        self, guest, source_path, shared_repo_dir, exclude_patterns=None
    ):
        pass


@pytest.fixture
def mock_provider(root_logger):
    return MockProvider("mock:123", repository_priority=50, logger=root_logger)


def test_filter_artifacts(mock_provider):
    artifacts = list(mock_provider._filter_artifacts([re.compile("mock")]))
    assert artifacts == []


def test_download_artifacts(tmp_path, root_logger, mock_provider):
    guest = MagicMock()

    paths = mock_provider.fetch_contents(guest, tmp_path, [])
    file_path = tmp_path / "mock-1.0-1.x86_64.rpm"
    assert file_path in paths
    assert file_path.exists()
    assert file_path.read_text() == "ok"


def test_persist_artifact_metadata(tmp_path, mock_provider):
    prepare = MagicMock()
    prepare.plan_workdir = tmp_path
    prepare.ARTIFACTS_METADATA_FILENAME = 'artifacts.yaml'

    PrepareArtifact._persist_artifact_metadata(prepare, [mock_provider])

    # Verify YAML
    yaml_file = tmp_path / "artifacts.yaml"
    assert yaml_file.exists()

    content = tmt.utils.from_yaml(yaml_file.read_text())

    assert len(content["providers"]) == 1

    provider_data = content["providers"][0]
    assert provider_data["id"] == "mock:123"
    assert len(provider_data["artifacts"]) == 1

    artifact = provider_data["artifacts"][0]
    expected = {
        "version": {
            "name": "mock",
            "version": "1.0",
            "release": "1",
            "arch": "x86_64",
            "epoch": 0,
        },
        "nvra": "mock-1.0-1.x86_64",
        "location": "http://example.com/mock-1.0-1.x86_64.rpm",
    }
    assert artifact == expected
