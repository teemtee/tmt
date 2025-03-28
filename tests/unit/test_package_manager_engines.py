"""
Tests for package manager engines
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
    Package,
    PackageManagerClass,
)
from tmt.steps.provision.podman import GuestContainer

from ._test_package_manager import (
    CONTAINER_BASE_MATRIX,
    CONTAINER_FEDORA_RAWHIDE,
    CONTAINER_MATRIX_IDS,
    do_test_install,
    do_test_install_dont_check_first,
    do_test_install_filesystempath,
    do_test_install_multiple,
    do_test_install_nonexistent,
    do_test_install_nonexistent_skip,
)


def _parametrize_test_install() -> Iterator[
    tuple[Container, PackageManagerClass, Package, str, Optional[str]]
]:
    for container, package_manager_class in CONTAINER_BASE_MATRIX:
        if package_manager_class is tmt.package_managers.dnf.Yum:
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

        elif package_manager_class is tmt.package_managers.dnf.Dnf:
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

        elif package_manager_class is tmt.package_managers.dnf.Dnf5:
            yield (
                container,
                package_manager_class,
                Package('tree'),
                r"rpm -q --whatprovides tree \|\| dnf5 install -y  tree",
                'Installing:',
            )

        elif package_manager_class is tmt.package_managers.apt.Apt:
            yield (
                container,
                package_manager_class,
                Package('tree'),
                r"export DEBIAN_FRONTEND=noninteractive;\s+installable_packages=\"tree\";\s+dpkg-query --show \$installable_packages \\\s+\|\| apt install -y  \$installable_packages",  # noqa: E501
                'Setting up tree',
            )

        elif package_manager_class is tmt.package_managers.rpm_ostree.RpmOstree:
            yield (
                container,
                package_manager_class,
                Package('tree'),
                r"rpm -q --whatprovides tree \|\| rpm-ostree install --apply-live --idempotent --allow-inactive --assumeyes  tree",  # noqa: E501
                'Installing: tree',
            )

        elif package_manager_class is tmt.package_managers.apk.Apk:
            yield (
                container,
                package_manager_class,
                Package('tree'),
                r"apk info -e tree \|\| apk add tree",
                'Installing tree',
            )

        else:
            pytest.fail(f"Unhandled package manager class '{package_manager_class}'.")


@pytest.mark.containers
@pytest.mark.parametrize(
    (
        'container_per_test',
        'package_manager_class',
        'package',
        'expected_command',
        'expected_output',
    ),
    list(_parametrize_test_install()),
    indirect=["container_per_test"],
    ids=CONTAINER_MATRIX_IDS,
)
def test_install(
    container_per_test: ContainerData,
    guest_per_test: GuestContainer,
    package_manager_class: PackageManagerClass,
    package: Package,
    expected_command: str,
    expected_output: Optional[str],
    root_logger: tmt.log.Logger,
    caplog: _pytest.logging.LogCaptureFixture,
) -> None:
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


def _parametrize_test_install_nonexistent() -> Iterator[
    tuple[Container, PackageManagerClass, str, Optional[str]]
]:
    for container, package_manager_class in CONTAINER_BASE_MATRIX:
        if package_manager_class is tmt.package_managers.dnf.Dnf5:
            yield (
                container,
                package_manager_class,
                r"rpm -q --whatprovides tree-but-spelled-wrong \|\| dnf5 install -y  tree-but-spelled-wrong",  # noqa: E501
                'No match for argument: tree-but-spelled-wrong',
            )

        elif package_manager_class is tmt.package_managers.dnf.Dnf:
            if container.url == CONTAINER_FEDORA_RAWHIDE.url:
                yield (
                    container,
                    package_manager_class,
                    r"rpm -q --whatprovides tree-but-spelled-wrong \|\| dnf install -y  tree-but-spelled-wrong",  # noqa: E501
                    'No match for argument: tree-but-spelled-wrong',
                )

            else:
                yield (
                    container,
                    package_manager_class,
                    r"rpm -q --whatprovides tree-but-spelled-wrong \|\| dnf install -y  tree-but-spelled-wrong",  # noqa: E501
                    'Error: Unable to find a match: tree-but-spelled-wrong',
                )

        elif package_manager_class is tmt.package_managers.dnf.Yum:
            if container.url == CONTAINER_FEDORA_RAWHIDE.url:
                yield (
                    container,
                    package_manager_class,
                    r"rpm -q --whatprovides tree-but-spelled-wrong \|\| yum install -y  tree-but-spelled-wrong && rpm -q --whatprovides tree-but-spelled-wrong",  # noqa: E501
                    'No match for argument: tree-but-spelled-wrong',
                )

            elif 'fedora' in container.url:
                yield (
                    container,
                    package_manager_class,
                    r"rpm -q --whatprovides tree-but-spelled-wrong \|\| yum install -y  tree-but-spelled-wrong && rpm -q --whatprovides tree-but-spelled-wrong",  # noqa: E501
                    'Error: Unable to find a match: tree-but-spelled-wrong',
                )

            elif (
                'centos' in container.url and 'centos/7' not in container.url
            ) or 'ubi/8' in container.url:
                yield (
                    container,
                    package_manager_class,
                    r"rpm -q --whatprovides tree-but-spelled-wrong \|\| yum install -y  tree-but-spelled-wrong && rpm -q --whatprovides tree-but-spelled-wrong",  # noqa: E501
                    'No match for argument: tree-but-spelled-wrong',
                )

            else:
                yield (
                    container,
                    package_manager_class,
                    r"rpm -q --whatprovides tree-but-spelled-wrong \|\| yum install -y  tree-but-spelled-wrong && rpm -q --whatprovides tree-but-spelled-wrong",  # noqa: E501
                    'No package tree-but-spelled-wrong available.',
                )

        elif package_manager_class is tmt.package_managers.apt.Apt:
            yield (
                container,
                package_manager_class,
                r"export DEBIAN_FRONTEND=noninteractive;\s+installable_packages=\"tree-but-spelled-wrong\";\s+dpkg-query --show \$installable_packages \\\s+\|\| apt install -y  \$installable_packages",  # noqa: E501
                'E: Unable to locate package tree-but-spelled-wrong',
            )

        elif package_manager_class is tmt.package_managers.rpm_ostree.RpmOstree:
            yield (
                container,
                package_manager_class,
                r"rpm -q --whatprovides tree-but-spelled-wrong \|\| rpm-ostree install --apply-live --idempotent --allow-inactive --assumeyes  tree-but-spelled-wrong",  # noqa: E501
                'no package provides tree-but-spelled-wrong',
            )

        elif package_manager_class is tmt.package_managers.apk.Apk:
            yield (
                container,
                package_manager_class,
                r"apk info -e tree-but-spelled-wrong \|\| apk add tree-but-spelled-wrong",
                'ERROR: unable to select packages:\n  tree-but-spelled-wrong (no such package):\n    required by: world[tree-but-spelled-wrong]',  # noqa: E501
            )

        else:
            pytest.fail(f"Unhandled package manager class '{package_manager_class}'.")


@pytest.mark.containers
@pytest.mark.parametrize(
    ('container', 'package_manager_class', 'expected_command', 'expected_output'),
    list(_parametrize_test_install_nonexistent()),
    indirect=["container"],
    ids=CONTAINER_MATRIX_IDS,
)
def test_install_nonexistent(
    container: ContainerData,
    guest: GuestContainer,
    package_manager_class: PackageManagerClass,
    expected_command: str,
    expected_output: Optional[str],
    root_logger: tmt.log.Logger,
    caplog: _pytest.logging.LogCaptureFixture,
) -> None:
    do_test_install_nonexistent(
        container,
        guest,
        package_manager_class,
        expected_command,
        expected_output,
        root_logger,
        caplog,
    )


def _parametrize_test_install_nonexistent_skip() -> Iterator[
    tuple[Container, PackageManagerClass, str, Optional[str]]
]:
    for container, package_manager_class in CONTAINER_BASE_MATRIX:
        if package_manager_class is tmt.package_managers.dnf.Dnf5:
            yield (
                container,
                package_manager_class,
                r"rpm -q --whatprovides tree-but-spelled-wrong \|\| dnf5 install -y --skip-unavailable tree-but-spelled-wrong",  # noqa: E501
                None,
            )

        elif package_manager_class is tmt.package_managers.dnf.Dnf:
            yield (
                container,
                package_manager_class,
                r"rpm -q --whatprovides tree-but-spelled-wrong \|\| dnf install -y --skip-broken tree-but-spelled-wrong",  # noqa: E501
                'No match for argument: tree-but-spelled-wrong',
            )

        elif package_manager_class is tmt.package_managers.dnf.Yum:
            if container.url == CONTAINER_FEDORA_RAWHIDE.url:  # noqa: SIM114
                yield (
                    container,
                    package_manager_class,
                    r"rpm -q --whatprovides tree-but-spelled-wrong \|\| yum install -y --skip-broken tree-but-spelled-wrong \|\| /bin/true",  # noqa: E501
                    'No match for argument: tree-but-spelled-wrong',
                )

            elif 'fedora' in container.url:  # noqa: SIM114
                yield (
                    container,
                    package_manager_class,
                    r"rpm -q --whatprovides tree-but-spelled-wrong \|\| yum install -y --skip-broken tree-but-spelled-wrong \|\| /bin/true",  # noqa: E501
                    'No match for argument: tree-but-spelled-wrong',
                )

            elif (
                'centos' in container.url and 'centos/7' not in container.url
            ) or 'ubi/8' in container.url:
                yield (
                    container,
                    package_manager_class,
                    r"rpm -q --whatprovides tree-but-spelled-wrong \|\| yum install -y --skip-broken tree-but-spelled-wrong \|\| /bin/true",  # noqa: E501
                    'No match for argument: tree-but-spelled-wrong',
                )

            else:
                yield (
                    container,
                    package_manager_class,
                    r"rpm -q --whatprovides tree-but-spelled-wrong \|\| yum install -y --skip-broken tree-but-spelled-wrong \|\| /bin/true",  # noqa: E501
                    'No package tree-but-spelled-wrong available.',
                )

        elif package_manager_class is tmt.package_managers.apt.Apt:
            yield (
                container,
                package_manager_class,
                r"export DEBIAN_FRONTEND=noninteractive;\s+installable_packages=\"tree-but-spelled-wrong\";\s+dpkg-query --show \$installable_packages \\\s+\|\| apt install -y --ignore-missing \$installable_packages",  # noqa: E501
                'E: Unable to locate package tree-but-spelled-wrong',
            )

        elif package_manager_class is tmt.package_managers.rpm_ostree.RpmOstree:
            yield (
                container,
                package_manager_class,
                r"rpm -q --whatprovides tree-but-spelled-wrong \|\| rpm-ostree install --apply-live --idempotent --allow-inactive --assumeyes  tree-but-spelled-wrong \|\| /bin/true",  # noqa: E501
                'no package provides tree-but-spelled-wrong',
            )

        elif package_manager_class is tmt.package_managers.apk.Apk:
            yield (
                container,
                package_manager_class,
                r"apk info -e tree-but-spelled-wrong \|\| apk add tree-but-spelled-wrong \|\| /bin/true",  # noqa: E501
                'ERROR: unable to select packages:\n  tree-but-spelled-wrong (no such package):\n    required by: world[tree-but-spelled-wrong]',  # noqa: E501
            )

        else:
            pytest.fail(f"Unhandled package manager class '{package_manager_class}'.")


@pytest.mark.containers
@pytest.mark.parametrize(
    ('container', 'package_manager_class', 'expected_command', 'expected_output'),
    list(_parametrize_test_install_nonexistent_skip()),
    indirect=["container"],
    ids=CONTAINER_MATRIX_IDS,
)
def test_install_nonexistent_skip(
    container: ContainerData,
    guest: GuestContainer,
    package_manager_class: PackageManagerClass,
    expected_command: str,
    expected_output: Optional[str],
    root_logger: tmt.log.Logger,
    caplog: _pytest.logging.LogCaptureFixture,
) -> None:
    do_test_install_nonexistent_skip(
        container,
        guest,
        package_manager_class,
        expected_command,
        expected_output,
        root_logger,
        caplog,
    )


def _parametrize_test_install_dont_check_first() -> Iterator[
    tuple[Container, PackageManagerClass, Package, str, Optional[str]]
]:
    for container, package_manager_class in CONTAINER_BASE_MATRIX:
        if package_manager_class is tmt.package_managers.dnf.Dnf5:
            yield container, package_manager_class, Package('tree'), r"dnf5 install -y  tree", None

        elif package_manager_class is tmt.package_managers.dnf.Dnf:
            if 'ubi/8' in container.url:
                yield (
                    container,
                    package_manager_class,
                    Package('dconf'),
                    r"dnf install -y  dconf",
                    'Installed:\n  dconf',
                )
            else:
                yield (
                    container,
                    package_manager_class,
                    Package('tree'),
                    r"dnf install -y  tree",
                    'Installed:\n  tree',
                )

        elif package_manager_class is tmt.package_managers.dnf.Yum:
            if 'ubi/8' in container.url:
                yield (
                    container,
                    package_manager_class,
                    Package('dconf'),
                    r"yum install -y  dconf && rpm -q --whatprovides dconf",
                    'Installed:\n  dconf',
                )

            else:
                yield (
                    container,
                    package_manager_class,
                    Package('tree'),
                    r"yum install -y  tree && rpm -q --whatprovides tree",
                    'Installed:\n  tree',
                )

        elif package_manager_class is tmt.package_managers.apt.Apt:
            yield (
                container,
                package_manager_class,
                Package('tree'),
                r"export DEBIAN_FRONTEND=noninteractive;\s+installable_packages=\"tree\";\s+/bin/false \\\s+\|\| apt install -y  \$installable_packages",  # noqa: E501
                'Setting up tree',
            )

        elif package_manager_class is tmt.package_managers.rpm_ostree.RpmOstree:
            yield (
                container,
                package_manager_class,
                Package('tree'),
                r"rpm-ostree install --apply-live --idempotent --allow-inactive --assumeyes  tree",
                'Installing: tree',
            )

        elif package_manager_class is tmt.package_managers.apk.Apk:
            yield (
                container,
                package_manager_class,
                Package('tree'),
                r"apk add tree",
                'Installing tree',
            )

        else:
            pytest.fail(f"Unhandled package manager class '{package_manager_class}'.")


@pytest.mark.containers
@pytest.mark.parametrize(
    (
        'container_per_test',
        'package_manager_class',
        'package',
        'expected_command',
        'expected_output',
    ),
    list(_parametrize_test_install_dont_check_first()),
    indirect=["container_per_test"],
    ids=CONTAINER_MATRIX_IDS,
)
def test_install_dont_check_first(
    container_per_test: ContainerData,
    guest_per_test: GuestContainer,
    package_manager_class: PackageManagerClass,
    package: Package,
    expected_command: str,
    expected_output: Optional[str],
    root_logger: tmt.log.Logger,
    caplog: _pytest.logging.LogCaptureFixture,
) -> None:
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


def _parametrize_test_install_filesystempath() -> Iterator[
    tuple[Container, PackageManagerClass, FileSystemPath, Optional[str]]
]:
    for container, package_manager_class in CONTAINER_BASE_MATRIX:
        if package_manager_class is tmt.package_managers.dnf.Dnf5:
            yield (
                container,
                package_manager_class,
                FileSystemPath('/usr/bin/dos2unix'),
                r"rpm -q --whatprovides /usr/bin/dos2unix \|\| dnf5 install -y  /usr/bin/dos2unix",
                '[1/1] dos2unix',
            )

        elif package_manager_class is tmt.package_managers.dnf.Dnf:
            yield (
                container,
                package_manager_class,
                FileSystemPath('/usr/bin/dos2unix'),
                r"rpm -q --whatprovides /usr/bin/dos2unix \|\| dnf install -y  /usr/bin/dos2unix",
                'Installed:\n  dos2unix-',
            )

        elif package_manager_class is tmt.package_managers.dnf.Yum:
            if 'centos/7' in container.url:
                yield (
                    container,
                    package_manager_class,
                    FileSystemPath('/usr/bin/dos2unix'),
                    r"rpm -q --whatprovides /usr/bin/dos2unix \|\| yum install -y  /usr/bin/dos2unix && rpm -q --whatprovides /usr/bin/dos2unix",  # noqa: E501
                    'Installed:\n  dos2unix.',
                )

            else:
                yield (
                    container,
                    package_manager_class,
                    FileSystemPath('/usr/bin/dos2unix'),
                    r"rpm -q --whatprovides /usr/bin/dos2unix \|\| yum install -y  /usr/bin/dos2unix && rpm -q --whatprovides /usr/bin/dos2unix",  # noqa: E501
                    'Installed:\n  dos2unix-',
                )

        elif package_manager_class is tmt.package_managers.apt.Apt:
            yield (
                container,
                package_manager_class,
                FileSystemPath('/usr/bin/dos2unix'),
                r"export DEBIAN_FRONTEND=noninteractive.*fs_path_package=\"\$\(apt-file search --package-only /usr/bin/dos2unix\)\".*apt install -y.*\$installable_packages",  # noqa: E501
                "Setting up dos2unix",
            )

        elif package_manager_class is tmt.package_managers.rpm_ostree.RpmOstree:
            yield (
                container,
                package_manager_class,
                FileSystemPath('/usr/bin/dos2unix'),
                r"rpm -qf /usr/bin/dos2unix \|\| rpm-ostree install --apply-live --idempotent --allow-inactive --assumeyes  /usr/bin/dos2unix",  # noqa: E501
                "Installing 1 packages:\n  dos2unix-",
            )

        elif package_manager_class is tmt.package_managers.apk.Apk:
            yield (
                container,
                package_manager_class,
                FileSystemPath('/usr/bin/dos2unix'),
                r"apk info -e dos2unix \|\| apk add dos2unix",
                'Installing dos2unix',
            )

        else:
            pytest.fail(f"Unhandled package manager class '{package_manager_class}'.")


@pytest.mark.containers
@pytest.mark.parametrize(
    (
        'container_per_test',
        'package_manager_class',
        'installable',
        'expected_command',
        'expected_output',
    ),
    list(_parametrize_test_install_filesystempath()),
    indirect=["container_per_test"],
    ids=CONTAINER_MATRIX_IDS,
)
def test_install_filesystempath(
    container_per_test: ContainerData,
    guest_per_test: GuestContainer,
    package_manager_class: PackageManagerClass,
    installable: FileSystemPath,
    expected_command: str,
    expected_output: Optional[str],
    root_logger: tmt.log.Logger,
    caplog: _pytest.logging.LogCaptureFixture,
) -> None:
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


def _parametrize_test_install_multiple() -> Iterator[
    tuple[Container, PackageManagerClass, tuple[Package, Package], str, Optional[str]]
]:
    for container, package_manager_class in CONTAINER_BASE_MATRIX:
        if package_manager_class is tmt.package_managers.dnf.Yum:
            if 'ubi/8' in container.url:
                yield (
                    container,
                    package_manager_class,
                    (Package('dconf'), Package('libpng')),
                    r"rpm -q --whatprovides dconf libpng \|\| yum install -y  dconf libpng && rpm -q --whatprovides dconf libpng",  # noqa: E501
                    'Complete!',
                )

            elif 'centos' in container.url:
                yield (
                    container,
                    package_manager_class,
                    (Package('tree'), Package('diffutils')),
                    r"rpm -q --whatprovides tree diffutils \|\| yum install -y  tree diffutils && rpm -q --whatprovides tree diffutils",  # noqa: E501
                    'Complete!',
                )

            else:
                yield (
                    container,
                    package_manager_class,
                    (Package('tree'), Package('nano')),
                    r"rpm -q --whatprovides tree nano \|\| yum install -y  tree nano && rpm -q --whatprovides tree nano",  # noqa: E501
                    'Complete!',
                )

        elif package_manager_class is tmt.package_managers.dnf.Dnf:
            if 'ubi/8' in container.url:
                yield (
                    container,
                    package_manager_class,
                    (Package('dconf'), Package('libpng')),
                    r"rpm -q --whatprovides dconf libpng \|\| dnf install -y  dconf libpng",
                    'Complete!',
                )

            elif 'centos' in container.url:
                yield (
                    container,
                    package_manager_class,
                    (Package('tree'), Package('diffutils')),
                    r"rpm -q --whatprovides tree diffutils \|\| dnf install -y  tree diffutils",
                    'Complete!',
                )

            else:
                yield (
                    container,
                    package_manager_class,
                    (Package('tree'), Package('nano')),
                    r"rpm -q --whatprovides tree nano \|\| dnf install -y  tree nano",
                    'Complete!',
                )

        elif package_manager_class is tmt.package_managers.dnf.Dnf5:
            yield (
                container,
                package_manager_class,
                (Package('tree'), Package('nano')),
                r"rpm -q --whatprovides tree nano \|\| dnf5 install -y  tree nano",
                None,
            )

        elif package_manager_class is tmt.package_managers.apt.Apt:
            yield (
                container,
                package_manager_class,
                (Package('tree'), Package('nano')),
                r"export DEBIAN_FRONTEND=noninteractive;\s+installable_packages=\"tree nano\";\s+dpkg-query --show \$installable_packages \\\s+\|\| apt install -y  \$installable_packages",  # noqa: E501
                'Setting up tree',
            )

        elif package_manager_class is tmt.package_managers.rpm_ostree.RpmOstree:
            yield (
                container,
                package_manager_class,
                (Package('tree'), Package('nano')),
                r"rpm -q --whatprovides tree nano \|\| rpm-ostree install --apply-live --idempotent --allow-inactive --assumeyes  tree nano",  # noqa: E501
                'Installing: tree',
            )

        elif package_manager_class is tmt.package_managers.apk.Apk:
            yield (
                container,
                package_manager_class,
                (Package('tree'), Package('diffutils')),
                r"apk info -e tree diffutils \|\| apk add tree diffutils",
                'Installing tree',
            )

        else:
            pytest.fail(f"Unhandled package manager class '{package_manager_class}'.")


@pytest.mark.containers
@pytest.mark.parametrize(
    (
        'container_per_test',
        'package_manager_class',
        'packages',
        'expected_command',
        'expected_output',
    ),
    list(_parametrize_test_install_multiple()),
    indirect=["container_per_test"],
    ids=CONTAINER_MATRIX_IDS,
)
def test_install_multiple(
    container_per_test: ContainerData,
    guest_per_test: GuestContainer,
    package_manager_class: PackageManagerClass,
    packages: tuple[Package, Package],
    expected_command: str,
    expected_output: Optional[str],
    root_logger: tmt.log.Logger,
    caplog: _pytest.logging.LogCaptureFixture,
) -> None:
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
