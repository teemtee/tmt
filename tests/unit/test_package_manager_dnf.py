"""
Tests for DNF package manager family (dnf, dnf5, yum)
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
    Package,
    PackageManagerClass,
)
from tmt.steps.provision.podman import GuestContainer

from ._test_package_manager import (
    CONTAINER_BASE_MATRIX,
    CONTAINER_CENTOS_7,
    CONTAINER_CENTOS_STREAM_9,
    CONTAINER_CENTOS_STREAM_10,
    CONTAINER_FEDORA_40,
    CONTAINER_FEDORA_41,
    CONTAINER_FEDORA_RAWHIDE,
    CONTAINER_MATRIX_IDS,
    CONTAINER_UBI_8,
    PACKAGE_MANAGER_DNF,
    PACKAGE_MANAGER_DNF5,
    PACKAGE_MANAGER_YUM,
    do_test_install,
    do_test_install_debuginfo,
    do_test_install_downloaded,
    do_test_refresh_metadata,
    do_test_reinstall,
)


def _filter_dnf_family_test_cases() -> Iterator[
    tuple[Container, PackageManagerClass, Package, str, Optional[str]]
]:
    """Filter dnf-family test cases from the container matrix."""
    for container, package_manager_class in CONTAINER_BASE_MATRIX:
        if package_manager_class not in [
            PACKAGE_MANAGER_DNF,
            PACKAGE_MANAGER_DNF5,
            PACKAGE_MANAGER_YUM,
        ]:
            continue

        if package_manager_class is PACKAGE_MANAGER_YUM:
            if container.url == CONTAINER_FEDORA_RAWHIDE.url:
                yield (
                    container,
                    package_manager_class,
                    Package('tree'),
                    r"rpm -q --whatprovides tree \|\| yum install -y  tree && rpm -q --whatprovides tree",  # noqa: E501
                    'Installing:',
                )

            elif 'ubi/8' in container.url:
                yield (
                    container,
                    package_manager_class,
                    Package('dconf'),
                    r"rpm -q --whatprovides dconf \|\| yum install -y  dconf && rpm -q --whatprovides dconf",  # noqa: E501
                    'Installed:\n  dconf',
                )

            else:
                yield (
                    container,
                    package_manager_class,
                    Package('tree'),
                    r"rpm -q --whatprovides tree \|\| yum install -y  tree && rpm -q --whatprovides tree",  # noqa: E501
                    'Installed:\n  tree',
                )

        elif package_manager_class is PACKAGE_MANAGER_DNF:
            if container.url == CONTAINER_FEDORA_RAWHIDE.url:
                yield (
                    container,
                    package_manager_class,
                    Package('tree'),
                    r"rpm -q --whatprovides tree \|\| dnf install -y  tree",
                    'Installing:',
                )

            elif 'ubi/8' in container.url:
                yield (
                    container,
                    package_manager_class,
                    Package('dconf'),
                    r"rpm -q --whatprovides dconf \|\| dnf install -y  dconf",
                    'Installed:\n  dconf',
                )

            else:
                yield (
                    container,
                    package_manager_class,
                    Package('tree'),
                    r"rpm -q --whatprovides tree \|\| dnf install -y  tree",
                    'Installed:\n  tree',
                )

        elif package_manager_class is PACKAGE_MANAGER_DNF5:
            yield (
                container,
                package_manager_class,
                Package('tree'),
                r"rpm -q --whatprovides tree \|\| dnf5 install -y  tree",
                'Installing:',
            )


def _filter_dnf_family_matrix_ids() -> list[str]:
    """Filter dnf-family test IDs from the container matrix."""
    return [
        matrix_id
        for i, matrix_id in enumerate(CONTAINER_MATRIX_IDS)
        if CONTAINER_BASE_MATRIX[i][1]
        in [PACKAGE_MANAGER_DNF, PACKAGE_MANAGER_DNF5, PACKAGE_MANAGER_YUM]
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
    list(_filter_dnf_family_test_cases()),
    indirect=["container_per_test"],
    ids=_filter_dnf_family_matrix_ids(),
)
def test_dnf_family_install(
    container_per_test: ContainerData,
    guest_per_test: GuestContainer,
    package_manager_class: PackageManagerClass,
    package: Package,
    expected_command: str,
    expected_output: Optional[str],
    root_logger: tmt.log.Logger,
    caplog: _pytest.logging.LogCaptureFixture,
) -> None:
    """Test installing a package with dnf/dnf5/yum."""
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


def _dnf_family_refresh_metadata_cases() -> Iterator[
    tuple[Container, PackageManagerClass, str, Optional[str]]
]:
    """Generate test cases for dnf/dnf5/yum refresh_metadata."""
    # YUM cases
    for container in [
        CONTAINER_CENTOS_7,
        CONTAINER_CENTOS_STREAM_9,
        CONTAINER_UBI_8,
        CONTAINER_FEDORA_40,
    ]:
        yield (
            container,
            PACKAGE_MANAGER_YUM,
            r"yum makecache",
            'Metadata',
        )

    # DNF cases
    for container in [
        CONTAINER_CENTOS_STREAM_9,
        CONTAINER_CENTOS_STREAM_10,
        CONTAINER_UBI_8,
        CONTAINER_FEDORA_40,
    ]:
        yield (
            container,
            PACKAGE_MANAGER_DNF,
            r"dnf makecache -y --refresh",
            'Metadata cache created',
        )

    # DNF5 cases
    for container in [CONTAINER_FEDORA_RAWHIDE, CONTAINER_FEDORA_41, CONTAINER_FEDORA_40]:
        yield (
            container,
            PACKAGE_MANAGER_DNF5,
            r"dnf5 makecache -y --refresh",
            'Metadata cache created',
        )


@pytest.mark.containers
@pytest.mark.parametrize(
    ('container_per_test', 'package_manager_class', 'expected_command', 'expected_output'),
    list(_dnf_family_refresh_metadata_cases()),
    indirect=["container_per_test"],
    ids=_filter_dnf_family_matrix_ids(),
)
def test_dnf_family_refresh_metadata(
    container_per_test: ContainerData,
    guest_per_test: GuestContainer,
    package_manager_class: PackageManagerClass,
    expected_command: str,
    expected_output: Optional[str],
    root_logger: tmt.log.Logger,
    caplog: _pytest.logging.LogCaptureFixture,
) -> None:
    """Test refreshing metadata with dnf/dnf5/yum."""
    do_test_refresh_metadata(
        container_per_test,
        guest_per_test,
        package_manager_class,
        expected_command,
        expected_output,
        root_logger,
        caplog,
    )


def _dnf_reinstall_cases() -> Iterator[
    tuple[Container, PackageManagerClass, Package, bool, Optional[str], Optional[str]]
]:
    """Generate test cases for dnf/dnf5/yum reinstall."""
    # YUM cases
    for container in [CONTAINER_CENTOS_7]:
        yield (
            container,
            PACKAGE_MANAGER_YUM,
            Package('tar'),
            True,
            r"rpm -q --whatprovides tar && yum reinstall -y  tar && rpm -q --whatprovides tar",
            'Reinstalling:\n tar',
        )

    for container in [CONTAINER_CENTOS_STREAM_9, CONTAINER_UBI_8, CONTAINER_FEDORA_40]:
        yield (
            container,
            PACKAGE_MANAGER_YUM,
            Package('tar'),
            True,
            r"rpm -q --whatprovides tar && yum reinstall -y  tar && rpm -q --whatprovides tar",
            'Reinstalled:\n  tar',
        )

    # DNF cases
    for container in [
        CONTAINER_CENTOS_STREAM_9,
        CONTAINER_CENTOS_STREAM_10,
        CONTAINER_UBI_8,
        CONTAINER_FEDORA_40,
    ]:
        yield (
            container,
            PACKAGE_MANAGER_DNF,
            Package('tar'),
            True,
            r"rpm -q --whatprovides tar && dnf reinstall -y  tar",
            'Reinstalled:\n  tar',
        )

    # DNF5 cases
    for container in [CONTAINER_FEDORA_RAWHIDE, CONTAINER_FEDORA_41, CONTAINER_FEDORA_40]:
        yield (
            container,
            PACKAGE_MANAGER_DNF5,
            Package('tar'),
            True,
            r"rpm -q --whatprovides tar && dnf5 reinstall -y  tar",
            'Reinstalling tar',
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
    list(_dnf_reinstall_cases()),
    indirect=["container_per_test"],
    ids=_filter_dnf_family_matrix_ids(),
)
def test_dnf_family_reinstall(
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
    """Test reinstalling a package with dnf/dnf5/yum."""
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


def _dnf_debuginfo_install_cases() -> Iterator[
    tuple[Container, PackageManagerClass, tuple[Package, Package], str, Optional[str]]
]:
    """Generate test cases for dnf/dnf5/yum debuginfo install."""
    # DNF5 cases
    for container in [CONTAINER_FEDORA_RAWHIDE, CONTAINER_FEDORA_41, CONTAINER_FEDORA_40]:
        yield (
            container,
            PACKAGE_MANAGER_DNF5,
            (Package('dos2unix'), Package('tree')),
            r"rpm -q --whatprovides /usr/bin/debuginfo-install \|\| dnf5 install -y  /usr/bin/debuginfo-install && debuginfo-install -y  dos2unix tree && rpm -q dos2unix-debuginfo tree-debuginfo",  # noqa: E501
            None,
        )

    # DNF cases - UBI
    for container in [CONTAINER_UBI_8]:
        yield (
            container,
            PACKAGE_MANAGER_DNF,
            (Package('dconf'), Package('libpng')),
            r"rpm -q --whatprovides /usr/bin/debuginfo-install \|\| dnf install -y  /usr/bin/debuginfo-install && debuginfo-install -y  dconf libpng && rpm -q dconf-debuginfo libpng-debuginfo",  # noqa: E501
            None,
        )

    # DNF cases - Fedora
    for container in [CONTAINER_FEDORA_40]:
        yield (
            container,
            PACKAGE_MANAGER_DNF,
            (Package('dos2unix'), Package('tree')),
            r"rpm -q --whatprovides /usr/bin/debuginfo-install \|\| dnf install -y  /usr/bin/debuginfo-install && debuginfo-install -y  dos2unix tree && rpm -q dos2unix-debuginfo tree-debuginfo",  # noqa: E501
            None,
        )

    # YUM cases - UBI
    for container in [CONTAINER_UBI_8]:
        yield (
            container,
            PACKAGE_MANAGER_YUM,
            (Package('dconf'), Package('libpng')),
            r"rpm -q --whatprovides /usr/bin/debuginfo-install \|\| yum install -y  /usr/bin/debuginfo-install && rpm -q --whatprovides /usr/bin/debuginfo-install && debuginfo-install -y  dconf libpng && rpm -q dconf-debuginfo libpng-debuginfo",  # noqa: E501
            None,
        )

    # YUM cases - Fedora
    for container in [CONTAINER_FEDORA_40]:
        yield (
            container,
            PACKAGE_MANAGER_YUM,
            (Package('dos2unix'), Package('tree')),
            r"rpm -q --whatprovides /usr/bin/debuginfo-install \|\| yum install -y  /usr/bin/debuginfo-install && rpm -q --whatprovides /usr/bin/debuginfo-install && debuginfo-install -y  dos2unix tree && rpm -q dos2unix-debuginfo tree-debuginfo",  # noqa: E501
            None,
        )


@pytest.mark.containers
@pytest.mark.parametrize(
    (
        'container_per_test',
        'package_manager_class',
        'installables',
        'expected_command',
        'expected_output',
    ),
    list(_dnf_debuginfo_install_cases()),
    indirect=["container_per_test"],
    ids=_filter_dnf_family_matrix_ids(),
)
def test_dnf_family_install_debuginfo(
    container_per_test: ContainerData,
    guest_per_test: GuestContainer,
    package_manager_class: PackageManagerClass,
    installables: tuple[Package, Package],
    expected_command: str,
    expected_output: Optional[str],
    root_logger: tmt.log.Logger,
    caplog: _pytest.logging.LogCaptureFixture,
) -> None:
    """Test installing debuginfo packages with dnf/dnf5/yum."""
    do_test_install_debuginfo(
        container_per_test,
        guest_per_test,
        package_manager_class,
        installables,
        expected_command,
        expected_output,
        root_logger,
        caplog,
    )


def _dnf_downloaded_install_cases() -> Iterator[
    tuple[
        Container,
        PackageManagerClass,
        tuple[Package, Package],
        tuple[str, str],
        str,
        Optional[str],
    ]
]:
    """Generate test cases for installing downloaded packages with dnf/dnf5/yum."""
    # YUM cases - UBI
    for container in [CONTAINER_UBI_8]:
        yield (
            container,
            PACKAGE_MANAGER_YUM,
            (Package('dconf'), Package('libpng')),
            ('dconf*.x86_64.rpm', 'libpng*.x86_64.rpm'),
            r"yum install -y --skip-broken /tmp/dconf.rpm /tmp/libpng.rpm \|\| /bin/true",
            'Complete!',
        )

    # YUM cases - Fedora
    for container in [CONTAINER_FEDORA_40]:
        yield (
            container,
            PACKAGE_MANAGER_YUM,
            (Package('tree'), Package('nano')),
            ('tree*.x86_64.rpm', 'nano*.x86_64.rpm'),
            r"yum install -y --skip-broken /tmp/tree.rpm /tmp/nano.rpm \|\| /bin/true",
            'Complete!',
        )

    # DNF cases - UBI
    for container in [CONTAINER_UBI_8]:
        yield (
            container,
            PACKAGE_MANAGER_DNF,
            (Package('dconf'), Package('libpng')),
            ('dconf*.x86_64.rpm', 'libpng*.x86_64.rpm'),
            r"dnf install -y  /tmp/dconf.rpm /tmp/libpng.rpm",
            'Complete!',
        )

    # DNF cases - Fedora
    for container in [CONTAINER_FEDORA_40]:
        yield (
            container,
            PACKAGE_MANAGER_DNF,
            (Package('tree'), Package('nano')),
            ('tree*.x86_64.rpm', 'nano*.x86_64.rpm'),
            r"dnf install -y  /tmp/tree.rpm /tmp/nano.rpm",
            'Complete!',
        )

    # DNF5 cases
    for container in [CONTAINER_FEDORA_41]:
        yield (
            container,
            PACKAGE_MANAGER_DNF5,
            (Package('tree'), Package('nano')),
            ('tree*.x86_64.rpm', 'nano*.x86_64.rpm'),
            r"dnf5 install -y  /tmp/tree.rpm /tmp/nano.rpm",
            None,
        )


@pytest.mark.containers
@pytest.mark.parametrize(
    (
        'container_per_test',
        'package_manager_class',
        'packages',
        'artifacts',
        'expected_command',
        'expected_output',
    ),
    list(_dnf_downloaded_install_cases()),
    indirect=["container_per_test"],
    ids=_filter_dnf_family_matrix_ids(),
)
def test_dnf_family_install_downloaded(
    container_per_test: ContainerData,
    guest_per_test: GuestContainer,
    package_manager_class: PackageManagerClass,
    packages: tuple[Package, Package],
    artifacts: tuple[str, str],
    expected_command: str,
    expected_output: Optional[str],
    root_logger: tmt.log.Logger,
    caplog: _pytest.logging.LogCaptureFixture,
) -> None:
    """Test installing downloaded packages with dnf/dnf5/yum."""
    do_test_install_downloaded(
        container_per_test,
        guest_per_test,
        package_manager_class,
        packages,
        artifacts,
        expected_command,
        expected_output,
        root_logger,
        caplog,
    )
