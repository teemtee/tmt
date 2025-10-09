import re
from unittest.mock import MagicMock

from tmt.steps.prepare.artifact.providers import ArtifactInfo, ArtifactProvider


class MockArtifactInfo(ArtifactInfo):
    @property
    def id(self) -> str:
        return "mock.rpm"

    @property
    def location(self) -> str:
        return "http://example.com/mock.rpm"


class MockProvider(ArtifactProvider[MockArtifactInfo]):
    def _extract_provider_id(self, raw_provider_id: str) -> str:
        return raw_provider_id.split(":", 1)[1]

    @property
    def artifacts(self):
        return [MockArtifactInfo(_raw_artifact={})]

    def _download_artifact(self, artifact, guest, destination):
        destination.write_text("ok")


def test_filter_artifacts(root_logger):
    provider = MockProvider("mock:123", root_logger)

    artifacts = list(provider._filter_artifacts([re.compile("mock")]))
    assert artifacts == []


def test_download_artifacts(tmp_path, root_logger):
    guest = MagicMock()
    provider = MockProvider("mock:123", root_logger)

    paths = provider.fetch_contents(guest, tmp_path, [])

    file_path = tmp_path / "mock.rpm"
    assert file_path in paths
    assert file_path.exists()
    assert file_path.read_text() == "ok"
