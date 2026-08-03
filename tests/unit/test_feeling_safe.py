import logging
from collections.abc import Sequence

import _pytest.logging
import _pytest.monkeypatch
import pytest

import tmt
from tmt.log import Logger
from tmt.utils import GeneralError
from tmt.utils.feeling_safe import (
    UnsafeBehavior,
    allow_behaviors,
    is_allowed,
)

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


@pytest.mark.parametrize(
    ("allowed_behaviors", "requested_behaviors", "expected"),
    [
        # with `all``, everything is allowed
        (
            ('all',),
            ('provision/local',),
            True,
        ),
        # with `none``, nothing is allowed
        (
            ('none',),
            ('provision/local',),
            False,
        ),
        # with both `all`` and `none``, nothing is allowed
        (
            ('all', 'none'),
            ('provision/local',),
            False,
        ),
        # with exact name, the name is allowed
        (
            ('provision/local',),
            ('provision/local',),
            True,
        ),
        # with exact but different name, the name is not allowed
        (
            ('provision/mock',),
            ('provision/local',),
            False,
        ),
    ],
    ids=(
        'with `all`, everything is allowed',
        'with `none`, nothing is allowed',
        'with both `all` and `none`, nothing is allowed',
        'with exact name, the name is allowed',
        'with exact but different name, the name is not allowed',
    ),
)
def test_is_allowed(
    allowed_behaviors: Sequence[str],
    requested_behaviors: Sequence[str],
    expected: bool,
    monkeypatch: _pytest.monkeypatch.MonkeyPatch,
) -> None:
    allow_behaviors(*allowed_behaviors)

    assert is_allowed(*requested_behaviors) is expected
