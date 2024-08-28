from collections.abc import Iterator
from inspect import isclass
from typing import Optional

import _pytest.logging
import pytest
from pytest_container import Container
from pytest_container.container import ContainerData

import tmt.log
import tmt.package_managers
import tmt.package_managers.apk
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
    PackagePath,
    )
from tmt.steps.provision.podman import GuestContainer, PodmanGuestData
from tmt.utils import ShellScript

from . import MATCH, assert_log

# We will need a logger...
logger = tmt.Logger.create()
logger.add_console_handler()

# Explore available plugins
tmt.plugins.explore(logger)

# Local images created via `make images-tests`, reference to local registry
CONTAINER_FEDORA_RAWHIDE = Container(
    url='containers-storage:localhost/tmt/tests/container/fedora/rawhide/upstream:latest')
CONTAINER_FEDORA_41 = Container(
    url='containers-storage:localhost/tmt/tests/container/fedora/41/upstream:latest')
CONTAINER_FEDORA_40 = Container(
    url='containers-storage:localhost/tmt/tests/container/fedora/40/upstream:latest')
CONTAINER_FEDORA_39 = Container(
    url='containers-storage:localhost/tmt/tests/container/fedora/39/upstream:latest')
CONTAINER_CENTOS_STREAM_9 = Container(
    url='containers-storage:localhost/tmt/tests/container/centos/stream9/upstream:latest')
CONTAINER_CENTOS_7 = Container(
    url='containers-storage:localhost/tmt/tests/container/centos/7/upstream:latest')
CONTAINER_UBI_8 = Container(
    url='containers-storage:localhost/tmt/tests/container/ubi/8/upstream:latest')
CONTAINER_UBUNTU_2204 = Container(
    url='containers-storage:localhost/tmt/tests/container/ubuntu/22.04/upstream:latest')
CONTAINER_FEDORA_COREOS = Container(
    url='containers-storage:localhost/tmt/tests/container/fedora/coreos:stable')
CONTAINER_FEDORA_COREOS_OSTREE = Container(
    url='containers-storage:localhost/tmt/tests/container/fedora/coreos/ostree:stable')
CONTAINER_ALPINE = Container(
    url='containers-storage:localhost/tmt/tests/container/alpine:latest')

PACKAGE_MANAGER_DNF5 = tmt.package_managers._PACKAGE_MANAGER_PLUGIN_REGISTRY.get_plugin('dnf5')
PACKAGE_MANAGER_DNF = tmt.package_managers._PACKAGE_MANAGER_PLUGIN_REGISTRY.get_plugin('dnf')
PACKAGE_MANAGER_YUM = tmt.package_managers._PACKAGE_MANAGER_PLUGIN_REGISTRY.get_plugin('yum')
PACKAGE_MANAGER_APT = tmt.package_managers._PACKAGE_MANAGER_PLUGIN_REGISTRY.get_plugin('apt')
PACKAGE_MANAGER_RPMOSTREE = tmt.package_managers._PACKAGE_MANAGER_PLUGIN_REGISTRY \
    .get_plugin('rpm-ostree')
PACKAGE_MANAGER_APK = tmt.package_managers._PACKAGE_MANAGER_PLUGIN_REGISTRY.get_plugin('apk')


def has_legacy_dnf(container: ContainerData) -> bool:
    """
    Checks whether a container provides older ``dnf`` and ``yum``.

    At some point, Fedora switched to ``dnf5`` completely, and older
    ``dnf`` and ``yum`` commands are now mere symlinks to ``dnf5``.
    """

    if 'fedora' not in container.image_url_or_id \
            and 'centos' not in container.image_url_or_id:
        return False

    return container.image_url_or_id not in (
        CONTAINER_FEDORA_RAWHIDE.url,
        CONTAINER_FEDORA_41.url,
        CONTAINER_FEDORA_COREOS.url,
        CONTAINER_FEDORA_COREOS_OSTREE.url
        )


def has_dnf5_preinstalled(container: ContainerData) -> bool:
    """ Checks whether a container provides ``dnf5`` """

    return container.image_url_or_id in (
        CONTAINER_FEDORA_RAWHIDE.url,
        CONTAINER_FEDORA_41.url,
        CONTAINER_FEDORA_COREOS.url,
        CONTAINER_FEDORA_COREOS_OSTREE.url
        )


# Note: keep the list ordered by the most desired package manager to the
# least desired one. For most of the tests, the order is not important,
# but the list is used to generate the discovery tests as well, and the
# order is used to find out what package manager is expected to be
# discovered.
CONTAINER_BASE_MATRIX = [
    # Fedora
    (CONTAINER_FEDORA_RAWHIDE, PACKAGE_MANAGER_DNF5),

    (CONTAINER_FEDORA_41, PACKAGE_MANAGER_DNF5),

    (CONTAINER_FEDORA_40, PACKAGE_MANAGER_DNF5),
    (CONTAINER_FEDORA_40, PACKAGE_MANAGER_DNF),
    (CONTAINER_FEDORA_40, PACKAGE_MANAGER_YUM),

    (CONTAINER_FEDORA_39, PACKAGE_MANAGER_DNF5),
    (CONTAINER_FEDORA_39, PACKAGE_MANAGER_DNF),
    (CONTAINER_FEDORA_39, PACKAGE_MANAGER_YUM),

    # CentOS Stream
    (CONTAINER_CENTOS_STREAM_9, PACKAGE_MANAGER_DNF),
    (CONTAINER_CENTOS_STREAM_9, PACKAGE_MANAGER_YUM),

    # CentOS
    (CONTAINER_CENTOS_7, PACKAGE_MANAGER_YUM),

    # UBI
    (CONTAINER_UBI_8, PACKAGE_MANAGER_DNF),
    (CONTAINER_UBI_8, PACKAGE_MANAGER_YUM),

    # Ubuntu
    (CONTAINER_UBUNTU_2204, PACKAGE_MANAGER_APT),

    # Fedora CoreOS
    (CONTAINER_FEDORA_COREOS, PACKAGE_MANAGER_DNF5),
    (CONTAINER_FEDORA_COREOS_OSTREE, PACKAGE_MANAGER_RPMOSTREE),

    # Alpine
    (CONTAINER_ALPINE, PACKAGE_MANAGER_APK),
    ]

CONTAINER_MATRIX_IDS = [
    f'{container.url} / {package_manager_class.__name__.lower()}'
    for container, package_manager_class in CONTAINER_BASE_MATRIX
    ]


CONTAINER_DISCOVERY_MATRIX: dict[str, tuple[Container, PackageManagerClass]] = {}

for container, package_manager_class in CONTAINER_BASE_MATRIX:
    if container.url in CONTAINER_DISCOVERY_MATRIX:
        continue

    CONTAINER_DISCOVERY_MATRIX[container.url] = (container, package_manager_class)


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


def is_dnf5_preinstalled(container: ContainerData) -> bool:
    return container.image_url_or_id in (
        CONTAINER_FEDORA_RAWHIDE.url,
        CONTAINER_FEDORA_41.url,
        CONTAINER_FEDORA_COREOS.url,
        CONTAINER_FEDORA_COREOS_OSTREE.url)


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
    guest.show()

    if package_manager_class is tmt.package_managers.dnf.Dnf5:
        # Note that our custom images contain `dnf5` already
        if is_dnf5_preinstalled(container):
            pass

        else:
            guest.execute(ShellScript('dnf install --nogpgcheck -y dnf5'))

    elif package_manager_class is tmt.package_managers.apt.Apt:
        guest.execute(ShellScript('apt update'))

    return package_manager_class(guest=guest, logger=logger)


def _parametrize_test_discovery() -> Iterator[tuple[ContainerData, PackageManagerClass]]:
    yield from CONTAINER_DISCOVERY_MATRIX.values()


@pytest.mark.containers()
@pytest.mark.parametrize(('container',
                          'expected_package_manager'),
                         list(_parametrize_test_discovery()),
                         indirect=["container"],
                         ids=[
                             container.url
                             for container, _
                             in CONTAINER_DISCOVERY_MATRIX.values()
    ])
def test_discovery(
        container: ContainerData,
        guest: GuestContainer,
        expected_package_manager: PackageManagerClass,
        root_logger: tmt.log.Logger,
        caplog: _pytest.logging.LogCaptureFixture) -> None:

    guest.show()

    def _test_discovery(expected: str, expected_discovery: str) -> None:
        caplog.clear()

        guest.facts.sync(guest)

        assert guest.facts.package_manager == expected

        assert_log(caplog, message=MATCH(
            rf"^Discovered package managers: {expected_discovery}$"))

    # Images in which `dnf5`` would be the best possible choice, do not
    # come with `dnf5`` pre-installed. Therefore run the discovery first,
    # but expect to find *dnf* instead of `dnf5`. Then install `dnf5`,
    # re-run the discovery and expect the original outcome.
    if expected_package_manager is tmt.package_managers.dnf.Dnf5:
        guest.info(f'{container.image_url_or_id=}')
        guest.info(f'{has_legacy_dnf(container)=}')
        guest.info(f'{has_dnf5_preinstalled(container)=}')

        if has_legacy_dnf(container):
            _test_discovery(tmt.package_managers.dnf.Dnf.NAME, 'dnf and yum')

            if not has_dnf5_preinstalled(container):
                guest.execute(ShellScript('dnf install --nogpgcheck -y dnf5'))

        if has_legacy_dnf(container):
            _test_discovery(expected_package_manager.NAME, 'dnf5, dnf and yum')

        else:
            _test_discovery(expected_package_manager.NAME, 'dnf5')

    elif expected_package_manager is tmt.package_managers.dnf.Dnf:
        _test_discovery(expected_package_manager.NAME, 'dnf and yum')

    elif expected_package_manager is tmt.package_managers.rpm_ostree.RpmOstree:
        _test_discovery(expected_package_manager.NAME, 'rpm-ostree and dnf5')

    else:
        _test_discovery(expected_package_manager.NAME, expected_package_manager.NAME)


def _parametrize_test_install() -> \
        Iterator[tuple[
            Container,
            PackageManagerClass,
            Package,
            str,
            Optional[str],
            Optional[str]]]:

    for container, package_manager_class in CONTAINER_BASE_MATRIX:
        if package_manager_class is tmt.package_managers.dnf.Yum:
            if container.url == CONTAINER_FEDORA_RAWHIDE.url:
                yield container, \
                    package_manager_class, \
                    Package('tree'), \
                    r"rpm -q --whatprovides tree \|\| yum install -y  tree && rpm -q --whatprovides tree", \
                    'Installing:', \
                    None  # noqa: E501

            elif 'ubi/8' in container.url:
                yield container, \
                    package_manager_class, \
                    Package('dconf'), \
                    r"rpm -q --whatprovides dconf \|\| yum install -y  dconf && rpm -q --whatprovides dconf", \
                    'Installed:\n  dconf', \
                    None  # noqa: E501

            else:
                yield container, \
                    package_manager_class, \
                    Package('tree'), \
                    r"rpm -q --whatprovides tree \|\| yum install -y  tree && rpm -q --whatprovides tree", \
                    'Installed:\n  tree', \
                    None  # noqa: E501

        elif package_manager_class is tmt.package_managers.dnf.Dnf:
            if container.url == CONTAINER_FEDORA_RAWHIDE.url:
                yield container, \
                    package_manager_class, \
                    Package('tree'), \
                    r"rpm -q --whatprovides tree \|\| dnf install -y  tree", \
                    'Installing:', \
                    None

            elif 'ubi/8' in container.url:
                yield container, \
                    package_manager_class, \
                    Package('dconf'), \
                    r"rpm -q --whatprovides dconf \|\| dnf install -y  dconf", \
                    'Installed:\n  dconf', \
                    None

            else:
                yield container, \
                    package_manager_class, \
                    Package('tree'), \
                    r"rpm -q --whatprovides tree \|\| dnf install -y  tree", \
                    'Installed:\n  tree', \
                    None

        elif package_manager_class is tmt.package_managers.dnf.Dnf5:
            yield container, \
                package_manager_class, \
                Package('tree'), \
                r"rpm -q --whatprovides tree \|\| dnf5 install -y  tree", \
                'Installing:', \
                None

        elif package_manager_class is tmt.package_managers.apt.Apt:
            yield container, \
                package_manager_class, \
                Package('tree'), \
                r"export DEBIAN_FRONTEND=noninteractive; dpkg-query --show tree \|\| apt install -y  tree", \
                'Setting up tree', \
                None  # noqa: E501

        elif package_manager_class is tmt.package_managers.rpm_ostree.RpmOstree:
            yield container, \
                package_manager_class, \
                Package('tree'), \
                r"rpm -q --whatprovides tree \|\| rpm-ostree install --apply-live --idempotent --allow-inactive  tree", \
                'Installing: tree', \
                None  # noqa: E501

        elif package_manager_class is tmt.package_managers.apk.Apk:
            yield container, \
                package_manager_class, \
                Package('tree'), \
                r"apk info -e tree \|\| apk add tree", \
                'Installing tree', \
                None

        else:
            pytest.fail(f"Unhandled package manager class '{package_manager_class}'.")


@pytest.mark.containers()
@pytest.mark.parametrize(('container_per_test',
                          'package_manager_class',
                          'package',
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
        package: Package,
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

    output = package_manager.install(package)

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
            if container.url == CONTAINER_FEDORA_RAWHIDE.url:
                yield container, \
                    package_manager_class, \
                    r"rpm -q --whatprovides tree-but-spelled-wrong \|\| dnf install -y  tree-but-spelled-wrong", \
                    None, \
                    'No match for argument: tree-but-spelled-wrong'  # noqa: E501

            else:
                yield container, \
                    package_manager_class, \
                    r"rpm -q --whatprovides tree-but-spelled-wrong \|\| dnf install -y  tree-but-spelled-wrong", \
                    None, \
                    'Error: Unable to find a match: tree-but-spelled-wrong'  # noqa: E501

        elif package_manager_class is tmt.package_managers.dnf.Yum:
            if container.url == CONTAINER_FEDORA_RAWHIDE.url:
                yield container, \
                    package_manager_class, \
                    r"rpm -q --whatprovides tree-but-spelled-wrong \|\| yum install -y  tree-but-spelled-wrong && rpm -q --whatprovides tree-but-spelled-wrong", \
                    None, \
                    'No match for argument: tree-but-spelled-wrong'  # noqa: E501

            elif 'fedora' in container.url:
                yield container, \
                    package_manager_class, \
                    r"rpm -q --whatprovides tree-but-spelled-wrong \|\| yum install -y  tree-but-spelled-wrong && rpm -q --whatprovides tree-but-spelled-wrong", \
                    None, \
                    'Error: Unable to find a match: tree-but-spelled-wrong'  # noqa: E501

            elif ('centos' in container.url and 'centos/7' not in container.url) \
                    or 'ubi/8' in container.url:
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

        elif package_manager_class is tmt.package_managers.apk.Apk:
            yield container, \
                package_manager_class, \
                r"apk info -e tree-but-spelled-wrong \|\| apk add tree-but-spelled-wrong", \
                None, \
                'ERROR: unable to select packages:\n  tree-but-spelled-wrong (no such package):\n    required by: world[tree-but-spelled-wrong]'  # noqa: E501

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
            if container.url == CONTAINER_FEDORA_RAWHIDE.url:
                yield container, \
                    package_manager_class, \
                    r"rpm -q --whatprovides tree-but-spelled-wrong \|\| yum install -y --skip-broken tree-but-spelled-wrong \|\| /bin/true", \
                    None, \
                    'No match for argument: tree-but-spelled-wrong'  # noqa: E501

            elif 'fedora' in container.url:  # noqa: SIM114
                yield container, \
                    package_manager_class, \
                    r"rpm -q --whatprovides tree-but-spelled-wrong \|\| yum install -y --skip-broken tree-but-spelled-wrong \|\| /bin/true", \
                    'No match for argument: tree-but-spelled-wrong', \
                    None  # noqa: E501

            elif ('centos' in container.url and 'centos/7' not in container.url) \
                    or 'ubi/8' in container.url:
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

        elif package_manager_class is tmt.package_managers.apk.Apk:
            yield container, \
                package_manager_class, \
                r"apk info -e tree-but-spelled-wrong \|\| apk add tree-but-spelled-wrong \|\| /bin/true", \
                None, \
                'ERROR: unable to select packages:\n  tree-but-spelled-wrong (no such package):\n    required by: world[tree-but-spelled-wrong]'  # noqa: E501

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
        Iterator[tuple[
            Container,
            PackageManagerClass,
            Package,
            str,
            Optional[str],
            Optional[str]]]:

    for container, package_manager_class in CONTAINER_BASE_MATRIX:
        if package_manager_class is tmt.package_managers.dnf.Dnf5:
            yield container, \
                package_manager_class, \
                Package('tree'), \
                r"dnf5 install -y  tree", \
                None, \
                None

        elif package_manager_class is tmt.package_managers.dnf.Dnf:
            if 'ubi/8' in container.url:
                yield container, \
                    package_manager_class, \
                    Package('dconf'), \
                    r"dnf install -y  dconf", \
                    'Installed:\n  dconf', \
                    None
            else:
                yield container, \
                    package_manager_class, \
                    Package('tree'), \
                    r"dnf install -y  tree", \
                    'Installed:\n  tree', \
                    None

        elif package_manager_class is tmt.package_managers.dnf.Yum:
            if 'ubi/8' in container.url:
                yield container, \
                    package_manager_class, \
                    Package('dconf'), \
                    r"yum install -y  dconf && rpm -q --whatprovides dconf", \
                    'Installed:\n  dconf', \
                    None

            else:
                yield container, \
                    package_manager_class, \
                    Package('tree'), \
                    r"yum install -y  tree && rpm -q --whatprovides tree", \
                    'Installed:\n  tree', \
                    None

        elif package_manager_class is tmt.package_managers.apt.Apt:
            yield container, \
                package_manager_class, \
                Package('tree'), \
                r"export DEBIAN_FRONTEND=noninteractive; apt install -y  tree", \
                'Setting up tree', \
                None

        elif package_manager_class is tmt.package_managers.rpm_ostree.RpmOstree:
            yield container, \
                package_manager_class, \
                Package('tree'), \
                r"rpm-ostree install --apply-live --idempotent --allow-inactive  tree", \
                'Installing: tree', \
                None

        elif package_manager_class is tmt.package_managers.apk.Apk:
            yield container, \
                package_manager_class, \
                Package('tree'), \
                r"apk add tree", \
                'Installing tree', \
                None

        else:
            pytest.fail(f"Unhandled package manager class '{package_manager_class}'.")


@pytest.mark.containers()
@pytest.mark.parametrize(('container_per_test',
                          'package_manager_class',
                          'package',
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
        package: Package,
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
        package,
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
            if 'centos/7' in container.url:
                yield container, \
                    package_manager_class, \
                    Package('tar'), \
                    True, \
                    r"rpm -q --whatprovides tar && yum reinstall -y  tar && rpm -q --whatprovides tar", \
                    'Reinstalling:\n tar', \
                    None  # noqa: E501

            else:
                yield container, \
                    package_manager_class, \
                    Package('tar'), \
                    True, \
                    r"rpm -q --whatprovides tar && yum reinstall -y  tar && rpm -q --whatprovides tar", \
                    'Reinstalled:\n  tar', \
                    None  # noqa: E501

        elif package_manager_class is tmt.package_managers.dnf.Dnf:
            yield container, \
                package_manager_class, \
                Package('tar'), \
                True, \
                r"rpm -q --whatprovides tar && dnf reinstall -y  tar", \
                'Reinstalled:\n  tar', \
                None

        elif package_manager_class is tmt.package_managers.dnf.Dnf5:
            yield container, \
                package_manager_class, \
                Package('tar'), \
                True, \
                r"rpm -q --whatprovides tar && dnf5 reinstall -y  tar", \
                'Reinstalling tar', \
                None

        elif package_manager_class is tmt.package_managers.apt.Apt:
            yield container, \
                package_manager_class, \
                Package('tar'), \
                True, \
                r"export DEBIAN_FRONTEND=noninteractive; dpkg-query --show tar && apt reinstall -y  tar", \
                'Setting up tar', \
                None  # noqa: E501

        elif package_manager_class is tmt.package_managers.rpm_ostree.RpmOstree:
            yield container, \
                package_manager_class, \
                Package('tar'), \
                False, \
                None, \
                None, \
                None

        elif package_manager_class is tmt.package_managers.apk.Apk:
            yield container, \
                package_manager_class, \
                Package('bash'), \
                True, \
                r"apk info -e bash && apk fix bash", \
                'Reinstalling bash', \
                None

        else:
            pytest.fail(f"Unhandled package manager class '{package_manager_class}'.")


@pytest.mark.containers()
@pytest.mark.parametrize(('container_per_test',
                          'package_manager_class',
                          'package',
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
        package: Package,
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

        output = package_manager.reinstall(package)

        assert_log(caplog, message=MATCH(
            rf"Run command: podman exec .+? /bin/bash -c '{expected_command}'"))

    else:
        with pytest.raises(tmt.utils.GeneralError) as excinfo:
            package_manager.reinstall(package)

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

            elif 'centos' in container.url and 'centos/7' not in container.url:
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

        elif package_manager_class is tmt.package_managers.apk.Apk:
            yield container, \
                package_manager_class, \
                True, \
                r"apk info -e tree-but-spelled-wrong && apk fix tree-but-spelled-wrong", \
                None, \
                ''

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
            if 'ubi/8' in container.url:
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

            elif 'centos/stream9' in container.url or 'fedora/40' in container.url:
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
            if 'centos/7' in container.url or 'ubi/8' in container.url:
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

            elif 'centos/stream9' in container.url or 'fedora/40' in container.url:
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

        elif package_manager_class is tmt.package_managers.apk.Apk:
            yield container, \
                package_manager_class, \
                Package('busybox'), \
                True, \
                r"apk info -e busybox", \
                r'\s+out:\s+busybox', \
                None

            yield container, \
                package_manager_class, \
                Package('tree-but-spelled-wrong'), \
                False, \
                r"apk info -e tree-but-spelled-wrong", \
                None, \
                ''

            yield container, \
                package_manager_class, \
                FileSystemPath('/usr/bin/arch'), \
                True, \
                r"apk info -e busybox", \
                r'\s+out:\s+busybox', \
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


def _parametrize_test_install_filesystempath() -> Iterator[
        tuple[Container, PackageManagerClass, FileSystemPath, Optional[str], Optional[str]]]:

    for container, package_manager_class in CONTAINER_BASE_MATRIX:
        if package_manager_class is tmt.package_managers.dnf.Dnf5:
            yield container, \
                package_manager_class, \
                FileSystemPath('/usr/bin/dos2unix'), \
                r"rpm -q --whatprovides /usr/bin/dos2unix \|\| dnf5 install -y  /usr/bin/dos2unix", \
                '[1/1] dos2unix', \
                None  # noqa: E501

        elif package_manager_class is tmt.package_managers.dnf.Dnf:
            yield container, \
                package_manager_class, \
                FileSystemPath('/usr/bin/dos2unix'), \
                r"rpm -q --whatprovides /usr/bin/dos2unix \|\| dnf install -y  /usr/bin/dos2unix", \
                'Installed:\n  dos2unix-', \
                None  # noqa: E501

        elif package_manager_class is tmt.package_managers.dnf.Yum:
            if 'centos/7' in container.url:
                yield container, \
                    package_manager_class, \
                    FileSystemPath('/usr/bin/dos2unix'), \
                    r"rpm -q --whatprovides /usr/bin/dos2unix \|\| yum install -y  /usr/bin/dos2unix && rpm -q --whatprovides /usr/bin/dos2unix", \
                    'Installed:\n  dos2unix.', \
                    None  # noqa: E501

            else:
                yield container, \
                    package_manager_class, \
                    FileSystemPath('/usr/bin/dos2unix'), \
                    r"rpm -q --whatprovides /usr/bin/dos2unix \|\| yum install -y  /usr/bin/dos2unix && rpm -q --whatprovides /usr/bin/dos2unix", \
                    'Installed:\n  dos2unix-', \
                    None  # noqa: E501

        elif package_manager_class is tmt.package_managers.apt.Apt:
            yield container, \
                package_manager_class, \
                FileSystemPath('/usr/bin/dos2unix'), \
                r"export DEBIAN_FRONTEND=noninteractive; dpkg-query --show dos2unix \|\| apt install -y  dos2unix", \
                "Setting up dos2unix", \
                None  # noqa: E501

        elif package_manager_class is tmt.package_managers.rpm_ostree.RpmOstree:
            yield container, \
                package_manager_class, \
                FileSystemPath('/usr/bin/dos2unix'), \
                r"rpm -qf /usr/bin/dos2unix \|\| rpm-ostree install --apply-live --idempotent --allow-inactive  /usr/bin/dos2unix", \
                "Installing 1 packages:\n  dos2unix-", \
                None  # noqa: E501

        elif package_manager_class is tmt.package_managers.apk.Apk:
            yield container, \
                package_manager_class, \
                FileSystemPath('/usr/bin/dos2unix'), \
                r"apk info -e dos2unix \|\| apk add dos2unix", \
                'Installing dos2unix', \
                None

        else:
            pytest.fail(f"Unhandled package manager class '{package_manager_class}'.")


@pytest.mark.containers()
@pytest.mark.parametrize(('container_per_test',
                          'package_manager_class',
                          'installable',
                          'expected_command',
                          'expected_stdout',
                          'expected_stderr'),
                         list(_parametrize_test_install_filesystempath()),
                         indirect=["container_per_test"],
                         ids=CONTAINER_MATRIX_IDS)
def test_install_filesystempath(
        container_per_test: ContainerData,
        guest_per_test: GuestContainer,
        package_manager_class: PackageManagerClass,
        installable: FileSystemPath,
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

    output = package_manager.install(installable)

    assert_log(caplog, message=MATCH(
        rf"Run command: podman exec .+? /bin/bash -c '{expected_command}'"))

    if expected_stdout:
        assert output.stdout is not None
        assert expected_stdout in output.stdout

    if expected_stderr:
        assert output.stderr is not None
        assert expected_stderr in output.stderr


def _parametrize_test_install_multiple() -> \
        Iterator[tuple[
            Container,
            PackageManagerClass,
            tuple[Package, Package],
            str,
            Optional[str],
            Optional[str]]]:

    for container, package_manager_class in CONTAINER_BASE_MATRIX:
        if package_manager_class is tmt.package_managers.dnf.Yum:
            if 'ubi/8' in container.url:
                yield container, \
                    package_manager_class, \
                    (Package('dconf'), Package('libpng')), \
                    r"rpm -q --whatprovides dconf libpng \|\| yum install -y  dconf libpng && rpm -q --whatprovides dconf libpng", \
                    'Complete!', \
                    None  # noqa: E501

            else:
                yield container, \
                    package_manager_class, \
                    (Package('tree'), Package('diffutils')), \
                    r"rpm -q --whatprovides tree diffutils \|\| yum install -y  tree diffutils && rpm -q --whatprovides tree diffutils", \
                    'Complete!', \
                    None  # noqa: E501

        elif package_manager_class is tmt.package_managers.dnf.Dnf:
            if 'ubi/8' in container.url:
                yield container, \
                    package_manager_class, \
                    (Package('dconf'), Package('libpng')), \
                    r"rpm -q --whatprovides dconf libpng \|\| dnf install -y  dconf libpng", \
                    'Complete!', \
                    None

            else:
                yield container, \
                    package_manager_class, \
                    (Package('tree'), Package('diffutils')), \
                    r"rpm -q --whatprovides tree diffutils \|\| dnf install -y  tree diffutils", \
                    'Complete!', \
                    None

        elif package_manager_class is tmt.package_managers.dnf.Dnf5:
            yield container, \
                package_manager_class, \
                (Package('tree'), Package('diffutils')), \
                r"rpm -q --whatprovides tree diffutils \|\| dnf5 install -y  tree diffutils", \
                None, \
                None

        elif package_manager_class is tmt.package_managers.apt.Apt:
            yield container, \
                package_manager_class, \
                (Package('tree'), Package('diffutils')), \
                r"export DEBIAN_FRONTEND=noninteractive; dpkg-query --show tree diffutils \|\| apt install -y  tree diffutils", \
                'Setting up tree', \
                None  # noqa: E501

        elif package_manager_class is tmt.package_managers.rpm_ostree.RpmOstree:
            yield container, \
                package_manager_class, \
                (Package('tree'), Package('diffutils')), \
                r"rpm -q --whatprovides tree diffutils \|\| rpm-ostree install --apply-live --idempotent --allow-inactive  tree diffutils", \
                'Installing: tree', \
                None  # noqa: E501

        elif package_manager_class is tmt.package_managers.apk.Apk:
            yield container, \
                package_manager_class, \
                (Package('tree'), Package('diffutils')), \
                r"apk info -e tree diffutils \|\| apk add tree diffutils", \
                'Installing tree', \
                None

        else:
            pytest.fail(f"Unhandled package manager class '{package_manager_class}'.")


@pytest.mark.containers()
@pytest.mark.parametrize(('container_per_test',
                          'package_manager_class',
                          'packages',
                          'expected_command',
                          'expected_stdout',
                          'expected_stderr'),
                         list(_parametrize_test_install_multiple()),
                         indirect=["container_per_test"],
                         ids=CONTAINER_MATRIX_IDS)
def test_install_multiple(
        container_per_test: ContainerData,
        guest_per_test: GuestContainer,
        package_manager_class: PackageManagerClass,
        packages: tuple[Package, Package],
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

    output = package_manager.install(*packages)

    assert_log(caplog, message=MATCH(
        rf"Run command: podman exec .+? /bin/bash -c '{expected_command}'"))

    if expected_stdout:
        assert output.stdout is not None
        assert expected_stdout in output.stdout

    if expected_stderr:
        assert output.stderr is not None
        assert expected_stderr in output.stderr


def _parametrize_test_install_downloaded() -> \
        Iterator[tuple[
            Container,
            PackageManagerClass,
            tuple[Package, Package],
            str,
            Optional[str],
            Optional[str]]]:

    for container, package_manager_class in CONTAINER_BASE_MATRIX:
        if package_manager_class is tmt.package_managers.dnf.Yum:
            if 'centos/7' in container.url:
                yield pytest.param(
                    container,
                    package_manager_class,
                    (Package('tree'), Package('diffutils')),
                    r"yum install -y --skip-broken /tmp/tree.rpm /tmp/diffutils.rpm \|\| /bin/true",  # noqa: E501
                    'Complete!',
                    None,
                    marks=pytest.mark.skip(reason="CentOS 7 does not support 'download' command")
                    )

            elif 'ubi/8' in container.url:
                yield container, \
                    package_manager_class, \
                    (Package('dconf'), Package('libpng')), \
                    r"yum install -y --skip-broken /tmp/dconf.rpm /tmp/libpng.rpm \|\| /bin/true", \
                    'Complete!', \
                    None  # noqa: E501

            else:
                yield container, \
                    package_manager_class, \
                    (Package('tree'), Package('diffutils')), \
                    r"yum install -y --skip-broken /tmp/tree.rpm /tmp/diffutils.rpm \|\| /bin/true", \
                    'Complete!', \
                    None  # noqa: E501

        elif package_manager_class is tmt.package_managers.dnf.Dnf:
            if 'ubi/8' in container.url:
                yield container, \
                    package_manager_class, \
                    (Package('dconf'), Package('libpng')), \
                    r"dnf install -y  /tmp/dconf.rpm /tmp/libpng.rpm", \
                    'Complete!', \
                    None

            else:
                yield container, \
                    package_manager_class, \
                    (Package('tree'), Package('diffutils')), \
                    r"dnf install -y  /tmp/tree.rpm /tmp/diffutils.rpm", \
                    'Complete!', \
                    None

        elif package_manager_class is tmt.package_managers.dnf.Dnf5:
            yield container, \
                package_manager_class, \
                (Package('tree'), Package('diffutils')), \
                r"dnf5 install -y  /tmp/tree.rpm /tmp/diffutils.rpm", \
                None, \
                None

        elif package_manager_class is tmt.package_managers.rpm_ostree.RpmOstree:
            yield container, \
                package_manager_class, \
                (Package('tree'), Package('diffutils')), \
                r"rpm-ostree install --apply-live --idempotent --allow-inactive  /tmp/tree.rpm /tmp/diffutils.rpm", \
                'Installing: tree', \
                None  # noqa: E501

        elif package_manager_class is tmt.package_managers.apt.Apt:
            yield pytest.param(
                container,
                package_manager_class,
                (Package('tree'), Package('diffutils')),
                r"export DEBIAN_FRONTEND=noninteractive; dpkg-query --show tree diffutils \|\| apt install -y  tree diffutils",  # noqa: E501
                'Setting up tree',
                None,
                marks=pytest.mark.skip(reason="not supported yet")
            )

        elif package_manager_class is tmt.package_managers.apk.Apk:
            yield pytest.param(
                container,
                package_manager_class,
                (Package('tree'), Package('diffutils')),
                r"apk info -e tree diffutils \|\| apk add tree diffutils",
                'Installing tree',
                None,
                marks=pytest.mark.skip(reason="not supported yet")
                )

        else:
            pytest.fail(f"Unhandled package manager class '{package_manager_class}'.")


@pytest.mark.containers()
@pytest.mark.parametrize(('container_per_test',
                          'package_manager_class',
                          'packages',
                          'expected_command',
                          'expected_stdout',
                          'expected_stderr'),
                         list(_parametrize_test_install_downloaded()),
                         indirect=["container_per_test"],
                         ids=CONTAINER_MATRIX_IDS)
def test_install_downloaded(
        container_per_test: ContainerData,
        guest_per_test: GuestContainer,
        package_manager_class: PackageManagerClass,
        packages: tuple[Package, Package],
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

    installables = tuple(PackagePath(f'/tmp/{package}.rpm') for package in packages)

    # TODO: move to a fixture
    guest_per_test.execute(ShellScript(
        f"""
        (yum download --destdir /tmp {packages[0]} {packages[1]} \
        || (dnf install -y 'dnf-command(download)' && dnf download --destdir /tmp {packages[0]} {packages[1]}) \
        || (dnf5 install -y 'dnf-command(download)' && dnf5 download --destdir /tmp {packages[0]} {packages[1]})) \
        && mv /tmp/{packages[0]}*.x86_64.rpm /tmp/{packages[0]}.rpm && mv /tmp/{packages[1]}*.x86_64.rpm /tmp/{packages[1]}.rpm
        """))  # noqa: E501

    # TODO: yum and downloaded packages results in post-install `rpm -q`
    # check to make sure packages were indeed installed - but that
    # breaks because that test uses original package paths, not package
    # names, and fails. Disable this check for now, but it's a sloppy
    # "solution".
    if package_manager_class is tmt.package_managers.dnf.Yum:
        output = package_manager.install(
            *installables,
            options=Options(
                check_first=False,
                skip_missing=True
                ))

    else:
        output = package_manager.install(
            *installables,
            options=Options(
                check_first=False
                ))

    assert_log(caplog, message=MATCH(
        rf"Run command: podman exec .+? /bin/bash -c '{expected_command}'"))

    if expected_stdout:
        assert output.stdout is not None
        assert expected_stdout in output.stdout

    if expected_stderr:
        assert output.stderr is not None
        assert expected_stderr in output.stderr


def _parametrize_test_install_debuginfo() -> Iterator[
        tuple[
            Container,
            PackageManagerClass,
            tuple[Package, Package],
            str,
            Optional[str],
            Optional[str]]]:

    for container, package_manager_class in CONTAINER_BASE_MATRIX:
        # Skip testing debuginfo install on coreos images
        if 'coreos' in container.url:
            yield pytest.param(
                container,
                package_manager_class,
                (Package('tree'), Package('dos2unix')),
                "",
                None,
                None,
                marks=pytest.mark.skip(reason="debuginfo install not supported yet on coreos")
                )

        elif package_manager_class is tmt.package_managers.dnf.Dnf5:
            yield container, \
                package_manager_class, \
                (Package('dos2unix'), Package('tree')), \
                r"debuginfo-install -y  dos2unix tree && rpm -q dos2unix-debuginfo tree-debuginfo", \
                None, \
                None  # noqa: E501

        elif package_manager_class is tmt.package_managers.dnf.Dnf \
                or package_manager_class is tmt.package_managers.dnf.Yum:
            if 'centos' in container.url:
                yield pytest.param(
                    container,
                    package_manager_class,
                    (Package('dos2unix'), Package('tree')),
                    r"debuginfo-install -y  dos2unix tree && rpm -q dos2unix-debuginfo tree-debuginfo",  # noqa: E501
                    None,
                    None,
                    marks=pytest.mark.skip(
                        reason='centos comes without debuginfo repos, we do not enable them yet'))

            elif 'ubi/8' in container.url:
                yield container, \
                    package_manager_class, \
                    (Package('dconf'), Package('libpng')), \
                    r"debuginfo-install -y  dconf libpng && rpm -q dconf-debuginfo libpng-debuginfo", \
                    None, \
                    None  # noqa: E501

            else:
                yield container, \
                    package_manager_class, \
                    (Package('dos2unix'), Package('tree')), \
                    r"debuginfo-install -y  dos2unix tree && rpm -q dos2unix-debuginfo tree-debuginfo", \
                    None, \
                    None  # noqa: E501

        elif package_manager_class is tmt.package_managers.apt.Apt \
                or package_manager_class is tmt.package_managers.rpm_ostree.RpmOstree \
                or package_manager_class is tmt.package_managers.apk.Apk:
            yield pytest.param(
                container,
                package_manager_class,
                (Package('tree'), Package('dos2unix')),
                "",
                None,
                None,
                marks=pytest.mark.skip(reason="not supported yet")
                )

        else:
            pytest.fail(f"Unhandled package manager class '{package_manager_class}'.")


@pytest.mark.containers()
@pytest.mark.parametrize(('container_per_test',
                          'package_manager_class',
                          'installables',
                          'expected_command',
                          'expected_stdout',
                          'expected_stderr'),
                         list(_parametrize_test_install_debuginfo()),
                         indirect=["container_per_test"],
                         ids=CONTAINER_MATRIX_IDS)
def test_install_debuginfo(
        container_per_test: ContainerData,
        guest_per_test: GuestContainer,
        package_manager_class: PackageManagerClass,
        installables: tuple[Package, Package],
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

    output = package_manager.install_debuginfo(*installables)

    assert_log(caplog, message=MATCH(
        rf"Run command: podman exec .+? /bin/bash -c '{expected_command}'"))

    if expected_stdout:
        assert output.stdout is not None
        assert expected_stdout in output.stdout

    if expected_stderr:
        assert output.stderr is not None
        assert expected_stderr in output.stderr


def _parametrize_test_install_debuginfo_nonexistent() -> Iterator[
        tuple[
            Container,
            PackageManagerClass,
            tuple[Package, Package],
            str,
            Optional[str],
            Optional[str]]]:

    for container, package_manager_class in CONTAINER_BASE_MATRIX:
        if package_manager_class is tmt.package_managers.dnf.Dnf5 \
                or package_manager_class is tmt.package_managers.dnf.Dnf \
                or package_manager_class is tmt.package_managers.dnf.Yum:
            yield container, \
                package_manager_class, \
                (Package('dos2unix'), Package('tree-but-spelled-wrong')), \
                r"debuginfo-install -y  dos2unix tree-but-spelled-wrong && rpm -q dos2unix-debuginfo tree-but-spelled-wrong-debuginfo", \
                None, \
                None  # noqa: E501

        elif package_manager_class is tmt.package_managers.apt.Apt \
                or package_manager_class is tmt.package_managers.rpm_ostree.RpmOstree \
                or package_manager_class is tmt.package_managers.apk.Apk:
            yield pytest.param(
                container,
                package_manager_class,
                (Package('tree-but-spelled-wrong'), Package('dos2unix')),
                "",
                None,
                None,
                marks=pytest.mark.skip(reason="not supported yet")
                )

        else:
            pytest.fail(f"Unhandled package manager class '{package_manager_class}'.")


@pytest.mark.containers()
@pytest.mark.parametrize(('container_per_test',
                          'package_manager_class',
                          'installables',
                          'expected_command',
                          'expected_stdout',
                          'expected_stderr'),
                         list(_parametrize_test_install_debuginfo_nonexistent()),
                         indirect=["container_per_test"],
                         ids=CONTAINER_MATRIX_IDS)
def test_install_debuginfo_nonexistent(
        container_per_test: ContainerData,
        guest_per_test: GuestContainer,
        package_manager_class: PackageManagerClass,
        installables: tuple[Package, Package],
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

    with pytest.raises(tmt.utils.RunError) as excinfo:
        package_manager.install_debuginfo(*installables)

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


def _parametrize_test_install_debuginfo_nonexistent_skip() -> Iterator[
        tuple[
            Container,
            PackageManagerClass,
            tuple[Package, Package],
            str,
            Optional[str],
            Optional[str]]]:

    for container, package_manager_class in CONTAINER_BASE_MATRIX:
        # Skip testing debuginfo install on coreos images
        if 'coreos' in container.url:
            yield pytest.param(
                container,
                package_manager_class,
                (Package('tree'), Package('dos2unix')),
                "",
                None,
                None,
                marks=pytest.mark.skip(reason="debuginfo install not supported yet on coreos")
                )

        elif package_manager_class is tmt.package_managers.dnf.Dnf5:
            yield container, \
                package_manager_class, \
                (Package('dos2unix'), Package('tree-but-spelled-wrong')), \
                r"debuginfo-install -y --skip-broken dos2unix tree-but-spelled-wrong", \
                None, \
                None

        elif package_manager_class is tmt.package_managers.dnf.Dnf \
                or package_manager_class is tmt.package_managers.dnf.Yum:
            if 'centos' in container.url:
                yield pytest.param(
                    container,
                    package_manager_class,
                    (Package('dos2unix'), Package('tree-but-spelled-wrong')),
                    r"debuginfo-install -y --skip-broken dos2unix tree-but-spelled-wrong",
                    None,
                    None,
                    marks=pytest.mark.skip(
                        reason='centos comes without debuginfo repos, we do not enable them yet'))

            else:
                yield container, \
                    package_manager_class, \
                    (Package('dos2unix'), Package('tree-but-spelled-wrong')), \
                    r"debuginfo-install -y --skip-broken dos2unix tree-but-spelled-wrong", \
                    None, \
                    None

        elif package_manager_class is tmt.package_managers.apt.Apt \
                or package_manager_class is tmt.package_managers.rpm_ostree.RpmOstree \
                or package_manager_class is tmt.package_managers.apk.Apk:
            yield pytest.param(
                container,
                package_manager_class,
                (Package('tree-but-spelled-wrong'), Package('dos2unix')),
                "",
                None,
                None,
                marks=pytest.mark.skip(reason="not supported yet")
                )

        else:
            pytest.fail(f"Unhandled package manager class '{package_manager_class}'.")


@pytest.mark.containers()
@pytest.mark.parametrize(('container_per_test',
                          'package_manager_class',
                          'installables',
                          'expected_command',
                          'expected_stdout',
                          'expected_stderr'),
                         list(_parametrize_test_install_debuginfo_nonexistent_skip()),
                         indirect=["container_per_test"],
                         ids=CONTAINER_MATRIX_IDS)
def test_install_debuginfo_nonexistent_skip(
        container_per_test: ContainerData,
        guest_per_test: GuestContainer,
        package_manager_class: PackageManagerClass,
        installables: tuple[Package, Package],
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

    output = package_manager.install_debuginfo(
        *installables,
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
