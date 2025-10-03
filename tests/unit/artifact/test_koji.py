import pytest

from tmt.steps.prepare.artifact.providers.koji import KojiArtifactProvider


@pytest.mark.integration
def test_koji_valid_build(root_logger):
    provider = KojiArtifactProvider("koji.build:2829512", root_logger)
    rpms = list(provider.list_artifacts())
    assert len(rpms) == 13


@pytest.mark.integration
def test_koji_valid_nvr(root_logger):
    provider = KojiArtifactProvider("koji.nvr:tmt-1.58.0-1.fc43", root_logger)
    rpms = list(provider.list_artifacts())
    assert len(rpms) == 13
    assert provider.build_id == 2829512  # Known build ID for this NVR


def test_koji_invalid_nvr(root_logger):
    from tmt.utils import GeneralError

    provider = KojiArtifactProvider("koji.nvr:nonexistent-1.0-1.fc43", root_logger)

    with pytest.raises(GeneralError, match="No build found for NVR 'nonexistent-1.0-1.fc43'."):
        _ = provider.build_id


@pytest.mark.integration
def test_koji_valid_task_id_that_produced_build(root_logger):
    provider = KojiArtifactProvider("koji.task:137451383", root_logger)
    rpms = list(provider.list_artifacts())
    assert provider.build_id == 2829512  # Known build ID for this task
    assert len(rpms) == 13


@pytest.mark.integration
def test_koji_valid_task_id_that_did_not_produce_build(root_logger):
    provider = KojiArtifactProvider("koji.task:137705547", root_logger)
    tasks = provider._get_task_children(137705547)
    assert len(tasks) == 13
    assert 137705547 in tasks  # The parent task itself should be included
    rpms = list(provider.list_artifacts())
    assert provider.build_id is None
    assert len(rpms) == 0
