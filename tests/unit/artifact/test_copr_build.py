from unittest.mock import MagicMock

import pytest
import pytest_mock

from tmt.steps.prepare.artifact.providers.copr_build import CoprBuildArtifactProvider
from tmt.utils import GeneralError

MOCK_BUILD_ID_COPR = 9820798
MOCK_COPR_RPM_URL = "https://download.copr.fedorainfracloud.org/results/user/project/fedora-rawhide-x86_64/11230530-tmt"
MOCK_RPMS_COPR = [f"{MOCK_COPR_RPM_URL}/pkg{i}-1.0-1.fc41.x86_64" for i in range(14)]


@pytest.fixture
def copr_session(mocker: pytest_mock.MockerFixture) -> MagicMock:
    # TODO: find a cleaner interface to navigate a partially mocked/spied client session
    #  (the return is not the copr_session but the get_results_url)
    return mocker.patch("copr.v3.BuildChrootProxy.get_results_url", return_value=MOCK_RPMS_COPR)


def test_copr_valid_build_non_pulp(artifact_provider, copr_session: MagicMock):
    provider = artifact_provider(f"copr.build:{MOCK_BUILD_ID_COPR}:fedora-41-x86_64")
    assert isinstance(provider, CoprBuildArtifactProvider)
    assert provider.build_id == MOCK_BUILD_ID_COPR
    assert len(provider.artifacts) == len(MOCK_RPMS_COPR)

    for artifact in provider.artifacts:
        assert artifact.location.startswith(MOCK_COPR_RPM_URL)
    assert copr_session.assert_called_once()


def test_copr_invalid_build_id(artifact_provider, copr_session: MagicMock):
    with pytest.raises(ValueError, match=r"Invalid provider id 'invalid_id:fedora-41-x86_64'\."):
        _ = artifact_provider("copr.build:invalid_id:fedora-41-x86_64")
    assert copr_session.assert_not_called()


def test_copr_invalid_chroot(artifact_provider, copr_session: MagicMock):
    provider = artifact_provider(f"copr.build:{MOCK_BUILD_ID_COPR}:invalid_chroot")
    with pytest.raises(
        GeneralError, match=r"Chroot 'invalid_chroot' not found in build '9820798'\."
    ):
        _ = provider.artifacts
    assert copr_session.assert_not_called()
