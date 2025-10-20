import pytest

from tmt.steps.prepare.artifact.providers.koji import KojiArtifactProvider


@pytest.mark.skip(reason="would be replaced by mocks")
@pytest.mark.integration
def test_koji_valid_build(root_logger):
    provider = KojiArtifactProvider("koji.build:2829512", root_logger)
    assert len(provider.artifacts) == 13


@pytest.mark.skip(reason="would be replaced by mocks")
@pytest.mark.integration
def test_koji_valid_nvr(root_logger):
    provider = KojiArtifactProvider("koji.nvr:tmt-1.58.0-1.fc43", root_logger)
    assert len(provider.artifacts) == 13
    assert provider.build_id == 2829512  # Known build ID for this NVR


@pytest.mark.skip(reason="would be replaced by mocks")
def test_koji_invalid_nvr(root_logger):
    from tmt.utils import GeneralError

    provider = KojiArtifactProvider("koji.nvr:nonexistent-1.0-1.fc43", root_logger)

    with pytest.raises(GeneralError, match=r"No build found for NVR 'nonexistent-1\.0-1\.fc43'\."):
        _ = provider.build_id


@pytest.mark.skip(reason="would be replaced by mocks")
@pytest.mark.integration
def test_koji_valid_task_id_actual_build(root_logger):
    provider = KojiArtifactProvider("koji.task:137451383", root_logger)
    assert provider.build_id == 2829512  # Known build ID for this task
    assert len(provider.artifacts) == 13


@pytest.mark.skip(reason="would be replaced by mocks")
@pytest.mark.integration
def test_koji_valid_task_id_scratch_build(root_logger):
    provider = KojiArtifactProvider("koji.task:137705547", root_logger)
    tasks = provider._get_task_children(137705547)
    assert len(tasks) == 13
    assert 137705547 in tasks  # The parent task itself should be included
    assert provider.build_id is None
    assert (
        provider.artifacts[0]._raw_artifact['url']
        == 'https://kojipkgs.fedoraproject.org/work/tasks/5553/137705553/python-scikit-build-core-0.11.5-5.fc44.src.rpm'
    )
    assert len(provider.artifacts) == 2
