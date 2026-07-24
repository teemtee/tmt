import logging

import _pytest.logging
import _pytest.monkeypatch
import pytest

import tmt
from tmt.log import Logger
from tmt.utils import GeneralError
from tmt.utils.feeling_safe import UnsafeBehavior

from . import MATCH, assert_log


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
    ),
)
def test_assert_is_allowed(
    tmt_version: str,
    deprecated_version: str,
    expect_warn: bool,
    expect_exception: str,
    root_logger: Logger,
    monkeypatch: _pytest.monkeypatch.MonkeyPatch,
    caplog: _pytest.logging.LogCaptureFixture,
) -> None:
    ub = UnsafeBehavior(name='test', label='test unsafe behavior', locked_since=deprecated_version)

    monkeypatch.setattr(tmt, '__version__', tmt_version)

    if expect_exception:
        with pytest.raises(GeneralError):
            ub.assert_is_allowed(root_logger)

    else:
        ub.assert_is_allowed(root_logger)

        assert_log(
            caplog,
            message=MATCH(
                rf"warn: Starting with tmt {ub.locked_since},"
                r" test unsafe behavior will require '--feeling-safe' option\."
            ),
            levelno=logging.WARNING,
        )
