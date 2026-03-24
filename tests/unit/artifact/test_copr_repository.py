from unittest.mock import MagicMock, patch

import pytest

from tmt.utils import Path


@pytest.mark.parametrize(
    ("raw_id", "expected"),
    [
        ("copr.repository:packit/packit-dev", "packit/packit-dev"),
        ("copr.repository:@teemtee/stable", "@teemtee/stable"),
    ],
)
def test_valid_repository_id(raw_id, expected, artifact_provider):
    provider = artifact_provider(raw_id)
    assert provider.copr_repo == expected


@pytest.mark.parametrize(
    ("raw_id", "error"),
    [
        ("copr.repository:invalid-id", "Invalid Copr repository format"),
        ("copr.repository:@/stable", "Invalid Copr repository format"),
        ("copr.repository:", "Missing Copr repository name"),
    ],
)
def test_invalid_repository_id(raw_id, error, artifact_provider):
    with pytest.raises(ValueError, match=error):
        artifact_provider(raw_id)


def test_fetch_contents_enables_repository(
    mock_copr_build_session, mock_package_manager, artifact_provider, tmppath
):
    mock_repo = MagicMock()
    mock_guest = MagicMock()
    mock_guest.package_manager = mock_package_manager

    provider = artifact_provider("copr.repository:@teemtee/stable")
    download_path = tmppath / "artifacts"

    # @teemtee/stable: is_group=True -> owner="group_teemtee"
    expected_repo_filename = "_copr:copr.fedorainfracloud.org:group_teemtee:stable.repo"

    with patch(
        'tmt.steps.prepare.artifact.providers.copr_repository.Repository.from_file_path',
        return_value=mock_repo,
    ) as mock_from_file:
        result = provider.fetch_contents(mock_guest, download_path)

    mock_package_manager.enable_copr.assert_called_once_with('@teemtee/stable')
    mock_guest.pull.assert_called_once_with(
        source=Path(f"/etc/yum.repos.d/{expected_repo_filename}"),
        destination=download_path,
    )
    mock_from_file.assert_called_once_with(
        download_path / expected_repo_filename,
        provider.logger,
        name='@teemtee/stable',
    )
    assert result == []
    assert provider.repository is mock_repo
