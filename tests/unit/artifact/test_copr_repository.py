from unittest.mock import MagicMock, patch

import pytest


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
        'tmt.steps.prepare.artifact.providers.copr_repository.Repository.from_content',
        return_value=mock_repo,
    ) as mock_from_content:
        result = provider.fetch_contents(mock_guest, download_path)

    mock_package_manager.enable_copr.assert_called_once_with('@teemtee/stable')
    mock_guest.execute.assert_called_once()
    assert expected_repo_filename in str(mock_guest.execute.call_args[0][0])
    mock_from_content.assert_called_once_with(
        mock_guest.execute.return_value.stdout or '',
        '@teemtee/stable',
        provider.logger,
    )
    assert result == []
    assert provider.repository is mock_repo
