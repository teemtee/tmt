from unittest.mock import MagicMock, patch

import pytest


def _make_project_info(*chroots: str) -> MagicMock:
    info = MagicMock()
    info.chroot_repos = {chroot: f'https://example.com/{chroot}/' for chroot in chroots}
    return info


@pytest.mark.parametrize(
    ("raw_id", "expected"),
    [
        ("copr.repository:packit/packit-dev", "packit/packit-dev"),
        ("copr.repository:@teemtee/stable", "@teemtee/stable"),
    ],
)
def test_valid_repository_id(raw_id, expected, mock_copr, artifact_provider):
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


def test_fetch_contents_fetches_repo_file(
    mock_copr, mock_package_manager, artifact_provider, tmppath
):
    mock_repo = MagicMock()
    mock_guest = MagicMock()
    mock_guest.package_manager = mock_package_manager
    mock_guest.facts.os_release_content = {'ID': 'fedora', 'VERSION_ID': '42'}
    mock_guest.facts.arch = 'x86_64'

    mock_copr.project_proxy.get.return_value = _make_project_info(
        'fedora-42-x86_64', 'fedora-41-x86_64'
    )
    provider = artifact_provider("copr.repository:@teemtee/stable")

    with patch(
        'tmt.steps.prepare.artifact.providers.Repository.from_url',
        return_value=mock_repo,
    ) as mock_from_url:
        result = provider.fetch_contents(mock_guest, tmppath / "artifacts")

    expected_url = (
        'https://copr.fedorainfracloud.org/coprs/g/teemtee/stable/repo/'
        'fedora-42-x86_64/group_teemtee-stable-fedora-42-x86_64.repo'
    )
    mock_from_url.assert_called_once_with(expected_url, provider.logger)
    mock_package_manager.install_repository.assert_not_called()
    assert result == []
