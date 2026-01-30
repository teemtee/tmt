import pytest

from tmt.steps.prepare.artifact.providers.brew import BrewArtifactProvider, BrewBuild, BrewTask
from tmt.utils import GeneralError

from . import (
    MOCK_BUILD_ID_KOJI_BREW,
    MOCK_RPMS_BREW,
    mock_call_api_for,
    mock_koji_brew_build_api_responses,
    mock_task_api_responses,
)


@pytest.fixture
def mock_call_api():
    with mock_call_api_for(BrewArtifactProvider) as mock:
        yield mock


def test_brew_valid_build(mock_brew, mock_call_api, artifact_provider):
    mock_koji_brew_build_api_responses(mock_call_api, MOCK_RPMS_BREW)
    provider = artifact_provider(f"brew.build:{MOCK_BUILD_ID_KOJI_BREW}")
    assert isinstance(provider, BrewBuild)
    assert provider.build_id == MOCK_BUILD_ID_KOJI_BREW
    assert len(provider.artifacts) == 21


def test_brew_valid_draft_build(mock_brew, mock_call_api, artifact_provider):
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
        lambda method, *a, **kw: mock_rpms
        if method == "listBuildRPMs"
        else {"id": draft_id, "package_name": "test-package"}
    )

    provider = artifact_provider(f"brew.build:{draft_id}")
    assert isinstance(provider, BrewBuild)
    assert len(provider.artifacts) == 2
    assert any(f"draft_{draft_id}" in a.location for a in provider.artifacts)


def test_brew_valid_task_id_scratch_build(mock_brew, mock_call_api, artifact_provider):
    task_id = 69111304
    mock_task_api_responses(mock_call_api, has_build=False)

    provider = artifact_provider(f"brew.task:{task_id}")
    assert isinstance(provider, BrewTask)
    tasks = list(provider._get_task_children(task_id))

    assert len(tasks) == 2
    assert task_id in tasks
    assert provider.build_id is None
    assert len(provider.artifacts) == 2
