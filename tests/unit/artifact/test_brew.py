import pytest

from tmt.steps.prepare.artifact.providers.brew import BrewArtifactProvider
from tmt.utils import GeneralError

from . import (
    MOCK_BUILD_ID,
    MOCK_RPMS_BREW,
    mock_build_api_responses,
    mock_call_api_for,
    mock_task_api_responses,
)


@pytest.fixture
def mock_call_api():
    with mock_call_api_for(BrewArtifactProvider) as mock:
        yield mock


def test_brew_valid_build(mock_brew, mock_call_api, root_logger):
    mock_build_api_responses(mock_call_api, MOCK_BUILD_ID, MOCK_RPMS_BREW)
    provider = BrewArtifactProvider(f"brew.build:{MOCK_BUILD_ID}", root_logger)
    assert provider.build_id == MOCK_BUILD_ID
    assert len(provider.artifacts) == 21


def test_brew_valid_draft_build(mock_brew, mock_call_api, root_logger):
    draft_id = 3525300
    mock_rpms = [
        {
            "name": f"draft_{draft_id}_pkg{i}",
            "version": "1.0",
            "release": "1.el9",
            "arch": "x86_64",
        }
        for i in range(2)
    ]
    mock_call_api.side_effect = (
        lambda method, *a, **kw: mock_rpms if method == "listBuildRPMs" else {"id": draft_id}
    )

    provider = BrewArtifactProvider(f"brew.build:{draft_id}", root_logger)
    assert len(provider.artifacts) == 2
    assert any(f"draft_{draft_id}" in a.location for a in provider.artifacts)


def test_brew_valid_task_id_scratch_build(mock_brew, mock_call_api, root_logger):
    task_id = 69111304
    mock_task_api_responses(mock_call_api, has_build=False)

    provider = BrewArtifactProvider(f"brew.task:{task_id}", root_logger)
    provider._top_url = "http://brew.example.com"
    tasks = list(provider._get_task_children(task_id))

    assert len(tasks) == 2
    assert task_id in tasks
    assert provider.build_id is None
    assert len(provider.artifacts) == 2
