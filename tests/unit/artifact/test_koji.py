import pytest

from tmt.steps.prepare.artifact.providers import RpmVersion
from tmt.steps.prepare.artifact.providers.koji import (
    KojiArtifactProvider,
    KojiBuild,
    KojiNvr,
    KojiTask,
)
from tmt.utils import GeneralError

from . import (
    MOCK_BUILD_ID_KOJI_BREW,
    MOCK_RPMS_KOJI,
    mock_call_api_for,
    mock_koji_brew_build_api_responses,
    mock_task_api_responses,
)


@pytest.fixture
def mock_call_api():
    with mock_call_api_for(KojiArtifactProvider) as mock:
        yield mock


def test_koji_valid_build(mock_koji, mock_call_api, artifact_provider):
    mock_koji_brew_build_api_responses(mock_call_api, MOCK_RPMS_KOJI)
    provider = artifact_provider(f"koji.build:{MOCK_BUILD_ID_KOJI_BREW}")
    assert isinstance(provider, KojiBuild)
    assert provider.build_id == MOCK_BUILD_ID_KOJI_BREW
    assert len(provider.artifacts) == 13


def test_koji_valid_nvr(mock_koji, mock_call_api, artifact_provider):
    mock_koji_brew_build_api_responses(mock_call_api, MOCK_RPMS_KOJI)
    provider = artifact_provider("koji.nvr:tmt-1.58.0-1.fc43")
    assert isinstance(provider, KojiNvr)
    assert provider.build_id == MOCK_BUILD_ID_KOJI_BREW
    assert len(provider.artifacts) == 13


def test_koji_invalid_nvr(mock_koji, mock_call_api, artifact_provider):
    mock_call_api.return_value = None
    provider = artifact_provider("koji.nvr:nonexistent-1.0-1.fc43")
    assert isinstance(provider, KojiNvr)
    with pytest.raises(GeneralError, match=r"No build found for NVR 'nonexistent-1\.0-1\.fc43'\."):
        _ = provider.build_id


def test_koji_valid_task_id_actual_build(mock_koji, mock_call_api, artifact_provider):
    mock_task_api_responses(mock_call_api, MOCK_RPMS_KOJI, has_build=True)
    provider = artifact_provider("koji.task:137451383")
    assert isinstance(provider, KojiTask)
    assert provider.build_id == MOCK_BUILD_ID_KOJI_BREW
    assert len(provider.artifacts) == 13


def test_koji_valid_task_id_scratch_build(mock_koji, mock_call_api, artifact_provider):
    task_id = 137705547
    mock_task_api_responses(mock_call_api, has_build=False)

    provider = artifact_provider(f"koji.task:{task_id}")
    assert isinstance(provider, KojiTask)
    provider._top_url = "http://koji.example.com"
    tasks = list(provider._get_task_children(task_id))

    assert len(tasks) == 2
    assert task_id in tasks
    assert provider.build_id is None
    assert len(provider.artifacts) == 2


@pytest.mark.parametrize(
    ("rpm_meta", "expected"),
    [
        (
            {"name": "bash", "version": "5.1.8", "release": "6.el9", "arch": "x86_64"},
            {
                "name": "bash",
                "epoch": 0,
                "version": "5.1.8",
                "release": "6.el9",
                "arch": "x86_64",
                "nvra": "bash-5.1.8-6.el9.x86_64",
            },
        ),
        (
            {
                "name": "docker-ce",
                "version": "20.10.7",
                "release": "3.el8",
                "arch": "x86_64",
                "epoch": 1,
            },
            {
                "name": "docker-ce",
                "epoch": 1,
                "version": "20.10.7",
                "release": "3.el8",
                "arch": "x86_64",
                "nvra": "docker-ce-20.10.7-3.el8.x86_64",
            },
        ),
        (
            {
                "name": "tmt+export-polarion",
                "version": "1.61.0.dev17+gf29b2e83e",
                "release": "1.fc41",
                "arch": "x86_64",
            },
            {
                "name": "tmt+export-polarion",
                "epoch": 0,
                "version": "1.61.0.dev17+gf29b2e83e",
                "release": "1.fc41",
                "arch": "x86_64",
                "nvra": "tmt+export-polarion-1.61.0.dev17+gf29b2e83e-1.fc41.x86_64",
            },
        ),
    ],
)
def test_version_from_rpm_meta_parsing(rpm_meta, expected):
    version = RpmVersion.from_rpm_meta(rpm_meta)

    assert version.name == expected["name"]
    assert version.epoch == expected["epoch"]
    assert version.version == expected["version"]
    assert version.release == expected["release"]
    assert version.arch == expected["arch"]
    assert version.nvra == expected["nvra"]
    assert str(version) == expected["nvra"]
