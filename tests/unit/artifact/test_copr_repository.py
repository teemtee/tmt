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


def test_fetch_contents_enables_repository(mock_copr_class, root_logger, tmppath):
    mock_guest = MagicMock()
    mock_copr_instance = MagicMock()
    mock_copr_class.return_value = mock_copr_instance

    provider = CoprRepositoryProvider("copr.repository:@teemtee/stable", root_logger)

    assert provider.copr_repo == '@teemtee/stable'
    assert provider.artifacts == []

    result = provider.fetch_contents(mock_guest, tmppath / "artifacts")

    mock_copr_class.assert_called_once_with(
        logger=root_logger,
        guest=mock_guest,
    )
    mock_copr_instance.enable_copr.assert_called_once_with([provider.copr_repo])
    assert result == []
