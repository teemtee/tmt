from unittest.mock import MagicMock, patch

import pytest

from tmt.steps.prepare.artifact import get_artifact_provider
from tmt.steps.prepare.artifact.providers import koji as koji_module
from tmt.steps.prepare.artifact.providers.brew import BrewArtifactProvider
from tmt.steps.prepare.artifact.providers.copr_repository import CoprRepositoryProvider
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

    with (
        patch.object(KojiArtifactProvider, "_initialize_session", return_value=MagicMock()),
        patch.object(
            KojiArtifactProvider,
            "_rpm_url",
            side_effect=lambda rpm: f"http://koji.example.com/{rpm['name']}.rpm",
        ),
        patch.object(koji_module, "koji", mock_koji),
    ):
        yield mock_koji


@pytest.fixture
def mock_brew(mock_koji):
    with (
        patch.object(BrewArtifactProvider, "_initialize_session", return_value=MagicMock()),
        patch.object(
            BrewArtifactProvider,
            "_rpm_url",
            side_effect=lambda rpm: f"http://brew.example.com/{rpm['name']}.rpm",
        ),
    ):
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
def mock_copr_class():
    with patch('tmt.steps.prepare.install.Copr') as mock_copr:
        yield mock_copr
