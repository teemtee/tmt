from unittest.mock import MagicMock

import pytest

from tmt.steps.prepare.artifact.providers.copr_repository import CoprRepositoryProvider


@pytest.mark.parametrize(
    ("raw_id", "expected"),
    [
        ("copr.repository:packit/packit-dev", "packit/packit-dev"),
        ("copr.repository:@teemtee/stable", "@teemtee/stable"),
    ],
)
def test_valid_repository_id(raw_id, expected, root_logger):
    provider = CoprRepositoryProvider(raw_id, root_logger)
    assert provider.copr_repo == expected


@pytest.mark.parametrize(
    ("raw_id", "error"),
    [
        ("invalid:@teemtee/stable", "Invalid Copr repository provider format"),
        ("copr.repository:invalid-id", "Invalid Copr repository format"),
        ("copr.repository:@/stable", "Invalid Copr repository format"),
        ("copr.repository:", "Missing Copr repository name"),
    ],
)
def test_invalid_repository_id(raw_id, error, root_logger):
    with pytest.raises(ValueError, match=error):
        CoprRepositoryProvider(raw_id, root_logger)


def test_fetch_contents_enables_repository(mock_installer, root_logger, tmppath):
    mock_guest = MagicMock()
    mock_guest.facts.package_manager = 'dnf'

    provider = CoprRepositoryProvider("copr.repository:@teemtee/stable", root_logger)

    result = provider.fetch_contents(mock_guest, tmppath / "artifacts")

    mock_installer.enable_copr.assert_called_once_with(['@teemtee/stable'])
    assert result == []
