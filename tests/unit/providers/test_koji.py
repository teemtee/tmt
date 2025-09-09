from unittest.mock import MagicMock

import pytest

from tmt.steps.prepare.brand_new_allmighty_install.providers.koji_provider import (
    KojiProvider,
)


def test_parse_artifact_id_valid():
    provider = KojiProvider(MagicMock(), "koji.build:12345")
    assert provider.artifact_id == "12345"


@pytest.mark.parametrize("invalid_id", ["koji.task:111", "koji.build:abc"])
def test_parse_artifact_id_invalid(invalid_id):
    with pytest.raises(ValueError, match="Invalid artifact ID format"):
        KojiProvider(MagicMock(), invalid_id)


def test_call_api_success():
    provider = KojiProvider(MagicMock(), "koji.build:123")
    provider._session = MagicMock()
    provider._session.some_method.return_value = "ok"

    result = provider._call_api("some_method", 1, 2)
    assert result == "ok"
