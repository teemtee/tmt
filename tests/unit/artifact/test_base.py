import re
from unittest.mock import MagicMock

from tmt.steps.prepare.artifact.providers import ArtifactProvider
from tmt.steps.prepare.artifact.providers.info import ArtifactInfo


class MockArtifactInfo(ArtifactInfo):
    @property
    def id(self) -> str:
        return "mock.rpm"

    @property
    def location(self) -> str:
        return "http://example.com/mock.rpm"


class MockProvider(ArtifactProvider[MockArtifactInfo]):
    def _parse_artifact_id(self, artifact_id: str) -> str:
        return artifact_id.split(":", 1)[1]

    def list_artifacts(self):
        yield MockArtifactInfo(_raw_artifact={})

    def _download_artifact(self, artifact, guest, destination):
        destination.write_text("ok")


def test_filter_artifacts(root_logger):
    provider = MockProvider(root_logger, "mock:123")

    artifacts = list(provider._filter_artifacts([re.compile("mock")]))
    assert artifacts == []


def test_download_artifacts(tmp_path, root_logger):
    guest = MagicMock()
    provider = MockProvider(root_logger, "mock:123")

    paths = provider.download_artifacts(guest, tmp_path, [])

    file_path = tmp_path / "mock.rpm"
    assert file_path in paths
    assert file_path.exists()
    assert file_path.read_text() == "ok"
