import pytest

from tmt.steps.prepare.artifact.providers.brew import BrewArtifactProvider


@pytest.mark.integration
def test_brew_valid_build(root_logger):
    provider = BrewArtifactProvider("brew.build:3866328", root_logger)
    assert len(provider.artifacts) == 21


@pytest.mark.integration
def test_brew_valid_draft_build(root_logger):
    provider = BrewArtifactProvider("brew.build:3525300", root_logger)
    assert len(provider.artifacts) == 2
    assert any(
        "draft_3525300" in artifact._raw_artifact['url'] for artifact in provider.artifacts
    ), "No artifact URL contains 'draft_3525300'"


@pytest.mark.integration
def test_brew_valid_nvr(root_logger):
    provider = BrewArtifactProvider("brew.nvr:unixODBC-2.3.12-1.el9", root_logger)
    assert len(provider.artifacts) == 21
    assert provider.build_id == 3866328  # Known build ID for this NVR


def test_brew_invalid_nvr(root_logger):
    from tmt.utils import GeneralError

    provider = BrewArtifactProvider("brew.nvr:nonexistent-1.0-1.fc43", root_logger)

    with pytest.raises(GeneralError, match=r"No build found for NVR 'nonexistent-1\.0-1\.fc43'\."):
        _ = provider.build_id


@pytest.mark.integration
def test_brew_valid_task_id_actual_build(root_logger):
    provider = BrewArtifactProvider("brew.task:69098388", root_logger)
    assert provider.build_id == 3866328  # Known build ID for this task
    assert len(provider.artifacts) == 21


@pytest.mark.integration
def test_brew_valid_task_id_scratch_build(root_logger):
    task_id = 69111304
    provider = BrewArtifactProvider(f"brew.task:{task_id}", root_logger)
    tasks = list(provider._get_task_children(task_id))

    assert len(tasks) == 11
    assert task_id in tasks
    assert provider.build_id is None
    assert len(provider.artifacts) == 12
