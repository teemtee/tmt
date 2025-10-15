import pytest

from tmt.steps.prepare.artifact.providers.koji import KojiArtifactProvider


@pytest.mark.integration
def test_koji_valid_build(root_logger):
    provider = KojiArtifactProvider("koji.build:2829512", root_logger)
    assert len(provider.artifacts) == 13


@pytest.mark.integration
def test_koji_valid_nvr(root_logger):
    provider = KojiArtifactProvider("koji.nvr:tmt-1.58.0-1.fc43", root_logger)
    assert len(provider.artifacts) == 13
    assert provider.build_id == 2829512  # Known build ID for this NVR


def test_koji_invalid_nvr(root_logger):
    from tmt.utils import GeneralError

    provider = KojiArtifactProvider("koji.nvr:nonexistent-1.0-1.fc43", root_logger)

    with pytest.raises(GeneralError, match=r"No build found for NVR 'nonexistent-1\.0-1\.fc43'\."):
        _ = provider.build_id


@pytest.mark.integration
def test_koji_valid_task_id_actual_build(root_logger):
    provider = KojiArtifactProvider("koji.task:137451383", root_logger)
    assert provider.build_id == 2829512  # Known build ID for this task
    assert len(provider.artifacts) == 13


@pytest.mark.integration
def test_koji_valid_task_id_scratch_build(root_logger):
    task_id = 137705547
    provider = KojiArtifactProvider(f"koji.task:{task_id}", root_logger)
    tasks = provider._get_task_children(task_id)

    assert len(tasks) == 13
    assert task_id in tasks
    assert provider.build_id is None
    assert len(provider.artifacts) == 2
