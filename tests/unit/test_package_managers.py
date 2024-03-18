from collections.abc import Iterator
from inspect import isclass
from typing import Optional

import _pytest.logging
import pytest
from pytest_container import Container
from pytest_container.container import ContainerData

import tmt.log
import tmt.package_managers
import tmt.package_managers.apt
import tmt.package_managers.dnf
import tmt.package_managers.rpm_ostree
import tmt.plugins
import tmt.steps.provision.podman
import tmt.utils
from tmt.package_managers import (
    FileSystemPath,
    Installable,
    Options,
    Package,
    PackageManager,
    PackageManagerClass,
    )
from tmt.steps.provision.podman import GuestContainer, PodmanGuestData
from tmt.utils import ShellScript

from . import MATCH, assert_log

# We will need a logger...
logger = tmt.Logger.create()
logger.add_console_handler()

# Explore available plugins
tmt.plugins.explore(logger)


CONTAINER_FEDORA_RAWHIDE = Container(url='registry.fedoraproject.org/fedora:rawhide')
CONTAINER_FEDORA_39 = Container(url='registry.fedoraproject.org/fedora:39')
CONTAINER_CENTOS_STREAM_8 = Container(url='quay.io/centos/centos:stream8')
CONTAINER_CENTOS_7 = Container(url='quay.io/centos/centos:7')
CONTAINER_UBUNTU_2204 = Container(url='docker.io/library/ubuntu:22.04')
CONTAINER_FEDORA_COREOS = Container(url='quay.io/fedora/fedora-coreos:stable')

PACKAGE_MANAGER_DNF5 = tmt.package_managers._PACKAGE_MANAGER_PLUGIN_REGISTRY.get_plugin('dnf5')
PACKAGE_MANAGER_DNF = tmt.package_managers._PACKAGE_MANAGER_PLUGIN_REGISTRY.get_plugin('dnf')
PACKAGE_MANAGER_YUM = tmt.package_managers._PACKAGE_MANAGER_PLUGIN_REGISTRY.get_plugin('yum')
PACKAGE_MANAGER_APT = tmt.package_managers._PACKAGE_MANAGER_PLUGIN_REGISTRY.get_plugin('apt')
PACKAGE_MANAGER_RPMOSTREE = tmt.package_managers._PACKAGE_MANAGER_PLUGIN_REGISTRY \
    .get_plugin('rpm-ostree')


CONTAINER_BASE_MATRIX = [
    # Fedora
    (CONTAINER_FEDORA_RAWHIDE, PACKAGE_MANAGER_DNF5),
    (CONTAINER_FEDORA_RAWHIDE, PACKAGE_MANAGER_DNF),
    (CONTAINER_FEDORA_RAWHIDE, PACKAGE_MANAGER_YUM),

    (CONTAINER_FEDORA_39, PACKAGE_MANAGER_DNF5),
    (CONTAINER_FEDORA_39, PACKAGE_MANAGER_DNF),
    (CONTAINER_FEDORA_39, PACKAGE_MANAGER_YUM),

    # CentOS Stream
    (CONTAINER_CENTOS_STREAM_8, PACKAGE_MANAGER_DNF),
    (CONTAINER_CENTOS_STREAM_8, PACKAGE_MANAGER_YUM),

    # CentOS
    (CONTAINER_CENTOS_7, PACKAGE_MANAGER_YUM),

    # Ubuntu
    (CONTAINER_UBUNTU_2204, PACKAGE_MANAGER_APT),

    # Fedora CoreOS
    (CONTAINER_FEDORA_COREOS, PACKAGE_MANAGER_RPMOSTREE),
    ]

CONTAINER_MATRIX_IDS = [
    f'{container.url} / {package_manager_class.__name__.lower()}'
    for container, package_manager_class in CONTAINER_BASE_MATRIX
    ]


@pytest.fixture(name='guest')
def fixture_guest(container: ContainerData, root_logger: tmt.log.Logger) -> GuestContainer:
    guest_data = PodmanGuestData(
        image=container.image_url_or_id,
        container=container.container_id
        )

    guest = GuestContainer(
        logger=root_logger,
        data=guest_data,
        name='dummy-container')

    guest.start()

    return guest


@pytest.fixture(name='guest_per_test')
def fixture_guest_per_test(
        container_per_test: ContainerData,
        root_logger: tmt.log.Logger) -> GuestContainer:
    guest_data = PodmanGuestData(
        image=container_per_test.image_url_or_id,
        container=container_per_test.container_id
        )

    guest = GuestContainer(
        logger=root_logger,
        data=guest_data,
        name='dummy-container')

    guest.start()

    return guest


def create_package_manager(
        container: ContainerData,
        guest: GuestContainer,
        package_manager_class: PackageManagerClass,
        logger: tmt.log.Logger) -> PackageManager:
    guest_data = tmt.steps.provision.podman.PodmanGuestData(
        image=container.image_url_or_id,
        container=container.container_id
        )

    guest = tmt.steps.provision.podman.GuestContainer(
        logger=logger,
        data=guest_data,
        name='dummy-container')
    guest.start()

    if package_manager_class is tmt.package_managers.dnf.Dnf5:
        guest.execute(ShellScript('dnf install --nogpgcheck -y dnf5'))

    elif package_manager_class is tmt.package_managers.apt.Apt:
        guest.execute(ShellScript('apt update'))

    return package_manager_class(guest=guest, logger=logger)


def _parametrize_test_install() -> \
        Iterator[tuple[Container, PackageManagerClass, str, Optional[str], Optional[str]]]:

    for container, package_manager_class in CONTAINER_BASE_MATRIX:
        if package_manager_class is tmt.package_managers.dnf.Yum:
            yield container, \
                package_manager_class, \
                r"rpm -q --whatprovides tree \|\| yum install -y  tree && rpm -q --whatprovides tree", \
                'Installed:\n  tree', \
                None  # noqa: E501

        elif package_manager_class is tmt.package_managers.dnf.Dnf:
            yield container, \
                package_manager_class, \
                r"rpm -q --whatprovides tree \|\| dnf install -y  tree", \
                'Installed:\n  tree', \
                None

        elif package_manager_class is tmt.package_managers.dnf.Dnf5:
            yield container, \
                package_manager_class, \
                r"rpm -q --whatprovides tree \|\| dnf5 install -y  tree", \
                None, \
                None

        elif package_manager_class is tmt.package_managers.apt.Apt:
            yield container, \
                package_manager_class, \
                r"export DEBIAN_FRONTEND=noninteractive; dpkg-query --show tree \|\| apt install -y  tree", \
                'Setting up tree', \
                None  # noqa: E501

        elif package_manager_class is tmt.package_managers.rpm_ostree.RpmOstree:
            yield container, \
                package_manager_class, \
                r"rpm -q --whatprovides tree \|\| rpm-ostree install --apply-live --idempotent --allow-inactive  tree", \
                'Installing: tree', \
                None  # noqa: E501

        else:
            pytest.fail(f"Unhandled package manager class '{package_manager_class}'.")


@pytest.mark.containers()
@pytest.mark.parametrize(('container_per_test',
                          'package_manager_class',
                          'expected_command',
                          'expected_stdout',
                          'expected_stderr'),
                         list(_parametrize_test_install()),
                         indirect=["container_per_test"],
                         ids=CONTAINER_MATRIX_IDS)
def test_install(
        container_per_test: ContainerData,
        guest_per_test: GuestContainer,
        package_manager_class: PackageManagerClass,
        expected_command: str,
        expected_stdout: Optional[str],
        expected_stderr: Optional[str],
        root_logger: tmt.log.Logger,
        caplog: _pytest.logging.LogCaptureFixture) -> None:
    package_manager = create_package_manager(
        container_per_test,
        guest_per_test,
        package_manager_class,
        root_logger)

    output = package_manager.install(Package('tree'))

    assert_log(caplog, message=MATCH(
        rf"Run command: podman exec .+? /bin/bash -c '{expected_command}'"))

    if expected_stdout:
        assert output.stdout is not None
        assert expected_stdout in output.stdout

    if expected_stderr:
        assert output.stderr is not None
        assert expected_stderr in output.stderr


def _parametrize_test_install_nonexistent() -> \
        Iterator[tuple[Container, PackageManagerClass, str, Optional[str], Optional[str]]]:

    for container, package_manager_class in CONTAINER_BASE_MATRIX:
        if package_manager_class is tmt.package_managers.dnf.Dnf5:
            yield container, \
                package_manager_class, \
                r"rpm -q --whatprovides tree-but-spelled-wrong \|\| dnf5 install -y  tree-but-spelled-wrong", \
                None, \
                'No match for argument: tree-but-spelled-wrong'  # noqa: E501

        elif package_manager_class is tmt.package_managers.dnf.Dnf:
            yield container, \
                package_manager_class, \
                r"rpm -q --whatprovides tree-but-spelled-wrong \|\| dnf install -y  tree-but-spelled-wrong", \
                None, \
                'Error: Unable to find a match: tree-but-spelled-wrong'  # noqa: E501

        elif package_manager_class is tmt.package_managers.dnf.Yum:
            if 'fedora' in container.url:
                yield container, \
                    package_manager_class, \
                    r"rpm -q --whatprovides tree-but-spelled-wrong \|\| yum install -y  tree-but-spelled-wrong && rpm -q --whatprovides tree-but-spelled-wrong", \
                    None, \
                    'Error: Unable to find a match: tree-but-spelled-wrong'  # noqa: E501

            elif 'centos' in container.url and 'centos:7' not in container.url:
                yield container, \
                    package_manager_class, \
                    r"rpm -q --whatprovides tree-but-spelled-wrong \|\| yum install -y  tree-but-spelled-wrong && rpm -q --whatprovides tree-but-spelled-wrong", \
                    'No match for argument: tree-but-spelled-wrong', \
                    'Error: Unable to find a match: tree-but-spelled-wrong'  # noqa: E501

            else:
                yield container, \
                    package_manager_class, \
                    r"rpm -q --whatprovides tree-but-spelled-wrong \|\| yum install -y  tree-but-spelled-wrong && rpm -q --whatprovides tree-but-spelled-wrong", \
                    'No package tree-but-spelled-wrong available.', \
                    'Error: Nothing to do'  # noqa: E501

        elif package_manager_class is tmt.package_managers.apt.Apt:
            yield container, \
                package_manager_class, \
                r"export DEBIAN_FRONTEND=noninteractive; dpkg-query --show tree-but-spelled-wrong \|\| apt install -y  tree-but-spelled-wrong", \
                None, \
                'E: Unable to locate package tree-but-spelled-wrong'  # noqa: E501

        elif package_manager_class is tmt.package_managers.rpm_ostree.RpmOstree:
            yield container, \
                package_manager_class, \
                r"rpm -q --whatprovides tree-but-spelled-wrong \|\| rpm-ostree install --apply-live --idempotent --allow-inactive  tree-but-spelled-wrong", \
                'no package provides tree-but-spelled-wrong', \
                'error: Packages not found: tree-but-spelled-wrong'  # noqa: E501

        else:
            pytest.fail(f"Unhandled package manager class '{package_manager_class}'.")


@pytest.mark.containers()
@pytest.mark.parametrize(('container',
                          'package_manager_class',
                          'expected_command',
                          'expected_stdout',
                          'expected_stderr'),
                         list(_parametrize_test_install_nonexistent()),
                         indirect=["container"],
                         ids=CONTAINER_MATRIX_IDS)
def test_install_nonexistent(
        container: ContainerData,
        guest: GuestContainer,
        package_manager_class: PackageManagerClass,
        expected_command: str,
        expected_stdout: Optional[str],
        expected_stderr: Optional[str],
        root_logger: tmt.log.Logger,
        caplog: _pytest.logging.LogCaptureFixture) -> None:
    package_manager = create_package_manager(container, guest, package_manager_class, root_logger)

    with pytest.raises(tmt.utils.RunError) as excinfo:
        package_manager.install(Package('tree-but-spelled-wrong'))

    assert_log(caplog, message=MATCH(
        rf"Run command: podman exec .+? /bin/bash -c '{expected_command}'"))

    assert excinfo.type is tmt.utils.RunError
    assert excinfo.value.returncode != 0

    if expected_stdout:
        assert excinfo.value.stdout is not None
        assert expected_stdout in excinfo.value.stdout

    if expected_stderr:
        assert excinfo.value.stderr is not None
        assert expected_stderr in excinfo.value.stderr


def _parametrize_test_install_nonexistent_skip() -> \
        Iterator[tuple[Container, PackageManagerClass, str, Optional[str], Optional[str]]]:

    for container, package_manager_class in CONTAINER_BASE_MATRIX:
        if package_manager_class is tmt.package_managers.dnf.Dnf5:
            yield container, \
                package_manager_class, \
                r"rpm -q --whatprovides tree-but-spelled-wrong \|\| dnf5 install -y --skip-unavailable tree-but-spelled-wrong", \
                None, \
                None  # noqa: E501

        elif package_manager_class is tmt.package_managers.dnf.Dnf:
            yield container, \
                package_manager_class, \
                r"rpm -q --whatprovides tree-but-spelled-wrong \|\| dnf install -y --skip-broken tree-but-spelled-wrong", \
                'No match for argument: tree-but-spelled-wrong', \
                None  # noqa: E501

        elif package_manager_class is tmt.package_managers.dnf.Yum:
            if 'fedora' in container.url:  # noqa: SIM114
                yield container, \
                    package_manager_class, \
                    r"rpm -q --whatprovides tree-but-spelled-wrong \|\| yum install -y --skip-broken tree-but-spelled-wrong \|\| /bin/true", \
                    'No match for argument: tree-but-spelled-wrong', \
                    None  # noqa: E501

            elif 'centos' in container.url and 'centos:7' not in container.url:
                yield container, \
                    package_manager_class, \
                    r"rpm -q --whatprovides tree-but-spelled-wrong \|\| yum install -y --skip-broken tree-but-spelled-wrong \|\| /bin/true", \
                    'No match for argument: tree-but-spelled-wrong', \
                    None  # noqa: E501

            else:
                yield container, \
                    package_manager_class, \
                    r"rpm -q --whatprovides tree-but-spelled-wrong \|\| yum install -y --skip-broken tree-but-spelled-wrong \|\| /bin/true", \
                    'No package tree-but-spelled-wrong available.', \
                    'Error: Nothing to do'  # noqa: E501

        elif package_manager_class is tmt.package_managers.apt.Apt:
            yield container, \
                package_manager_class, \
                r"export DEBIAN_FRONTEND=noninteractive; dpkg-query --show tree-but-spelled-wrong \|\| apt install -y --ignore-missing tree-but-spelled-wrong \|\| /bin/true", \
                None, \
                'E: Unable to locate package tree-but-spelled-wrong'  # noqa: E501

        elif package_manager_class is tmt.package_managers.rpm_ostree.RpmOstree:
            yield container, \
                package_manager_class, \
                r"rpm -q --whatprovides tree-but-spelled-wrong \|\| rpm-ostree install --apply-live --idempotent --allow-inactive  tree-but-spelled-wrong \|\| /bin/true", \
                'no package provides tree-but-spelled-wrong', \
                'error: Packages not found: tree-but-spelled-wrong'  # noqa: E501

        else:
            pytest.fail(f"Unhandled package manager class '{package_manager_class}'.")


@pytest.mark.containers()
@pytest.mark.parametrize(('container',
                          'package_manager_class',
                          'expected_command',
                          'expected_stdout',
                          'expected_stderr'),
                         list(_parametrize_test_install_nonexistent_skip()),
                         indirect=["container"],
                         ids=CONTAINER_MATRIX_IDS)
def test_install_nonexistent_skip(
        container: ContainerData,
        guest: GuestContainer,
        package_manager_class: PackageManagerClass,
        expected_command: str,
        expected_stdout: Optional[str],
        expected_stderr: Optional[str],
        root_logger: tmt.log.Logger,
        caplog: _pytest.logging.LogCaptureFixture) -> None:
    package_manager = create_package_manager(container, guest, package_manager_class, root_logger)

    output = package_manager.install(
        Package('tree-but-spelled-wrong'),
        options=Options(skip_missing=True)
        )

    assert_log(caplog, message=MATCH(
        rf"Run command: podman exec .+? /bin/bash -c '{expected_command}'"))

    if expected_stdout:
        assert output.stdout is not None
        assert expected_stdout in output.stdout

    if expected_stderr:
        assert output.stderr is not None
        assert expected_stderr in output.stderr


def _parametrize_test_install_dont_check_first() -> \
        Iterator[tuple[Container, PackageManagerClass, str, Optional[str], Optional[str]]]:

    for container, package_manager_class in CONTAINER_BASE_MATRIX:
        if package_manager_class is tmt.package_managers.dnf.Dnf5:
            yield container, \
                package_manager_class, \
                r"dnf5 install -y  tree", \
                None, \
                None

        elif package_manager_class is tmt.package_managers.dnf.Dnf:
            yield container, \
                package_manager_class, \
                r"dnf install -y  tree", \
                'Installed:\n  tree', \
                None

        elif package_manager_class is tmt.package_managers.dnf.Yum:
            yield container, \
                package_manager_class, \
                r"yum install -y  tree && rpm -q --whatprovides tree", \
                'Installed:\n  tree', \
                None

        elif package_manager_class is tmt.package_managers.apt.Apt:
            yield container, \
                package_manager_class, \
                r"export DEBIAN_FRONTEND=noninteractive; apt install -y  tree", \
                'Setting up tree', \
                None

        elif package_manager_class is tmt.package_managers.rpm_ostree.RpmOstree:
            yield container, \
                package_manager_class, \
                r"rpm-ostree install --apply-live --idempotent --allow-inactive  tree", \
                'Installing: tree', \
                None

        else:
            pytest.fail(f"Unhandled package manager class '{package_manager_class}'.")


@pytest.mark.containers()
@pytest.mark.parametrize(('container_per_test',
                          'package_manager_class',
                          'expected_command',
                          'expected_stdout',
                          'expected_stderr'),
                         list(_parametrize_test_install_dont_check_first()),
                         indirect=["container_per_test"],
                         ids=CONTAINER_MATRIX_IDS)
def test_install_dont_check_first(
        container_per_test: ContainerData,
        guest_per_test: GuestContainer,
        package_manager_class: PackageManagerClass,
        expected_command: str,
        expected_stdout: Optional[str],
        expected_stderr: Optional[str],
        root_logger: tmt.log.Logger,
        caplog: _pytest.logging.LogCaptureFixture) -> None:
    package_manager = create_package_manager(
        container_per_test,
        guest_per_test,
        package_manager_class,
        root_logger)

    output = package_manager.install(
        Package('tree'),
        options=Options(check_first=False)
        )

    assert_log(caplog, message=MATCH(
        rf"Run command: podman exec .+? /bin/bash -c '{expected_command}'"))

    if expected_stdout:
        assert output.stdout is not None
        assert expected_stdout in output.stdout

    if expected_stderr:
        assert output.stderr is not None
        assert expected_stderr in output.stderr


def _parametrize_test_reinstall() -> Iterator[tuple[
        Container, PackageManagerClass, Optional[str], Optional[str], Optional[str]]]:

    for container, package_manager_class in CONTAINER_BASE_MATRIX:
        if package_manager_class is tmt.package_managers.dnf.Yum:
            if 'centos:7' in container.url:
                yield container, \
                    package_manager_class, \
                    True, \
                    r"rpm -q --whatprovides tar && yum reinstall -y  tar && rpm -q --whatprovides tar", \
                    'Reinstalling:\n tar', \
                    None  # noqa: E501

            else:
                yield container, \
                    package_manager_class, \
                    True, \
                    r"rpm -q --whatprovides tar && yum reinstall -y  tar && rpm -q --whatprovides tar", \
                    'Reinstalled:\n  tar', \
                    None  # noqa: E501

        elif package_manager_class is tmt.package_managers.dnf.Dnf:
            yield container, \
                package_manager_class, \
                True, \
                r"rpm -q --whatprovides tar && dnf reinstall -y  tar", \
                'Reinstalled:\n  tar', \
                None

        elif package_manager_class is tmt.package_managers.dnf.Dnf5:
            yield container, \
                package_manager_class, \
                True, \
                r"rpm -q --whatprovides tar && dnf5 reinstall -y  tar", \
                'Reinstalling tar', \
                None

        elif package_manager_class is tmt.package_managers.apt.Apt:
            yield container, \
                package_manager_class, \
                True, \
                r"export DEBIAN_FRONTEND=noninteractive; dpkg-query --show tar && apt reinstall -y  tar", \
                'Setting up tar', \
                None  # noqa: E501

        elif package_manager_class is tmt.package_managers.rpm_ostree.RpmOstree:
            yield container, \
                package_manager_class, \
                False, \
                None, \
                None, \
                None

        else:
            pytest.fail(f"Unhandled package manager class '{package_manager_class}'.")


@pytest.mark.containers()
@pytest.mark.parametrize(('container_per_test',
                          'package_manager_class',
                          'supported',
                          'expected_command',
                          'expected_stdout',
                          'expected_stderr'),
                         list(_parametrize_test_reinstall()),
                         indirect=["container_per_test"],
                         ids=CONTAINER_MATRIX_IDS)
def test_reinstall(
        container_per_test: ContainerData,
        guest_per_test: GuestContainer,
        package_manager_class: PackageManagerClass,
        supported: bool,
        expected_command: Optional[str],
        expected_stdout: Optional[str],
        expected_stderr: Optional[str],
        root_logger: tmt.log.Logger,
        caplog: _pytest.logging.LogCaptureFixture) -> None:
    package_manager = create_package_manager(
        container_per_test,
        guest_per_test,
        package_manager_class,
        root_logger)

    if supported:
        assert expected_command is not None

        output = package_manager.reinstall(Package('tar'))

        assert_log(caplog, message=MATCH(
            rf"Run command: podman exec .+? /bin/bash -c '{expected_command}'"))

    else:
        with pytest.raises(tmt.utils.GeneralError) as excinfo:
            package_manager.reinstall(Package('tar'))

        assert excinfo.value.message \
            == "rpm-ostree does not support reinstall operation."

    if expected_stdout:
        assert output.stdout is not None
        assert expected_stdout in output.stdout

    if expected_stderr:
        assert output.stderr is not None
        assert expected_stderr in output.stderr


def _generate_test_reinstall_nonexistent_matrix() -> Iterator[tuple[
        Container, PackageManagerClass, Optional[str], Optional[str], Optional[str]]]:

    for container, package_manager_class in CONTAINER_BASE_MATRIX:
        if package_manager_class is tmt.package_managers.dnf.Dnf5:
            yield container, \
                package_manager_class, \
                True, \
                r"rpm -q --whatprovides tree-but-spelled-wrong && dnf5 reinstall -y  tree-but-spelled-wrong", \
                'no package provides tree-but-spelled-wrong', \
                None  # noqa: E501

        elif package_manager_class is tmt.package_managers.dnf.Dnf:
            yield container, \
                package_manager_class, \
                True, \
                r"rpm -q --whatprovides tree-but-spelled-wrong && dnf reinstall -y  tree-but-spelled-wrong", \
                'no package provides tree-but-spelled-wrong', \
                None  # noqa: E501

        elif package_manager_class is tmt.package_managers.dnf.Yum:
            if 'fedora' in container.url:  # noqa: SIM114
                yield container, \
                    package_manager_class, \
                    True, \
                    r"rpm -q --whatprovides tree-but-spelled-wrong && yum reinstall -y  tree-but-spelled-wrong && rpm -q --whatprovides tree-but-spelled-wrong", \
                    'no package provides tree-but-spelled-wrong', \
                    None  # noqa: E501

            elif 'centos' in container.url and 'centos:7' not in container.url:
                yield container, \
                    package_manager_class, \
                    True, \
                    r"rpm -q --whatprovides tree-but-spelled-wrong && yum reinstall -y  tree-but-spelled-wrong && rpm -q --whatprovides tree-but-spelled-wrong", \
                    'no package provides tree-but-spelled-wrong', \
                    None  # noqa: E501

            else:
                yield container, \
                    package_manager_class, \
                    True, \
                    r"rpm -q --whatprovides tree-but-spelled-wrong && yum reinstall -y  tree-but-spelled-wrong && rpm -q --whatprovides tree-but-spelled-wrong", \
                    'no package provides tree-but-spelled-wrong', \
                None  # noqa: E501

        elif package_manager_class is tmt.package_managers.apt.Apt:
            yield container, \
                package_manager_class, \
                True, \
                r"export DEBIAN_FRONTEND=noninteractive; dpkg-query --show tree-but-spelled-wrong && apt reinstall -y  tree-but-spelled-wrong", \
                None, \
                'dpkg-query: no packages found matching tree-but-spelled-wrong'  # noqa: E501

        elif package_manager_class is tmt.package_managers.rpm_ostree.RpmOstree:
            yield container, \
                package_manager_class, \
                False, \
                None, \
                None, \
                None

        else:
            pytest.fail(f"Unhandled package manager class '{package_manager_class}'.")


@pytest.mark.containers()
@pytest.mark.parametrize(('container',
                          'package_manager_class',
                          'supported',
                          'expected_command',
                          'expected_stdout',
                          'expected_stderr'),
                         list(_generate_test_reinstall_nonexistent_matrix()),
                         indirect=["container"],
                         ids=CONTAINER_MATRIX_IDS)
def test_reinstall_nonexistent(
        container: ContainerData,
        guest: GuestContainer,
        package_manager_class: PackageManagerClass,
        supported: bool,
        expected_command: str,
        expected_stdout: Optional[str],
        expected_stderr: Optional[str],
        root_logger: tmt.log.Logger,
        caplog: _pytest.logging.LogCaptureFixture) -> None:
    package_manager = create_package_manager(container, guest, package_manager_class, root_logger)

    if supported:
        assert expected_command is not None

        with pytest.raises(tmt.utils.RunError) as excinfo:
            package_manager.reinstall(Package('tree-but-spelled-wrong'))

        assert_log(caplog, message=MATCH(
            rf"Run command: podman exec .+? /bin/bash -c '{expected_command}'"))

        assert excinfo.type is tmt.utils.RunError
        assert excinfo.value.returncode != 0

    else:
        with pytest.raises(tmt.utils.GeneralError) as excinfo:
            package_manager.reinstall(Package('tree-but-spelled-wrong'))

        assert excinfo.value.message \
            == "rpm-ostree does not support reinstall operation."

    if expected_stdout:
        assert excinfo.value.stdout is not None
        assert expected_stdout in excinfo.value.stdout

    if expected_stderr:
        assert excinfo.value.stderr is not None
        assert expected_stderr in excinfo.value.stderr


def _generate_test_check_presence() -> Iterator[
        tuple[Container, PackageManagerClass, Installable, str, Optional[str], Optional[str]]]:

    for container, package_manager_class in CONTAINER_BASE_MATRIX:
        if package_manager_class is tmt.package_managers.dnf.Dnf5:
            yield container, \
                package_manager_class, \
                Package('coreutils'), \
                True, \
                r"rpm -q --whatprovides coreutils", \
                r'\s+out:\s+coreutils-', \
                None

            yield container, \
                package_manager_class, \
                Package('tree-but-spelled-wrong'), \
                False, \
                r"rpm -q --whatprovides tree-but-spelled-wrong", \
                r'\s+out:\s+no package provides tree-but-spelled-wrong', \
                None

            yield container, \
                package_manager_class, \
                FileSystemPath('/usr/bin/arch'), \
                True, \
                r"rpm -q --whatprovides /usr/bin/arch", \
                r'\s+out:\s+coreutils-', \
                None

        elif package_manager_class is tmt.package_managers.dnf.Dnf:
            if 'centos:stream8' in container.url:
                yield container, \
                    package_manager_class, \
                    Package('util-linux'), \
                    True, \
                    r"rpm -q --whatprovides util-linux", \
                    r'\s+out:\s+util-linux-', \
                    None

                yield container, \
                    package_manager_class, \
                    Package('tree-but-spelled-wrong'), \
                    False, \
                    r"rpm -q --whatprovides tree-but-spelled-wrong", \
                    r'\s+out:\s+no package provides tree-but-spelled-wrong', \
                    None

                yield container, \
                    package_manager_class, \
                    FileSystemPath('/usr/bin/flock'), \
                    True, \
                    r"rpm -q --whatprovides /usr/bin/flock", \
                    r'\s+out:\s+util-linux-', \
                    None

            elif 'fedora:rawhide' in container.url:
                yield container, \
                    package_manager_class, \
                    Package('coreutils'), \
                    True, \
                    r"rpm -q --whatprovides coreutils", \
                    r'\s+out:\s+coreutils-', \
                    None

                yield container, \
                    package_manager_class, \
                    Package('tree-but-spelled-wrong'), \
                    False, \
                    r"rpm -q --whatprovides tree-but-spelled-wrong", \
                    r'\s+out:\s+no package provides tree-but-spelled-wrong', \
                    None

                yield container, \
                    package_manager_class, \
                    FileSystemPath('/usr/bin/arch'), \
                    True, \
                    r"rpm -q --whatprovides /usr/bin/arch", \
                    r'\s+out:\s+coreutils-', \
                    None

            else:
                yield container, \
                    package_manager_class, \
                    Package('util-linux-core'), \
                    True, \
                    r"rpm -q --whatprovides util-linux-core", \
                    r'\s+out:\s+util-linux-core-', \
                    None

                yield container, \
                    package_manager_class, \
                    Package('tree-but-spelled-wrong'), \
                    False, \
                    r"rpm -q --whatprovides tree-but-spelled-wrong", \
                    r'\s+out:\s+no package provides tree-but-spelled-wrong', \
                    None

                yield container, \
                    package_manager_class, \
                    FileSystemPath('/usr/bin/flock'), \
                    True, \
                    r"rpm -q --whatprovides /usr/bin/flock", \
                    r'\s+out:\s+util-linux-core-', \
                    None

        elif package_manager_class is tmt.package_managers.dnf.Yum:
            if 'centos:stream8' in container.url or 'centos:7' in container.url:
                yield container, \
                    package_manager_class, \
                    Package('util-linux'), \
                    True, \
                    r"rpm -q --whatprovides util-linux", \
                    r'\s+out:\s+util-linux-', \
                    None

                yield container, \
                    package_manager_class, \
                    Package('tree-but-spelled-wrong'), \
                    False, \
                    r"rpm -q --whatprovides tree-but-spelled-wrong", \
                    r'\s+out:\s+no package provides tree-but-spelled-wrong', \
                    None

                yield container, \
                    package_manager_class, \
                    FileSystemPath('/usr/bin/flock'), \
                    True, \
                    r"rpm -q --whatprovides /usr/bin/flock", \
                    r'\s+out:\s+util-linux-', \
                    None

            elif 'fedora:rawhide' in container.url:
                yield container, \
                    package_manager_class, \
                    Package('coreutils'), \
                    True, \
                    r"rpm -q --whatprovides coreutils", \
                    r'\s+out:\s+coreutils-', \
                    None

                yield container, \
                    package_manager_class, \
                    Package('tree-but-spelled-wrong'), \
                    False, \
                    r"rpm -q --whatprovides tree-but-spelled-wrong", \
                    r'\s+out:\s+no package provides tree-but-spelled-wrong', \
                    None

                yield container, \
                    package_manager_class, \
                    FileSystemPath('/usr/bin/arch'), \
                    True, \
                    r"rpm -q --whatprovides /usr/bin/arch", \
                    r'\s+out:\s+coreutils-', \
                    None

            else:
                yield container, \
                    package_manager_class, \
                    Package('util-linux-core'), \
                    True, \
                    r"rpm -q --whatprovides util-linux-core", \
                    r'\s+out:\s+util-linux-core-', \
                    None

                yield container, \
                    package_manager_class, \
                    Package('tree-but-spelled-wrong'), \
                    False, \
                    r"rpm -q --whatprovides tree-but-spelled-wrong", \
                    r'\s+out:\s+no package provides tree-but-spelled-wrong', \
                    None

                yield container, \
                    package_manager_class, \
                    FileSystemPath('/usr/bin/flock'), \
                    True, \
                    r"rpm -q --whatprovides /usr/bin/flock", \
                    r'\s+out:\s+util-linux-core-', \
                    None

        elif package_manager_class is tmt.package_managers.apt.Apt:
            yield container, \
                package_manager_class, \
                Package('util-linux'), \
                True, \
                r"dpkg-query --show util-linux", \
                r'\s+out:\s+util-linux', \
                None

            yield container, \
                package_manager_class, \
                Package('tree-but-spelled-wrong'), \
                False, \
                r"dpkg-query --show tree-but-spelled-wrong", \
                None, \
                r'\s+err:\s+dpkg-query: no packages found matching tree-but-spelled-wrong'

            yield container, \
                package_manager_class, \
                FileSystemPath('/usr/bin/flock'), \
                True, \
                r"dpkg-query --show util-linux", \
                r'\s+out:\s+util-linux', \
                None

        elif package_manager_class is tmt.package_managers.rpm_ostree.RpmOstree:
            yield container, \
                package_manager_class, \
                Package('util-linux'), \
                True, \
                r"rpm -q --whatprovides util-linux", \
                r'\s+out:\s+util-linux', \
                None

            yield container, \
                package_manager_class, \
                Package('tree-but-spelled-wrong'), \
                False, \
                r"rpm -q --whatprovides tree-but-spelled-wrong", \
                r'\s+out:\s+no package provides tree-but-spelled-wrong', \
                None

            yield container, \
                package_manager_class, \
                FileSystemPath('/usr/bin/flock'), \
                True, \
                r"rpm -qf /usr/bin/flock", \
                r'\s+out:\s+util-linux-core', \
                None

        else:
            pytest.fail(f"Unhandled package manager class '{package_manager_class}'.")


def _generate_test_check_presence_ids(value) -> str:
    if isinstance(value, Container):
        return value.url

    if isclass(value) and issubclass(value, tmt.package_managers.PackageManager):
        return value.__name__.lower()

    if isinstance(value, (Package, FileSystemPath)):
        return str(value)

    return ''


@pytest.mark.containers()
@pytest.mark.parametrize(('container',
                          'package_manager_class',
                          'installable',
                          'expected_result',
                          'expected_command',
                          'expected_stdout',
                          'expected_stderr'),
                         list(_generate_test_check_presence()),
                         indirect=["container"],
                         ids=_generate_test_check_presence_ids)
def test_check_presence(
        container: ContainerData,
        guest: GuestContainer,
        package_manager_class: PackageManagerClass,
        installable: Installable,
        expected_result: bool,
        expected_command: str,
        expected_stdout: Optional[str],
        expected_stderr: Optional[str],
        root_logger: tmt.log.Logger,
        caplog: _pytest.logging.LogCaptureFixture) -> None:
    package_manager = create_package_manager(container, guest, package_manager_class, root_logger)

    assert package_manager.check_presence(installable) == {installable: expected_result}

    assert_log(caplog, message=MATCH(
        rf"Run command: podman exec .+? /bin/bash -c '{expected_command}'"))

    if expected_stdout:
        assert_log(caplog, remove_colors=True, message=MATCH(expected_stdout))

    if expected_stderr:
        assert_log(caplog, remove_colors=True, message=MATCH(expected_stderr))
