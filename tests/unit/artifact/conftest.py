from unittest.mock import MagicMock, patch

import pytest

from tmt.steps.prepare import install
from tmt.steps.prepare.artifact import get_artifact_provider
from tmt.steps.prepare.artifact.providers import koji as koji_module
from tmt.steps.prepare.artifact.providers.brew import BrewArtifactProvider
from tmt.steps.prepare.artifact.providers.koji import KojiArtifactProvider


@pytest.fixture
def mock_pathinfo():
    mock_pathinfo = MagicMock()
    mock_pathinfo.work.return_value = "/default/work"
    mock_pathinfo.taskrelpath.side_effect = lambda tid: f"tasks/{tid}"
    return mock_pathinfo


@pytest.fixture
def mock_koji(mock_pathinfo):
    mock_koji = MagicMock()
    mock_koji.PathInfo.return_value = mock_pathinfo

    def mock_initialize_session(self, api_url=None, top_url=None):
        self._top_url = top_url or "http://koji.example.com/"
        self._api_url = api_url or "http://koji.example.com/kojihub"
        return MagicMock()

    with (
        patch.object(KojiArtifactProvider, "_initialize_session", mock_initialize_session),
        patch.object(koji_module, "koji", mock_koji),
    ):
        yield mock_koji


@pytest.fixture
def mock_brew(mock_koji):
    def mock_initialize_session(self, api_url=None, top_url=None):
        self._top_url = top_url or "http://brew.example.com/"
        self._api_url = api_url or "http://brew.example.com/brewhub"
        return MagicMock()

    with patch.object(BrewArtifactProvider, "_initialize_session", mock_initialize_session):
        yield mock_koji


@pytest.fixture
def artifact_provider(root_logger):
    def get_provider(provider_id: str, repository_priority: int = 50):
        provider_class = get_artifact_provider(provider_id)
        return provider_class(
            provider_id, repository_priority=repository_priority, logger=root_logger
        )

    return get_provider


@pytest.fixture
def mock_installer(monkeypatch):
    installer = MagicMock(spec=install.Copr)
    installer_class = MagicMock(return_value=installer)

    monkeypatch.setattr(
        'tmt.steps.prepare.install.get_installer_class',
        lambda _pm: installer_class,
    )

    return installer
