from unittest.mock import MagicMock

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


def test_fetch_contents_enables_repository(mock_installer, artifact_provider, tmppath):
    mock_guest = MagicMock()
    mock_pm = MagicMock()
    mock_pm.NAME = "dnf"
    mock_guest.package_manager = mock_pm

    provider = artifact_provider("copr.repository:@teemtee/stable")

    result = provider.fetch_contents(mock_guest, tmppath / "artifacts")

    mock_installer.enable_copr.assert_called_once_with(['@teemtee/stable'])
    assert result == []
