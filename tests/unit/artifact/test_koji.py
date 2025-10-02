import pytest

from tmt.steps.prepare.artifact.providers.koji import KojiArtifactProvider


@pytest.mark.integration
def test_koji_valid_build(root_logger):
    provider = KojiArtifactProvider(root_logger, artifact_id="koji.build:2829512")
    rpms = list(provider.list_artifacts())
    assert len(rpms) == 13


@pytest.mark.integration
def test_koji_valid_nvr(root_logger):
    provider = KojiArtifactProvider(root_logger, artifact_id="koji.nvr:tmt-1.58.0-1.fc43")
    rpms = list(provider.list_artifacts())
    assert len(rpms) == 13
    assert provider.build_id == 2829512  # Known build ID for this NVR


def test_koji_invalid_nvr(root_logger):
    from tmt.utils import GeneralError

    provider = KojiArtifactProvider(root_logger, artifact_id="koji.nvr:nonexistent-1.0-1.fc43")

    with pytest.raises(GeneralError, match="No build found for NVR 'nonexistent-1.0-1.fc43'."):
        _ = provider.build_id


@pytest.mark.integration
def test_koji_valid_task_id_that_produced_build(root_logger):
    provider = KojiArtifactProvider(root_logger, artifact_id="koji.task:137451383")
    rpms = list(provider.list_artifacts())
    assert provider.build_id == 2829512  # Known build ID for this task
    assert len(rpms) == 13


@pytest.mark.integration
def test_koji_valid_task_id_that_did_not_produce_build(root_logger):
    provider = KojiArtifactProvider(root_logger, artifact_id="koji.task:137451529")
    rpms = list(provider.list_artifacts())
    assert provider.build_id is None
    assert len(rpms) == 13
