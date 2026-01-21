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


def test_fetch_contents_enables_repository(mock_copr_class, artifact_provider, tmppath):
    mock_guest = MagicMock()
    mock_copr_instance = MagicMock()
    mock_copr_class.return_value = mock_copr_instance

    provider = artifact_provider("copr.repository:@teemtee/stable")

    assert provider.copr_repo == '@teemtee/stable'
    assert provider.artifacts == []

    result = provider.fetch_contents(mock_guest, tmppath / "artifacts")

    mock_copr_class.assert_called_once_with(
        logger=provider.logger,
        guest=mock_guest,
    )
    mock_copr_instance.enable_copr.assert_called_once_with([provider.copr_repo])
    assert result == []
