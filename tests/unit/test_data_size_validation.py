"""
Unit tests for data size validation in tmt.utils and tmt.hardware
"""

import pytest

import tmt.hardware
import tmt.log
import tmt.utils
from tmt.utils import NormalizationError


@pytest.mark.parametrize(
    "size_str", ["32 MB", "500 kB", "2 MiB", "1024 B", "5 GB", "2 GiB", "1 TB", "1 TiB"]
)
def test_valid_string_sizes(root_logger, size_str):
    """Test that valid string size values are normalized correctly"""
    result = tmt.utils.normalize_data_amount("test.field", size_str, root_logger)

    # Check that result already has bytes dimension (not converting, but checking dimension)
    assert result.dimensionality == tmt.hardware.UNITS('1 byte').dimensionality


def test_valid_quantity_objects(root_logger):
    """Test that valid Quantity objects pass through"""
    from pint import Quantity

    valid_quantity = tmt.hardware.UNITS("64 MB")
    result = tmt.utils.normalize_data_amount("test.field", valid_quantity, root_logger)

    # Should return the same object
    assert result == valid_quantity


def test_invalid_molar_unit(root_logger):
    """Test that 'M' (molar) unit is rejected with helpful message"""
    with pytest.raises(NormalizationError) as exc_info:
        tmt.utils.normalize_data_amount("test.field", "32 M", root_logger)

    error_msg = str(exc_info.value)
    assert "valid data quantity" in error_msg
    assert "MB" in error_msg or "MiB" in error_msg
