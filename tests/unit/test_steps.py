from unittest.mock import MagicMock, patch

import pytest

import tmt
from tmt.steps import Phase
from tmt.utils import GeneralError


class TestPhaseAssertFeelingSafe:

    def setup_method(self):
        self.mock_logger = MagicMock()
        self.phase = Phase(logger=self.mock_logger)

    @pytest.mark.parametrize(
        ("tmt_version", "deprecated_version", "expect_warn", "expect_exception"),
        [
            ('1.30', '1.38', True, False),  # warn for older version
            ('1.4.0.dev1595+ga35d7140.d20240806', '1.38', True, False),  # warn for older version
            ('1.40', '1.38', False, True),  # raise exception for newer version
            ('1.38', '1.38', False, True),  # raise exception for same version
            ],
        ids=(
            'warn for older version',
            'warn for older version with commit ID',
            'raise exception for newer version',
            'raise exception for same version',
            )
        )
    def test_assert_feeling_safe(
            self,
            tmt_version,
            deprecated_version,
            expect_warn,
            expect_exception):
        with patch.object(self.phase, 'warn') as mock_warn:
            tmt.__version__ = tmt_version

            if expect_exception:
                with pytest.raises(GeneralError):
                    self.phase.assert_feeling_safe(deprecated_version, 'Local provision plugin')
            else:
                self.phase.assert_feeling_safe(deprecated_version, 'Local provision plugin')

            assert mock_warn.called == expect_warn

    def test_assert_feeling_safe_feeling_safe(self):
        with (patch.object(Phase, 'is_feeling_safe', True),
              patch.object(self.phase, 'warn') as mock_warn):
            tmt.__version__ = '1.40'
            self.phase.assert_feeling_safe('1.38', 'Local provision plugin')

            # Check that warn is not called when feeling safe
            assert not mock_warn.called
