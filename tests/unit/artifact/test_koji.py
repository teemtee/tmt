from unittest.mock import MagicMock, patch

import pytest

from tmt.steps.prepare.artifact.providers.koji import KojiArtifactProvider


@pytest.fixture
def koji_provider(root_logger):
    """Return a KojiArtifactProvider with a stable build ID for testing."""
    return KojiArtifactProvider(root_logger, "koji.build:12345")


# --- Tests ---
def test_parse_artifact_id_valid(koji_provider):
    assert koji_provider.artifact_id == "12345"


@pytest.mark.parametrize("invalid_artifact_id", ["koji.task:111", "koji.build:abc"])
def test_parse_artifact_id_invalid(root_logger, invalid_artifact_id):
    with pytest.raises(ValueError, match="Invalid artifact ID format"):
        KojiArtifactProvider(root_logger, invalid_artifact_id)


def test_call_api_success(koji_provider):
    koji_provider._session = MagicMock()
    koji_provider._session.some_method.return_value = "ok"

    result = koji_provider._call_api("some_method", 1, 2)
    assert result == "ok"


def test_fetch_rpms_populates_list(root_logger):
    rpm_data = [{"name": "foo", "version": "1.x", "release": "1", "nvr": "foo-1.x-1"}]

    with patch.object(KojiArtifactProvider, "_call_api", return_value=rpm_data) as mock_call:
        provider = KojiArtifactProvider(root_logger, "koji.build:123")
        assert provider._rpm_list == rpm_data
        mock_call.assert_called_once_with("listBuildRPMs", 123)


@pytest.mark.integration
def test_koji_real_build(koji_provider):
    artifacts = list(koji_provider.list_artifacts())
    assert len(artifacts) > 0
