"""
Tests for APT package manager
"""

from typing import Optional

import _pytest.logging
import pytest
from pytest_container import Container
from pytest_container.container import ContainerData

import tmt.log
from tmt.package_managers import (
    Package,
    PackageManagerClass,
)
from tmt.steps.provision.podman import GuestContainer

from ._test_package_manager import (
    APT_TEST_CASES,
    CONTAINER_DEBIAN_127,
    CONTAINER_UBUNTU_2204,
    PACKAGE_MANAGER_APT,
    do_test_install,
    do_test_install_nonexistent,
    do_test_refresh_metadata,
    filter_test_cases_by_package_manager,
)

# Get test cases and IDs specific to APT tests
APT_TEST_CASES, APT_TEST_IDS = filter_test_cases_by_package_manager(PACKAGE_MANAGER_APT)  # noqa: F811


@pytest.mark.containers
@pytest.mark.parametrize(
    (
        'container_per_test',
        'package_manager_class',
        'package',
        'expected_command',
        'expected_output',
    ),
    APT_TEST_CASES,
    indirect=["container_per_test"],
    ids=APT_TEST_IDS,
)
def test_apt_install(
    container_per_test: ContainerData,
    guest_per_test: GuestContainer,
    package_manager_class: PackageManagerClass,
    package: Package,
    expected_command: str,
    expected_output: Optional[str],
    root_logger: tmt.log.Logger,
    caplog: _pytest.logging.LogCaptureFixture,
) -> None:
    """Test installing a package with apt."""
    do_test_install(
        container_per_test,
        guest_per_test,
        package_manager_class,
        package,
        expected_command,
        expected_output,
        root_logger,
        caplog,
    )


def _apt_refresh_metadata_cases() -> list[
    tuple[Container, PackageManagerClass, str, Optional[str]]
]:
    """Generate test cases for apt refresh_metadata."""
    return [
        (
            container,
            PACKAGE_MANAGER_APT,
            r"export DEBIAN_FRONTEND=noninteractive; apt update",
            'Reading package list',
        )
        for container in [CONTAINER_UBUNTU_2204, CONTAINER_DEBIAN_127]
    ]


@pytest.mark.containers
@pytest.mark.parametrize(
    ('container_per_test', 'package_manager_class', 'expected_command', 'expected_output'),
    _apt_refresh_metadata_cases(),
    indirect=["container_per_test"],
    ids=APT_TEST_IDS,
)
def test_apt_refresh_metadata(
    container_per_test: ContainerData,
    guest_per_test: GuestContainer,
    package_manager_class: PackageManagerClass,
    expected_command: str,
    expected_output: Optional[str],
    root_logger: tmt.log.Logger,
    caplog: _pytest.logging.LogCaptureFixture,
) -> None:
    """Test refreshing APT metadata."""
    do_test_refresh_metadata(
        container_per_test,
        guest_per_test,
        package_manager_class,
        expected_command,
        expected_output,
        root_logger,
        caplog,
    )


def _apt_nonexistent_cases() -> list[tuple[Container, PackageManagerClass, str, Optional[str]]]:
    """Generate test cases for apt nonexistent package install."""
    return [
        (
            container,
            PACKAGE_MANAGER_APT,
            r"set -x\s+export DEBIAN_FRONTEND=noninteractive\s+installable_packages=\"tree-but-spelled-wrong\"\s+dpkg-query --show \$installable_packages \\\s+\|\| apt install -y  \$installable_packages\s+exit \$\?",  # noqa: E501
            'E: Unable to locate package tree-but-spelled-wrong',
        )
        for container in [CONTAINER_UBUNTU_2204, CONTAINER_DEBIAN_127]
    ]


@pytest.mark.containers
@pytest.mark.parametrize(
    ('container', 'package_manager_class', 'expected_command', 'expected_output'),
    _apt_nonexistent_cases(),
    indirect=["container"],
    ids=APT_TEST_IDS,
)
def test_apt_install_nonexistent(
    container: ContainerData,
    guest: GuestContainer,
    package_manager_class: PackageManagerClass,
    expected_command: str,
    expected_output: Optional[str],
    root_logger: tmt.log.Logger,
    caplog: _pytest.logging.LogCaptureFixture,
) -> None:
    """Test attempting to install a nonexistent package with apt."""
    do_test_install_nonexistent(
        container,
        guest,
        package_manager_class,
        expected_command,
        expected_output,
        root_logger,
        caplog,
    )
