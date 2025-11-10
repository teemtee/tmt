"""
Unit tests for data size validation in tmt.utils and tmt.hardware
"""

from unittest.mock import Mock

import pytest

import tmt.hardware
import tmt.log
import tmt.utils
from tmt.utils import NormalizationError


class TestDataSizeNormalization:
    """Test cases for normalize_data_amount function"""

    def setup_method(self):
        """Setup method for each test"""
        self.logger = Mock()

    def test_valid_string_sizes(self):
        """Test that valid string size values are normalized correctly"""
        valid_sizes = ["32 MB", "500 kB", "2 MiB", "1024 B", "5 GB", "2 GiB", "1 TB", "1 TiB"]

        for size_str in valid_sizes:
            result = tmt.utils.normalize_data_amount("test.field", size_str, self.logger)

            # Check that result can be converted to bytes (validates dimensionality)
            bytes_value = result.to('bytes')
            assert bytes_value.magnitude > 0

            # Check it's a valid size quantity
            assert hasattr(result, 'magnitude')
            assert hasattr(result, 'units')

    def test_valid_quantity_objects(self):
        """Test that valid Quantity objects pass through"""
        from pint import Quantity

        valid_quantity = tmt.hardware.UNITS("64 MB")
        result = tmt.utils.normalize_data_amount("test.field", valid_quantity, self.logger)

        # Should return the same object
        assert result == valid_quantity

    def test_invalid_molar_unit(self):
        """Test that 'M' (molar) unit is rejected with helpful message"""
        with pytest.raises(NormalizationError) as exc_info:
            tmt.utils.normalize_data_amount("test.field", "32 M", self.logger)

        error_msg = str(exc_info.value)
        assert "valid data quantity" in error_msg
        assert "MB" in error_msg or "MiB" in error_msg
