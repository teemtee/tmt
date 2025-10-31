import pytest

from tmt.steps.prepare.artifact.providers.koji import KojiArtifactProvider
from tmt.utils import GeneralError

from . import (
    MOCK_BUILD_ID,
    MOCK_RPMS_KOJI,
    mock_build_api_responses,
    mock_call_api_for,
    mock_task_api_responses,
)


@pytest.fixture
def mock_call_api():
    with mock_call_api_for(KojiArtifactProvider) as mock:
        yield mock


def test_koji_valid_build(mock_koji, mock_call_api, root_logger):
    mock_build_api_responses(mock_call_api, MOCK_BUILD_ID, MOCK_RPMS_KOJI)
    provider = KojiArtifactProvider(f"koji.build:{MOCK_BUILD_ID}", root_logger)
    assert provider.build_id == MOCK_BUILD_ID
    assert len(provider.artifacts) == 13


def test_koji_valid_nvr(mock_koji, mock_call_api, root_logger):
    mock_build_api_responses(mock_call_api, MOCK_BUILD_ID, MOCK_RPMS_KOJI)
    provider = KojiArtifactProvider("koji.nvr:tmt-1.58.0-1.fc43", root_logger)
    assert provider.build_id == MOCK_BUILD_ID
    assert len(provider.artifacts) == 13


def test_koji_invalid_nvr(mock_koji, mock_call_api, root_logger):
    mock_call_api.return_value = None
    provider = KojiArtifactProvider("koji.nvr:nonexistent-1.0-1.fc43", root_logger)
    with pytest.raises(GeneralError, match=r"No build found for NVR 'nonexistent-1\.0-1\.fc43'\."):
        _ = provider.build_id


def test_koji_valid_task_id_actual_build(mock_koji, mock_call_api, root_logger):
    mock_task_api_responses(mock_call_api, MOCK_BUILD_ID, MOCK_RPMS_KOJI, has_build=True)
    provider = KojiArtifactProvider("koji.task:137451383", root_logger)
    assert provider.build_id == MOCK_BUILD_ID
    assert len(provider.artifacts) == 13


def test_koji_valid_task_id_scratch_build(mock_koji, mock_call_api, root_logger):
    task_id = 137705547
    mock_task_api_responses(mock_call_api, has_build=False)

    provider = KojiArtifactProvider(f"koji.task:{task_id}", root_logger)
    provider._top_url = "http://koji.example.com"
    tasks = list(provider._get_task_children(task_id))

    assert len(tasks) == 2
    assert task_id in tasks
    assert provider.build_id is None
    assert len(provider.artifacts) == 2
