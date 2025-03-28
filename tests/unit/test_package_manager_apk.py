"""
Tests for APK package manager
"""

from collections.abc import Iterator
from typing import Optional

import _pytest.logging
import pytest
from pytest_container import Container
from pytest_container.container import ContainerData

import tmt.log
import tmt.package_managers
from tmt.package_managers import (
    FileSystemPath,
    Installable,
    Package,
    PackageManagerClass,
)
from tmt.steps.provision.podman import GuestContainer

from ._test_package_manager import (
    CONTAINER_ALPINE,
    CONTAINER_BASE_MATRIX,
    CONTAINER_MATRIX_IDS,
    PACKAGE_MANAGER_APK,
    do_test_check_presence,
    do_test_install,
    do_test_install_dont_check_first,
    do_test_install_filesystempath,
    do_test_install_multiple,
    do_test_install_nonexistent,
    do_test_install_nonexistent_skip,
    do_test_refresh_metadata,
    do_test_reinstall,
)


def _filter_apk_test_cases() -> Iterator[
    tuple[Container, PackageManagerClass, Package, str, Optional[str]]
]:
    """Filter apk-specific test cases from the container matrix."""
    for container, package_manager_class in CONTAINER_BASE_MATRIX:
        if package_manager_class is not PACKAGE_MANAGER_APK:
            continue

        yield (
            container,
            package_manager_class,
            Package('tree'),
            r"apk info -e tree \|\| apk add tree",
            'Installing tree',
        )


def _filter_apk_matrix_ids() -> list[str]:
    """Filter apk-specific test IDs from the container matrix."""
    return [
        matrix_id
        for i, matrix_id in enumerate(CONTAINER_MATRIX_IDS)
        if CONTAINER_BASE_MATRIX[i][1] is PACKAGE_MANAGER_APK
    ]


@pytest.mark.containers
@pytest.mark.parametrize(
    (
        'container_per_test',
        'package_manager_class',
        'package',
        'expected_command',
        'expected_output',
    ),
    list(_filter_apk_test_cases()),
    indirect=["container_per_test"],
    ids=_filter_apk_matrix_ids(),
)
def test_apk_install(
    container_per_test: ContainerData,
    guest_per_test: GuestContainer,
    package_manager_class: PackageManagerClass,
    package: Package,
    expected_command: str,
    expected_output: Optional[str],
    root_logger: tmt.log.Logger,
    caplog: _pytest.logging.LogCaptureFixture,
) -> None:
    """Test installing a package with apk."""
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


def _apk_refresh_metadata_cases() -> Iterator[
    tuple[Container, PackageManagerClass, str, Optional[str]]
]:
    """Generate test cases for apk refresh_metadata."""
    yield (
        CONTAINER_ALPINE,
        PACKAGE_MANAGER_APK,
        r"apk update",
        'OK:',
    )


@pytest.mark.containers
@pytest.mark.parametrize(
    ('container_per_test', 'package_manager_class', 'expected_command', 'expected_output'),
    list(_apk_refresh_metadata_cases()),
    indirect=["container_per_test"],
    ids=_filter_apk_matrix_ids(),
)
def test_apk_refresh_metadata(
    container_per_test: ContainerData,
    guest_per_test: GuestContainer,
    package_manager_class: PackageManagerClass,
    expected_command: str,
    expected_output: Optional[str],
    root_logger: tmt.log.Logger,
    caplog: _pytest.logging.LogCaptureFixture,
) -> None:
    """Test refreshing APK metadata."""
    do_test_refresh_metadata(
        container_per_test,
        guest_per_test,
        package_manager_class,
        expected_command,
        expected_output,
        root_logger,
        caplog,
    )


def _apk_nonexistent_cases() -> Iterator[
    tuple[Container, PackageManagerClass, str, Optional[str]]
]:
    """Generate test cases for apk nonexistent package install."""
    yield (
        CONTAINER_ALPINE,
        PACKAGE_MANAGER_APK,
        r"apk info -e tree-but-spelled-wrong \|\| apk add tree-but-spelled-wrong",
        'ERROR: unable to select packages:\n  tree-but-spelled-wrong (no such package):\n    required by: world[tree-but-spelled-wrong]',  # noqa: E501
    )


@pytest.mark.containers
@pytest.mark.parametrize(
    ('container', 'package_manager_class', 'expected_command', 'expected_output'),
    list(_apk_nonexistent_cases()),
    indirect=["container"],
    ids=_filter_apk_matrix_ids(),
)
def test_apk_install_nonexistent(
    container: ContainerData,
    guest: GuestContainer,
    package_manager_class: PackageManagerClass,
    expected_command: str,
    expected_output: Optional[str],
    root_logger: tmt.log.Logger,
    caplog: _pytest.logging.LogCaptureFixture,
) -> None:
    """Test attempting to install a nonexistent package with apk."""
    do_test_install_nonexistent(
        container,
        guest,
        package_manager_class,
        expected_command,
        expected_output,
        root_logger,
        caplog,
    )


def _apk_nonexistent_skip_cases() -> Iterator[
    tuple[Container, PackageManagerClass, str, Optional[str]]
]:
    """Generate test cases for apk nonexistent package install with skip_missing."""
    yield (
        CONTAINER_ALPINE,
        PACKAGE_MANAGER_APK,
        r"apk info -e tree-but-spelled-wrong \|\| apk add tree-but-spelled-wrong \|\| /bin/true",
        'ERROR: unable to select packages:\n  tree-but-spelled-wrong (no such package):\n    required by: world[tree-but-spelled-wrong]',  # noqa: E501
    )


@pytest.mark.containers
@pytest.mark.parametrize(
    ('container', 'package_manager_class', 'expected_command', 'expected_output'),
    list(_apk_nonexistent_skip_cases()),
    indirect=["container"],
    ids=_filter_apk_matrix_ids(),
)
def test_apk_install_nonexistent_skip(
    container: ContainerData,
    guest: GuestContainer,
    package_manager_class: PackageManagerClass,
    expected_command: str,
    expected_output: Optional[str],
    root_logger: tmt.log.Logger,
    caplog: _pytest.logging.LogCaptureFixture,
) -> None:
    """Test installing a nonexistent package with skip_missing option."""
    do_test_install_nonexistent_skip(
        container,
        guest,
        package_manager_class,
        expected_command,
        expected_output,
        root_logger,
        caplog,
    )


def _apk_install_dont_check_first_cases() -> Iterator[
    tuple[Container, PackageManagerClass, Package, str, Optional[str]]
]:
    """Generate test cases for apk install without first checking if installed."""
    yield (
        CONTAINER_ALPINE,
        PACKAGE_MANAGER_APK,
        Package('tree'),
        r"apk add tree",
        'Installing tree',
    )


@pytest.mark.containers
@pytest.mark.parametrize(
    (
        'container_per_test',
        'package_manager_class',
        'package',
        'expected_command',
        'expected_output',
    ),
    list(_apk_install_dont_check_first_cases()),
    indirect=["container_per_test"],
    ids=_filter_apk_matrix_ids(),
)
def test_apk_install_dont_check_first(
    container_per_test: ContainerData,
    guest_per_test: GuestContainer,
    package_manager_class: PackageManagerClass,
    package: Package,
    expected_command: str,
    expected_output: Optional[str],
    root_logger: tmt.log.Logger,
    caplog: _pytest.logging.LogCaptureFixture,
) -> None:
    """Test installing a package without first checking if it's already installed."""
    do_test_install_dont_check_first(
        container_per_test,
        guest_per_test,
        package_manager_class,
        package,
        expected_command,
        expected_output,
        root_logger,
        caplog,
    )


def _apk_reinstall_cases() -> Iterator[
    tuple[Container, PackageManagerClass, Package, bool, Optional[str], Optional[str]]
]:
    """Generate test cases for apk reinstall."""
    yield (
        CONTAINER_ALPINE,
        PACKAGE_MANAGER_APK,
        Package('bash'),
        True,
        r"apk info -e bash && apk fix bash",
        'Reinstalling bash',
    )


@pytest.mark.containers
@pytest.mark.parametrize(
    (
        'container_per_test',
        'package_manager_class',
        'package',
        'supported',
        'expected_command',
        'expected_output',
    ),
    list(_apk_reinstall_cases()),
    indirect=["container_per_test"],
    ids=_filter_apk_matrix_ids(),
)
def test_apk_reinstall(
    container_per_test: ContainerData,
    guest_per_test: GuestContainer,
    package_manager_class: PackageManagerClass,
    package: Package,
    supported: bool,
    expected_command: Optional[str],
    expected_output: Optional[str],
    root_logger: tmt.log.Logger,
    caplog: _pytest.logging.LogCaptureFixture,
) -> None:
    """Test reinstalling a package with apk."""
    do_test_reinstall(
        container_per_test,
        guest_per_test,
        package_manager_class,
        package,
        supported,
        expected_command,
        expected_output,
        root_logger,
        caplog,
    )


def _apk_check_presence_cases() -> Iterator[
    tuple[Container, PackageManagerClass, Installable, bool, str, Optional[str]]
]:
    """Generate test cases for apk check_presence."""
    yield (
        CONTAINER_ALPINE,
        PACKAGE_MANAGER_APK,
        Package('busybox'),
        True,
        r"apk info -e busybox",
        r'\s+out:\s+busybox',
    )

    yield (
        CONTAINER_ALPINE,
        PACKAGE_MANAGER_APK,
        Package('tree-but-spelled-wrong'),
        False,
        r"apk info -e tree-but-spelled-wrong",
        None,
    )

    yield (
        CONTAINER_ALPINE,
        PACKAGE_MANAGER_APK,
        FileSystemPath('/usr/bin/arch'),
        True,
        r"apk info -e busybox",
        r'\s+out:\s+busybox',
    )


def _apk_check_presence_ids(value) -> str:
    """Generate IDs for check_presence test cases."""
    if isinstance(value, Container):
        return value.url
    if isinstance(value, type) and issubclass(value, tmt.package_managers.PackageManager):
        return value.__name__.lower()
    if isinstance(value, (Package, FileSystemPath)):
        return str(value)
    return ''


@pytest.mark.containers
@pytest.mark.parametrize(
    (
        'container',
        'package_manager_class',
        'installable',
        'expected_result',
        'expected_command',
        'expected_output',
    ),
    list(_apk_check_presence_cases()),
    indirect=["container"],
    ids=_apk_check_presence_ids,
)
def test_apk_check_presence(
    container: ContainerData,
    guest: GuestContainer,
    package_manager_class: PackageManagerClass,
    installable: Installable,
    expected_result: bool,
    expected_command: str,
    expected_output: Optional[str],
    root_logger: tmt.log.Logger,
    caplog: _pytest.logging.LogCaptureFixture,
) -> None:
    """Test checking if a package or file is present with apk."""
    do_test_check_presence(
        container,
        guest,
        package_manager_class,
        installable,
        expected_result,
        expected_command,
        expected_output,
        root_logger,
        caplog,
    )


def _apk_install_filesystempath_cases() -> Iterator[
    tuple[Container, PackageManagerClass, FileSystemPath, str, Optional[str]]
]:
    """Generate test cases for apk install with filesystem path."""
    yield (
        CONTAINER_ALPINE,
        PACKAGE_MANAGER_APK,
        FileSystemPath('/usr/bin/dos2unix'),
        r"apk info -e dos2unix \|\| apk add dos2unix",
        'Installing dos2unix',
    )


@pytest.mark.containers
@pytest.mark.parametrize(
    (
        'container_per_test',
        'package_manager_class',
        'installable',
        'expected_command',
        'expected_output',
    ),
    list(_apk_install_filesystempath_cases()),
    indirect=["container_per_test"],
    ids=_filter_apk_matrix_ids(),
)
def test_apk_install_filesystempath(
    container_per_test: ContainerData,
    guest_per_test: GuestContainer,
    package_manager_class: PackageManagerClass,
    installable: FileSystemPath,
    expected_command: str,
    expected_output: Optional[str],
    root_logger: tmt.log.Logger,
    caplog: _pytest.logging.LogCaptureFixture,
) -> None:
    """Test installing a package by filesystem path with apk."""
    do_test_install_filesystempath(
        container_per_test,
        guest_per_test,
        package_manager_class,
        installable,
        expected_command,
        expected_output,
        root_logger,
        caplog,
    )


def _apk_install_multiple_cases() -> Iterator[
    tuple[Container, PackageManagerClass, tuple[Package, Package], str, Optional[str]]
]:
    """Generate test cases for installing multiple packages with apk."""
    yield (
        CONTAINER_ALPINE,
        PACKAGE_MANAGER_APK,
        (Package('tree'), Package('diffutils')),
        r"apk info -e tree diffutils \|\| apk add tree diffutils",
        'Installing tree',
    )


@pytest.mark.containers
@pytest.mark.parametrize(
    (
        'container_per_test',
        'package_manager_class',
        'packages',
        'expected_command',
        'expected_output',
    ),
    list(_apk_install_multiple_cases()),
    indirect=["container_per_test"],
    ids=_filter_apk_matrix_ids(),
)
def test_apk_install_multiple(
    container_per_test: ContainerData,
    guest_per_test: GuestContainer,
    package_manager_class: PackageManagerClass,
    packages: tuple[Package, Package],
    expected_command: str,
    expected_output: Optional[str],
    root_logger: tmt.log.Logger,
    caplog: _pytest.logging.LogCaptureFixture,
) -> None:
    """Test installing multiple packages with apk."""
    do_test_install_multiple(
        container_per_test,
        guest_per_test,
        package_manager_class,
        packages,
        expected_command,
        expected_output,
        root_logger,
        caplog,
    )
