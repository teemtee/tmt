import logging
from typing import cast
from unittest.mock import MagicMock

import _pytest.logging
import pytest
from testcloud.domain_configuration import DomainConfiguration, TPMConfiguration

from tests.unit import MATCH, assert_log
from tmt.hardware import TPM_VERSION_ALLOWED_OPERATORS, Hardware, Operator
from tmt.log import Logger
from tmt.steps.provision.testcloud import (
    TPM_VERSION_ALLOWED_OPERATORS as virtual_TPM_VERSION_ALLOWED_OPERATORS,  # noqa: N811
)
from tmt.steps.provision.testcloud import (
    _apply_hw_tpm,
    import_testcloud,
    )

import_testcloud()

# These must be imported *after* importing testcloud
from tmt.steps.provision.testcloud import TPM_CONFIG_ALLOWS_VERSIONS, \
    TPM_VERSION_SUPPORTED_VERSIONS  # noqa: I001,E402


if TPM_CONFIG_ALLOWS_VERSIONS:
    allowed_combinations: list[tuple[str, Operator]] = []

    for version in TPM_VERSION_SUPPORTED_VERSIONS[TPM_CONFIG_ALLOWS_VERSIONS]:
        for op in virtual_TPM_VERSION_ALLOWED_OPERATORS:
            allowed_combinations.append((version, op))

    @pytest.mark.parametrize(
        ('version', 'op'),
        allowed_combinations,
        ids=[f'{op.value} {version}' for version, op in allowed_combinations]
        )
    def test_tpm(
            root_logger: Logger,
            caplog: _pytest.logging.LogCaptureFixture,
            version: str,
            op: Operator) -> None:
        mock_domain = MagicMock(name='<domain>')

        _apply_hw_tpm(
            Hardware.from_spec({'tpm': {'version': f'{op.value} {version}'}}),
            mock_domain,
            root_logger)

        tpm_config = cast(DomainConfiguration, mock_domain).tpm_configuration

        assert isinstance(tpm_config, TPMConfiguration)

        assert tpm_config.version == version

        assert_log(
            caplog,
            message=MATCH(rf"tpm.version: set to '{version}' because of 'tpm.version: {op.value} {version}'"),  # noqa: E501
            levelno=logging.DEBUG)

else:
    allowed_combinations: list[tuple[str, Operator]] = []

    for version in TPM_VERSION_SUPPORTED_VERSIONS[TPM_CONFIG_ALLOWS_VERSIONS]:
        for op in virtual_TPM_VERSION_ALLOWED_OPERATORS:
            allowed_combinations.append((version, op))

    @pytest.mark.parametrize(
        ('version', 'op'),
        allowed_combinations,
        ids=[f'{op.value} {version}' for version, op in allowed_combinations]
        )
    def test_tpm_with_default_version(
            root_logger: Logger,
            caplog: _pytest.logging.LogCaptureFixture,
            version: str,
            op: Operator) -> None:
        mock_domain = MagicMock(name='<domain>')

        _apply_hw_tpm(
            Hardware.from_spec({'tpm': {'version': f'{op.value} {version}'}}),
            mock_domain,
            root_logger)

        tpm_config = cast(DomainConfiguration, mock_domain).tpm_configuration

        assert isinstance(tpm_config, TPMConfiguration)

        assert_log(
            caplog,
            message=MATCH(rf"tpm.version: set to '{version}' because of 'tpm.version: {op.value} {version}'"),  # noqa: E501
            levelno=logging.DEBUG)


def test_tpm_no_hardware(
        root_logger: Logger,
        caplog: _pytest.logging.LogCaptureFixture) -> None:
    mock_domain = MagicMock(name='<domain>')

    _apply_hw_tpm(None, mock_domain, root_logger)
    assert cast(DomainConfiguration, mock_domain).tpm_configuration is None

    assert_log(
        caplog,
        message=MATCH(r"tpm.version: not included because of no constraints"),
        levelno=logging.DEBUG)


def test_tpm_no_hardware_constraint(
        root_logger: Logger,
        caplog: _pytest.logging.LogCaptureFixture) -> None:
    mock_domain = MagicMock(name='<domain>')

    _apply_hw_tpm(Hardware(constraint=None, spec=None), mock_domain, root_logger)
    assert cast(DomainConfiguration, mock_domain).tpm_configuration is None

    assert_log(
        caplog,
        message=MATCH(r"tpm.version: not included because of no constraints"),
        levelno=logging.DEBUG)


def test_tpm_no_tpm_constraints(
        root_logger: Logger,
        caplog: _pytest.logging.LogCaptureFixture) -> None:
    mock_domain = MagicMock(name='<domain>')

    _apply_hw_tpm(
        Hardware.from_spec({'memory': '4 GB'}),
        mock_domain,
        root_logger)

    assert cast(DomainConfiguration, mock_domain).tpm_configuration is None

    assert_log(
        caplog,
        message=MATCH(r"tpm.version: not included because of no 'tpm.version' constraints"),
        levelno=logging.DEBUG)


def test_tpm_unsupported_version(
        root_logger: Logger,
        caplog: _pytest.logging.LogCaptureFixture) -> None:
    mock_domain = MagicMock(name='<domain>')

    _apply_hw_tpm(
        Hardware.from_spec({'tpm': {'version': '0.0.0'}}),
        mock_domain,
        root_logger)

    assert cast(DomainConfiguration, mock_domain).tpm_configuration is None

    assert_log(
        caplog,
        message=MATCH(r"warn: Cannot apply hardware requirement 'tpm\.version: == 0\.0\.0', "
                      r"TPM version not supported."),
        levelno=logging.WARNING)


@pytest.mark.parametrize(
    'op',
    [
        op.value for op in TPM_VERSION_ALLOWED_OPERATORS
        if op not in virtual_TPM_VERSION_ALLOWED_OPERATORS
        ]
    )
def test_tpm_unsupported_operator(
        root_logger: Logger,
        caplog: _pytest.logging.LogCaptureFixture,
        op: str) -> None:
    mock_domain = MagicMock(name='<domain>')

    _apply_hw_tpm(
        Hardware.from_spec({'tpm': {'version': f'{op} 2.0'}}),
        mock_domain,
        root_logger)

    assert cast(DomainConfiguration, mock_domain).tpm_configuration is None

    assert_log(
        caplog,
        message=MATCH(rf"warn: Cannot apply hardware requirement 'tpm\.version: {op} 2\.0', operator not supported."),  # noqa: E501
        levelno=logging.WARNING)
