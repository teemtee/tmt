import pytest

from tmt.steps.prepare.artifact.providers.copr_build import CoprBuildArtifactProvider
from tmt.utils import GeneralError

from . import MOCK_BUILD_ID_COPR, MOCK_BUILD_ID_PULP, MOCK_RPMS_PULP, mock_copr_build_api_responses


def test_copr_valid_build_non_pulp(artifact_provider):
    provider = artifact_provider(f"copr.build:{MOCK_BUILD_ID_COPR}:fedora-41-x86_64")
    provider._session = mock_copr_build_api_responses(provider._session)
    assert isinstance(provider, CoprBuildArtifactProvider)
    assert provider.build_id == MOCK_BUILD_ID_COPR
    assert len(provider.artifacts) == 14
    assert not provider.is_pulp

    for artifact in provider.artifacts:
        assert artifact._raw_artifact["url"].startswith(provider.result_url)


def test_copr_pulp_build(artifact_provider, monkeypatch):
    provider = artifact_provider(f"copr.build:{MOCK_BUILD_ID_PULP}:fedora-41-x86_64")
    provider._session = mock_copr_build_api_responses(provider._session, storage="pulp")

    monkeypatch.setattr(provider, "_fetch_results_json", lambda: MOCK_RPMS_PULP)

    artifacts = provider.artifacts
    assert provider.is_pulp
    assert len(artifacts) == len(MOCK_RPMS_PULP)

    for artifact in artifacts:
        first_letter = artifact._raw_artifact["name"][0]
        assert f"/Packages/{first_letter}/" in artifact._raw_artifact["url"]


def test_copr_invalid_build_id(artifact_provider):
    with pytest.raises(ValueError, match=r"Invalid provider id 'invalid_id:fedora-41-x86_64'\."):
        _ = artifact_provider("copr.build:invalid_id:fedora-41-x86_64")


def test_copr_invalid_chroot(artifact_provider):
    provider = artifact_provider(f"copr.build:{MOCK_BUILD_ID_COPR}:invalid_chroot")
    provider._session = mock_copr_build_api_responses(provider._session)
    with pytest.raises(
        GeneralError, match=r"Chroot 'invalid_chroot' not found in build '9820798'\."
    ):
        _ = provider.artifacts
