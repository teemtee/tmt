"""
Tests for rpm-ostree package manager
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
    CONTAINER_BASE_MATRIX,
    CONTAINER_FEDORA_COREOS_OSTREE,
    CONTAINER_MATRIX_IDS,
    PACKAGE_MANAGER_RPMOSTREE,
    do_test_check_presence,
    do_test_install,
    do_test_install_dont_check_first,
    do_test_install_filesystempath,
    do_test_install_multiple,
    do_test_install_nonexistent,
    do_test_install_nonexistent_skip,
    do_test_reinstall,
)


def _filter_rpm_ostree_test_cases() -> Iterator[
    tuple[Container, PackageManagerClass, Package, str, Optional[str]]
]:
    """Filter rpm-ostree test cases from the container matrix."""
    for container, package_manager_class in CONTAINER_BASE_MATRIX:
        if package_manager_class is not PACKAGE_MANAGER_RPMOSTREE:
            continue

        yield (
            container,
            package_manager_class,
            Package('tree'),
            r"rpm -q --whatprovides tree \|\| rpm-ostree install --apply-live --idempotent --allow-inactive --assumeyes  tree",  # noqa: E501
            'Installing: tree',
        )


def _filter_rpm_ostree_matrix_ids() -> list[str]:
    """Filter rpm-ostree test IDs from the container matrix."""
    return [
        matrix_id
        for i, matrix_id in enumerate(CONTAINER_MATRIX_IDS)
        if CONTAINER_BASE_MATRIX[i][1] is PACKAGE_MANAGER_RPMOSTREE
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
    list(_filter_rpm_ostree_test_cases()),
    indirect=["container_per_test"],
    ids=_filter_rpm_ostree_matrix_ids(),
)
def test_rpm_ostree_install(
    container_per_test: ContainerData,
    guest_per_test: GuestContainer,
    package_manager_class: PackageManagerClass,
    package: Package,
    expected_command: str,
    expected_output: Optional[str],
    root_logger: tmt.log.Logger,
    caplog: _pytest.logging.LogCaptureFixture,
) -> None:
    """Test installing a package with rpm-ostree."""
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


def _rpm_ostree_refresh_metadata_cases() -> Iterator[
    tuple[Container, PackageManagerClass, str, Optional[str]]
]:
    """Generate test cases for rpm-ostree refresh_metadata."""
    yield pytest.param(
        CONTAINER_FEDORA_COREOS_OSTREE,
        PACKAGE_MANAGER_RPMOSTREE,
        r"rpm-ostree refresh-md --force",
        'Available',
        marks=pytest.mark.skip(
            reason="refresh-md does not work with how tmt runs ostree container"
        ),
    )


@pytest.mark.containers
@pytest.mark.parametrize(
    ('container_per_test', 'package_manager_class', 'expected_command', 'expected_output'),
    list(_rpm_ostree_refresh_metadata_cases()),
    indirect=["container_per_test"],
    ids=_filter_rpm_ostree_matrix_ids(),
)
def test_rpm_ostree_refresh_metadata(
    container_per_test: ContainerData,
    guest_per_test: GuestContainer,
    package_manager_class: PackageManagerClass,
    expected_command: str,
    expected_output: Optional[str],
    root_logger: tmt.log.Logger,
    caplog: _pytest.logging.LogCaptureFixture,
) -> None:
    """Test refreshing rpm-ostree metadata."""
    pytest.skip("refresh-md does not work with how tmt runs ostree container")


def _rpm_ostree_nonexistent_cases() -> Iterator[
    tuple[Container, PackageManagerClass, str, Optional[str]]
]:
    """Generate test cases for rpm-ostree nonexistent package install."""
    yield (
        CONTAINER_FEDORA_COREOS_OSTREE,
        PACKAGE_MANAGER_RPMOSTREE,
        r"rpm -q --whatprovides tree-but-spelled-wrong \|\| rpm-ostree install --apply-live --idempotent --allow-inactive --assumeyes  tree-but-spelled-wrong",  # noqa: E501
        'no package provides tree-but-spelled-wrong',
    )


@pytest.mark.containers
@pytest.mark.parametrize(
    ('container', 'package_manager_class', 'expected_command', 'expected_output'),
    list(_rpm_ostree_nonexistent_cases()),
    indirect=["container"],
    ids=_filter_rpm_ostree_matrix_ids(),
)
def test_rpm_ostree_install_nonexistent(
    container: ContainerData,
    guest: GuestContainer,
    package_manager_class: PackageManagerClass,
    expected_command: str,
    expected_output: Optional[str],
    root_logger: tmt.log.Logger,
    caplog: _pytest.logging.LogCaptureFixture,
) -> None:
    """Test attempting to install a nonexistent package with rpm-ostree."""
    do_test_install_nonexistent(
        container,
        guest,
        package_manager_class,
        expected_command,
        expected_output,
        root_logger,
        caplog,
    )


def _rpm_ostree_nonexistent_skip_cases() -> Iterator[
    tuple[Container, PackageManagerClass, str, Optional[str]]
]:
    """Generate test cases for rpm-ostree nonexistent package install with skip_missing."""
    yield (
        CONTAINER_FEDORA_COREOS_OSTREE,
        PACKAGE_MANAGER_RPMOSTREE,
        r"rpm -q --whatprovides tree-but-spelled-wrong \|\| rpm-ostree install --apply-live --idempotent --allow-inactive --assumeyes  tree-but-spelled-wrong \|\| /bin/true",  # noqa: E501
        'no package provides tree-but-spelled-wrong',
    )


@pytest.mark.containers
@pytest.mark.parametrize(
    ('container', 'package_manager_class', 'expected_command', 'expected_output'),
    list(_rpm_ostree_nonexistent_skip_cases()),
    indirect=["container"],
    ids=_filter_rpm_ostree_matrix_ids(),
)
def test_rpm_ostree_install_nonexistent_skip(
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


def _rpm_ostree_install_dont_check_first_cases() -> Iterator[
    tuple[Container, PackageManagerClass, Package, str, Optional[str]]
]:
    """Generate test cases for rpm-ostree install without first checking if installed."""
    yield (
        CONTAINER_FEDORA_COREOS_OSTREE,
        PACKAGE_MANAGER_RPMOSTREE,
        Package('tree'),
        r"rpm-ostree install --apply-live --idempotent --allow-inactive --assumeyes  tree",
        'Installing: tree',
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
    list(_rpm_ostree_install_dont_check_first_cases()),
    indirect=["container_per_test"],
    ids=_filter_rpm_ostree_matrix_ids(),
)
def test_rpm_ostree_install_dont_check_first(
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


def _rpm_ostree_reinstall_cases() -> Iterator[
    tuple[Container, PackageManagerClass, Package, bool, Optional[str], Optional[str]]
]:
    """Generate test cases for rpm-ostree reinstall."""
    yield (
        CONTAINER_FEDORA_COREOS_OSTREE,
        PACKAGE_MANAGER_RPMOSTREE,
        Package('tar'),
        False,
        None,
        None,
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
    list(_rpm_ostree_reinstall_cases()),
    indirect=["container_per_test"],
    ids=_filter_rpm_ostree_matrix_ids(),
)
def test_rpm_ostree_reinstall(
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
    """Test reinstalling a package with rpm-ostree (not supported)."""
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


def _rpm_ostree_check_presence_cases() -> Iterator[
    tuple[Container, PackageManagerClass, Installable, bool, str, Optional[str]]
]:
    """Generate test cases for rpm-ostree check_presence."""
    yield (
        CONTAINER_FEDORA_COREOS_OSTREE,
        PACKAGE_MANAGER_RPMOSTREE,
        Package('util-linux'),
        True,
        r"rpm -q --whatprovides util-linux",
        r'\s+out:\s+util-linux',
    )

    yield (
        CONTAINER_FEDORA_COREOS_OSTREE,
        PACKAGE_MANAGER_RPMOSTREE,
        Package('tree-but-spelled-wrong'),
        False,
        r"rpm -q --whatprovides tree-but-spelled-wrong",
        r'\s+out:\s+no package provides tree-but-spelled-wrong',
    )

    yield (
        CONTAINER_FEDORA_COREOS_OSTREE,
        PACKAGE_MANAGER_RPMOSTREE,
        FileSystemPath('/usr/bin/flock'),
        True,
        r"rpm -qf /usr/bin/flock",
        r'\s+out:\s+util-linux-core',
    )


def _rpm_ostree_check_presence_ids(value) -> str:
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
    list(_rpm_ostree_check_presence_cases()),
    indirect=["container"],
    ids=_rpm_ostree_check_presence_ids,
)
def test_rpm_ostree_check_presence(
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
    """Test checking if a package or file is present with rpm-ostree."""
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


def _rpm_ostree_install_filesystempath_cases() -> Iterator[
    tuple[Container, PackageManagerClass, FileSystemPath, str, Optional[str]]
]:
    """Generate test cases for rpm-ostree install with filesystem path."""
    yield (
        CONTAINER_FEDORA_COREOS_OSTREE,
        PACKAGE_MANAGER_RPMOSTREE,
        FileSystemPath('/usr/bin/dos2unix'),
        r"rpm -qf /usr/bin/dos2unix \|\| rpm-ostree install --apply-live --idempotent --allow-inactive --assumeyes  /usr/bin/dos2unix",  # noqa: E501
        "Installing 1 packages:\n  dos2unix-",
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
    list(_rpm_ostree_install_filesystempath_cases()),
    indirect=["container_per_test"],
    ids=_filter_rpm_ostree_matrix_ids(),
)
def test_rpm_ostree_install_filesystempath(
    container_per_test: ContainerData,
    guest_per_test: GuestContainer,
    package_manager_class: PackageManagerClass,
    installable: FileSystemPath,
    expected_command: str,
    expected_output: Optional[str],
    root_logger: tmt.log.Logger,
    caplog: _pytest.logging.LogCaptureFixture,
) -> None:
    """Test installing a package by filesystem path with rpm-ostree."""
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


def _rpm_ostree_install_multiple_cases() -> Iterator[
    tuple[Container, PackageManagerClass, tuple[Package, Package], str, Optional[str]]
]:
    """Generate test cases for installing multiple packages with rpm-ostree."""
    yield (
        CONTAINER_FEDORA_COREOS_OSTREE,
        PACKAGE_MANAGER_RPMOSTREE,
        (Package('tree'), Package('nano')),
        r"rpm -q --whatprovides tree nano \|\| rpm-ostree install --apply-live --idempotent --allow-inactive --assumeyes  tree nano",  # noqa: E501
        'Installing: tree',
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
    list(_rpm_ostree_install_multiple_cases()),
    indirect=["container_per_test"],
    ids=_filter_rpm_ostree_matrix_ids(),
)
def test_rpm_ostree_install_multiple(
    container_per_test: ContainerData,
    guest_per_test: GuestContainer,
    package_manager_class: PackageManagerClass,
    packages: tuple[Package, Package],
    expected_command: str,
    expected_output: Optional[str],
    root_logger: tmt.log.Logger,
    caplog: _pytest.logging.LogCaptureFixture,
) -> None:
    """Test installing multiple packages with rpm-ostree."""
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
