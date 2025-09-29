import pytest

from tmt.steps.prepare.artifact.providers.koji import KojiArtifactProvider, RpmArtifactInfo


@pytest.mark.integration
def test_koji_valid_build(root_logger):
    provider = KojiArtifactProvider(root_logger, build_id=2829512)
    rpms = list(provider.list_artifacts())
    assert len(rpms) == 13


@pytest.mark.integration
def test_koji_valid_nvr(root_logger):
    provider = KojiArtifactProvider(root_logger, nvr="tmt-1.58.0-1.fc43")
    rpms = list(provider.list_artifacts())
    assert len(rpms) == 13
    assert provider.build_id == 2829512  # Known build ID for this NVR


def test_koji_invalid_nvr(root_logger):
    from tmt.utils import GeneralError

    with pytest.raises(GeneralError):
        KojiArtifactProvider(root_logger, nvr="nonexistent-1.0-1.fc43")


@pytest.mark.integration
def test_koji_valid_task_id(root_logger):
    provider = KojiArtifactProvider(root_logger, task_id=137451529)
    rpms = list(provider.list_artifacts())
    assert len(rpms) == 13


def test_provider_without_identifier(root_logger):
    with pytest.raises(
        ValueError, match="Exactly one of build_id, task_id, or nvr must be provided."
    ):
        KojiArtifactProvider(root_logger)


def test_rpm_artifactinfo_from_filename_valid():
    filename = "tmt-1.58.0-1.fc41.noarch.rpm"
    artifact = RpmArtifactInfo.from_filename(filename)

    assert artifact.id == "tmt-1.58.0-1.fc41.noarch.rpm"
    assert artifact._raw_artifact["name"] == "tmt"
    assert artifact._raw_artifact["version"] == "1.58.0"
    assert artifact._raw_artifact["release"] == "1.fc41"
    assert artifact._raw_artifact["arch"] == "noarch"
    assert artifact._raw_artifact["nvr"] == "tmt-1.58.0-1.fc41"


def test_rpm_artifactinfo_from_filename_invalid():
    with pytest.raises(
        ValueError, match=r"Invalid RPM filename format: 'not-a-real-rpm-file\.txt'"
    ):
        RpmArtifactInfo.from_filename("not-a-real-rpm-file.txt")
