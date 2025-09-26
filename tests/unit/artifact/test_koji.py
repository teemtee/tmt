from unittest.mock import MagicMock, patch

import pytest

from tmt.steps.prepare.artifact.providers.koji import KojiArtifactProvider


@pytest.fixture
def koji_provider(root_logger):
    """Return a KojiArtifactProvider with a stable build ID for testing."""
    return KojiArtifactProvider(root_logger, build_id=12345)


def test_parse_artifact_id_valid(koji_provider):
    assert koji_provider.artifact_id == 12345


def test_resolve_artifact_id_nvr(root_logger):
    with patch.object(KojiArtifactProvider, "_call_api", return_value={"id": 42}):
        provider = KojiArtifactProvider(root_logger, nvr="tmt-1.0.0-1.fc40")
        assert provider.artifact_id == 42


def test_call_api_success(koji_provider):
    koji_provider._session = MagicMock()
    koji_provider._session.some_method.return_value = "ok"

    result = koji_provider._call_api("some_method", 1, 2)
    assert result == "ok"


def test_list_artifacts_returns_rpm_artifacts(koji_provider):
    koji_provider._rpm_list = [
        {"nvr": "foo-1.0-1", "arch": "x86_64", "name": "foo", "version": "1.0", "release": "1"}
    ]
    artifacts = list(koji_provider.list_artifacts())
    assert len(artifacts) == 1
    artifact = artifacts[0]
    assert artifact.id.startswith("foo-1.0-1")
    assert "kojipkgs.fedoraproject.org" in artifact.location


@pytest.mark.integration
def test_koji_real_build(koji_provider):
    artifacts = list(koji_provider.list_artifacts())
    assert len(artifacts) > 0


@pytest.mark.integration
def test_koji_real_nvr(root_logger):
    provider = KojiArtifactProvider(root_logger, nvr="tmt-1.58.0-1.fc43")
    artifacts = list(provider.list_artifacts())
    assert len(artifacts) > 0
    assert provider.artifact_id == 2829512  # Known build ID for this NVR
