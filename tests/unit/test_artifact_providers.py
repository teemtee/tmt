import re
from unittest.mock import MagicMock

import pytest

from tmt.steps.prepare.brand_new_allmighty_install.providers import (
    ArtifactInfo,
    ArtifactProvider,
)
from tmt.steps.prepare.brand_new_allmighty_install.providers.koji_provider import (
    KojiProvider,
)


@pytest.fixture
def logger():
    """Provide a MagicMock logger for tests."""
    return MagicMock()


class MockArtifactInfo(ArtifactInfo):
    @property
    def name(self):
        return "mock.rpm"

    @property
    def location(self):
        return "http://example.com/mock.rpm"


class MockProvider(ArtifactProvider[MockArtifactInfo]):
    def _parse_artifact_id(self, artifact_id: str) -> str:
        return artifact_id.split(":", 1)[1]

    def list_artifacts(self):
        yield MockArtifactInfo(_raw_artifact={}, id=1)

    def _download_artifact(self, artifact, guest, destination):
        destination.write_text("ok")


def test_filter_artifacts(logger):
    provider = MockProvider(logger, "mock:123")
    artifacts = list(provider._filter_artifacts([re.compile("mock")]))
    assert artifacts == []


def test_download_artifacts(tmp_path, logger):
    guest = MagicMock()
    provider = MockProvider(logger, "mock:123")

    paths = provider.download_artifacts(guest, tmp_path, [])
    assert (tmp_path / "mock.rpm") in paths
    assert (tmp_path / "mock.rpm").exists()


def test_parse_artifact_id_valid():
    provider = KojiProvider(MagicMock(), "koji.build:12345")
    assert provider.artifact_id == "12345"


@pytest.mark.parametrize("invalid_id", ["koji.task:111", "koji.build:abc"])
def test_parse_artifact_id_invalid(invalid_id):
    with pytest.raises(ValueError, match="Invalid artifact ID format"):
        KojiProvider(MagicMock(), invalid_id)


def test_call_api_success():
    provider = KojiProvider(MagicMock(), "koji.build:123")
    provider._session = MagicMock()
    provider._session.some_method.return_value = "ok"

    result = provider._call_api("some_method", 1, 2)
    assert result == "ok"
