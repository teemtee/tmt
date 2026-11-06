import re
from unittest.mock import MagicMock

import pytest

import tmt.log
from tmt.base.core import DependencySimple
from tmt.steps.prepare.ansible import PrepareAnsibleData, _RawAnsibleStepData
from tmt.steps.prepare.feature import crb, epel, fips
from tmt.steps.prepare.install import PrepareInstall


def test_debuginfo(root_logger):
    """
    Check debuginfo package parsing
    """

    plugin = MagicMock(spec=PrepareInstall)

    PrepareInstall._prepare_installables(
        plugin,
        dependencies=[
            # Regular packages
            DependencySimple("wget"),
            DependencySimple("debuginfo-something"),
            DependencySimple("elfutils-debuginfod"),
            # Debuginfo packages
            DependencySimple("grep-debuginfo"),
            DependencySimple("elfutils-debuginfod-debuginfo"),
        ],
        directories=[],
        logger=root_logger,
    )

    assert plugin.packages == [
        "wget",
        "debuginfo-something",
        "elfutils-debuginfod",
    ]
    assert plugin.debuginfo_packages == [
        "grep",
        "elfutils-debuginfod",
    ]


@pytest.mark.parametrize(
    ('patterns', 'distro'),
    [
        (crb.SUPPORTED_DISTRO_PATTERNS, 'Red Hat Enterprise Linux 9'),
        (epel.SUPPORTED_DISTRO_PATTERNS, 'Red Hat Enterprise Linux 9'),
        (fips.SUPPORTED_DISTRO_PATTERNS, 'Red Hat Enterprise Linux Server 9'),
    ],
    ids=['crb', 'epel', 'fips'],
)
def test_supported_distro_patterns_are_reusable(
    patterns: tuple[re.Pattern[str], ...], distro: str
) -> None:
    """Checking a distribution in one plan must not exhaust patterns for the next."""

    assert isinstance(patterns, tuple)
    assert patterns
    assert any(pattern.match(distro) for pattern in patterns)
    assert any(pattern.match(distro) for pattern in patterns)
    assert list(patterns) == list(patterns)


@pytest.mark.parametrize(
    ('mapping', 'expected'),
    [
        ({}, []),
        ({'playbook': 'one.yml'}, ['one.yml']),
        ({'playbook': ['one.yml', 'two.yml']}, ['one.yml', 'two.yml']),
        ({'playbooks': 'one.yml'}, ['one.yml']),
        ({'playbooks': ['one.yml', 'two.yml']}, ['one.yml', 'two.yml']),
        (
            {'playbook': 'one.yml', 'playbooks': ['two.yml', 'three.yml']},
            ['one.yml', 'two.yml', 'three.yml'],
        ),
    ],
)
def test_ansible_playbook_normalization(
    mapping: _RawAnsibleStepData, expected: list[str], root_logger: tmt.log.Logger
) -> None:
    """Singular and plural playbook keys normalize into one ordered list."""

    raw_data: _RawAnsibleStepData = {'name': 'default-0', 'how': 'ansible', **mapping}
    assert PrepareAnsibleData.from_spec(raw_data, root_logger).playbook == expected
