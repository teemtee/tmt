from unittest.mock import MagicMock, patch

import pytest

import tmt
from tmt.steps import Phase


class TestPhaseAssertFeelingSafe:

    def setup_method(self):
        self.mock_logger = MagicMock()
        self.phase = Phase(logger=self.mock_logger)

    @pytest.mark.parametrize(
        ("tmt_version", "deprecated_version", "expected_result", "expect_warn", "expect_fail"), [
            ('1.30', '1.38', True, True, False),  # warn for older version
            ('1.40', '1.38', False, False, True),  # fail for newer version
            ('1.38', '1.38', False, False, True)  # fail for same version
            ])
    def test_assert_feeling_safe(
            self,
            tmt_version,
            deprecated_version,
            expected_result,
            expect_warn,
            expect_fail):
        with patch.object(self.phase, 'warn') as mock_warn, \
                patch.object(self.phase, 'fail') as mock_fail:
            tmt.__version__ = tmt_version
            result = self.phase.assert_feeling_safe(deprecated_version, 'Local provision plugin')

            assert result == expected_result
            assert mock_warn.called == expect_warn
            assert mock_fail.called == expect_fail

    def test_assert_feeling_safe_feeling_safe(self):
        with (patch.object(Phase, 'is_feeling_safe', True),
              patch.object(self.phase, 'warn') as mock_warn,
              patch.object(self.phase, 'fail') as mock_fail):
            tmt.__version__ = '1.40'
            result = self.phase.assert_feeling_safe('1.38', 'Local provision plugin')

            assert result is True
            # Check that neither warn nor fail is called when feeling safe
            assert not mock_warn.called
            assert not mock_fail.called
