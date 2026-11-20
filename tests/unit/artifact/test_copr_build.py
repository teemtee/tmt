import pytest

from tmt.steps.prepare.artifact.providers.copr_build import CoprBuildArtifactProvider

from . import MOCK_BUILD_ID_COPR, MOCK_COPR_RPM_URL, mock_copr_build_api_responses


def test_copr_valid_build_non_pulp(artifact_provider):
    provider = artifact_provider(f"copr.build:{MOCK_BUILD_ID_COPR}:fedora-41-x86_64")
    provider._session = mock_copr_build_api_responses(provider._session)
    assert isinstance(provider, CoprBuildArtifactProvider)
    assert provider.build_id == MOCK_BUILD_ID_COPR
    assert len(provider.artifacts) == 14

    for artifact in provider.artifacts:
        assert artifact.location.startswith(MOCK_COPR_RPM_URL)


def test_copr_invalid_build_id(artifact_provider):
    with pytest.raises(ValueError, match=r"Invalid provider id 'invalid_id:fedora-41-x86_64'\."):
        _ = artifact_provider("copr.build:invalid_id:fedora-41-x86_64")
