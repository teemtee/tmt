"""
Common functions for package manager tests
"""

from typing import Optional

import _pytest.logging
import pytest
from pytest_container import Container
from pytest_container.container import ContainerData

import tmt.log
import tmt.package_managers
from tmt.package_managers import (
    Installable,
    Options,
    Package,
    PackageManager,
    PackageManagerClass,
    PackagePath,
)
from tmt.steps.provision.podman import GuestContainer
from tmt.utils import RunError, ShellScript

from . import MATCH, assert_log


def assert_output(
    expected_output: Optional[str], stdout: Optional[str], stderr: Optional[str]
) -> None:
    """
    Check that the expected output is present

    We don't care whether the expected string is in stdout or stderr.
    Just make sure the output is there.
    """

    # Nothing to do if there are no expectations
    if not expected_output:
        return

    combined_output = (stdout or "") + (stderr or "")
    assert combined_output != ""
    assert expected_output in combined_output


# Local images created via `make images/test`, reference to local registry
CONTAINER_FEDORA_RAWHIDE = Container(
    url='containers-storage:localhost/tmt/container/test/fedora/rawhide/upstream:latest'
)
CONTAINER_FEDORA_41 = Container(
    url='containers-storage:localhost/tmt/container/test/fedora/41/upstream:latest'
)
CONTAINER_FEDORA_40 = Container(
    url='containers-storage:localhost/tmt/container/test/fedora/40/upstream:latest'
)
CONTAINER_FEDORA_39 = Container(
    url='containers-storage:localhost/tmt/container/test/fedora/39/upstream:latest'
)
CONTAINER_CENTOS_STREAM_10 = Container(
    url='containers-storage:localhost/tmt/container/test/centos/stream10/upstream:latest'
)
CONTAINER_CENTOS_STREAM_9 = Container(
    url='containers-storage:localhost/tmt/container/test/centos/stream9/upstream:latest'
)
CONTAINER_CENTOS_7 = Container(
    url='containers-storage:localhost/tmt/container/test/centos/7/upstream:latest'
)
CONTAINER_UBI_8 = Container(
    url='containers-storage:localhost/tmt/container/test/ubi/8/upstream:latest'
)
CONTAINER_UBUNTU_2204 = Container(
    url='containers-storage:localhost/tmt/container/test/ubuntu/22.04/upstream:latest'
)
CONTAINER_DEBIAN_127 = Container(
    url='containers-storage:localhost/tmt/container/test/debian/12.7/upstream:latest'
)
CONTAINER_FEDORA_COREOS = Container(
    url='containers-storage:localhost/tmt/container/test/fedora/coreos:stable'
)
CONTAINER_FEDORA_COREOS_OSTREE = Container(
    url='containers-storage:localhost/tmt/container/test/fedora/coreos/ostree:stable'
)
CONTAINER_ALPINE = Container(url='containers-storage:localhost/tmt/container/test/alpine:latest')

PACKAGE_MANAGER_DNF5 = tmt.package_managers._PACKAGE_MANAGER_PLUGIN_REGISTRY.get_plugin('dnf5')
PACKAGE_MANAGER_DNF = tmt.package_managers._PACKAGE_MANAGER_PLUGIN_REGISTRY.get_plugin('dnf')
PACKAGE_MANAGER_YUM = tmt.package_managers._PACKAGE_MANAGER_PLUGIN_REGISTRY.get_plugin('yum')
PACKAGE_MANAGER_APT = tmt.package_managers._PACKAGE_MANAGER_PLUGIN_REGISTRY.get_plugin('apt')
PACKAGE_MANAGER_RPMOSTREE = tmt.package_managers._PACKAGE_MANAGER_PLUGIN_REGISTRY.get_plugin(
    'rpm-ostree'
)
PACKAGE_MANAGER_APK = tmt.package_managers._PACKAGE_MANAGER_PLUGIN_REGISTRY.get_plugin('apk')


def has_legacy_dnf(container: ContainerData) -> bool:
    """
    Checks whether a container provides older ``dnf`` and ``yum``.

    At some point, Fedora switched to ``dnf5`` completely, and older
    ``dnf`` and ``yum`` commands are now mere symlinks to ``dnf5``.
    """

    if 'fedora' not in container.image_url_or_id and 'centos' not in container.image_url_or_id:
        return False

    return container.image_url_or_id not in (
        CONTAINER_FEDORA_RAWHIDE.url,
        CONTAINER_FEDORA_41.url,
        CONTAINER_FEDORA_COREOS.url,
        CONTAINER_FEDORA_COREOS_OSTREE.url,
    )


def has_dnf5_preinstalled(container: ContainerData) -> bool:
    """
    Checks whether a container provides ``dnf5``
    """

    return container.image_url_or_id in (
        CONTAINER_FEDORA_RAWHIDE.url,
        CONTAINER_FEDORA_41.url,
        CONTAINER_FEDORA_COREOS.url,
        CONTAINER_FEDORA_COREOS_OSTREE.url,
    )


def is_dnf5_preinstalled(container: ContainerData) -> bool:
    return container.image_url_or_id in (
        CONTAINER_FEDORA_RAWHIDE.url,
        CONTAINER_FEDORA_41.url,
        CONTAINER_FEDORA_COREOS.url,
        CONTAINER_FEDORA_COREOS_OSTREE.url,
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
    # CentOS Stream
    (CONTAINER_CENTOS_STREAM_10, PACKAGE_MANAGER_DNF),
    (CONTAINER_CENTOS_STREAM_9, PACKAGE_MANAGER_DNF),
    (CONTAINER_CENTOS_STREAM_9, PACKAGE_MANAGER_YUM),
    # CentOS
    (CONTAINER_CENTOS_7, PACKAGE_MANAGER_YUM),
    # UBI
    (CONTAINER_UBI_8, PACKAGE_MANAGER_DNF),
    (CONTAINER_UBI_8, PACKAGE_MANAGER_YUM),
    # Ubuntu
    (CONTAINER_UBUNTU_2204, PACKAGE_MANAGER_APT),
    # Debian
    (CONTAINER_DEBIAN_127, PACKAGE_MANAGER_APT),
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


def filter_test_cases_by_package_manager(package_manager_class: PackageManagerClass):
    """
    Filter test cases and IDs for a specific package manager.

    Returns a tuple of (test_cases, test_ids) where test_cases contains
    parameters for test functions, and test_ids are the corresponding IDs.
    """
    filtered_matrix = [
        (
            container,
            pm_class,
            Package('tree'),
            EXPECTED_INSTALL_COMMANDS.get((container, pm_class), ''),
            EXPECTED_INSTALL_OUTPUT.get((container, pm_class), None),
        )
        for container, pm_class in CONTAINER_BASE_MATRIX
        if pm_class is package_manager_class
    ]

    filtered_ids = [
        matrix_id
        for i, matrix_id in enumerate(CONTAINER_MATRIX_IDS)
        if CONTAINER_BASE_MATRIX[i][1] is package_manager_class
    ]

    return filtered_matrix, filtered_ids


# Expected commands and outputs for various package managers
EXPECTED_INSTALL_COMMANDS = {
    # APT package manager commands
    (
        CONTAINER_UBUNTU_2204,
        PACKAGE_MANAGER_APT,
    ): r"set -x\s+export DEBIAN_FRONTEND=noninteractive\s+installable_packages=\"tree\"\s+dpkg-query --show \$installable_packages \\\s+\|\| apt install -y  \$installable_packages\s+exit \$\?",  # noqa: E501
    (
        CONTAINER_DEBIAN_127,
        PACKAGE_MANAGER_APT,
    ): r"set -x\s+export DEBIAN_FRONTEND=noninteractive\s+installable_packages=\"tree\"\s+dpkg-query --show \$installable_packages \\\s+\|\| apt install -y  \$installable_packages\s+exit \$\?",  # noqa: E501
    # DNF package manager commands (simplified for example)
    (
        CONTAINER_FEDORA_40,
        PACKAGE_MANAGER_DNF,
    ): r"set -x\s+installable_packages=\"tree\"\s+rpm -q \$installable_packages \\\s+\|\| dnf install -y  \$installable_packages\s+exit \$\?",  # noqa: E501
    # Add other package managers as needed
}

EXPECTED_INSTALL_OUTPUT = {
    # APT package manager outputs
    (CONTAINER_UBUNTU_2204, PACKAGE_MANAGER_APT): 'Setting up tree',
    (CONTAINER_DEBIAN_127, PACKAGE_MANAGER_APT): 'Setting up tree',
    # Other package managers outputs
    (CONTAINER_FEDORA_40, PACKAGE_MANAGER_DNF): 'Complete!',
    # Add other package managers as needed
}

# Pre-filter test cases for specific package managers
APT_TEST_CASES = list(filter_test_cases_by_package_manager(PACKAGE_MANAGER_APT)[0])


def create_package_manager(
    container: ContainerData,
    guest: GuestContainer,
    package_manager_class: PackageManagerClass,
    logger: tmt.log.Logger,
) -> PackageManager:
    guest_data = tmt.steps.provision.podman.PodmanGuestData(
        image=container.image_url_or_id, container=container.container_id
    )

    guest = tmt.steps.provision.podman.GuestContainer(
        logger=logger, data=guest_data, name='dummy-container'
    )
    guest.start()
    guest.show()

    if package_manager_class is tmt.package_managers.dnf.Dnf5:
        # Note that our custom images contain `dnf5` already
        if is_dnf5_preinstalled(container):
            pass

        else:
            guest.execute(ShellScript('dnf install --nogpgcheck -y dnf5'))

    return package_manager_class(guest=guest, logger=logger)


# Generate the discovery matrix
CONTAINER_DISCOVERY_MATRIX = {}

for container, package_manager_class in CONTAINER_BASE_MATRIX:
    if container.url in CONTAINER_DISCOVERY_MATRIX:
        continue

    CONTAINER_DISCOVERY_MATRIX[container.url] = (container, package_manager_class)


# Helper functions that perform the actual test logic
# These will be called by the individual test files


def do_test_discovery(
    container: ContainerData,
    guest: GuestContainer,
    expected_package_manager: PackageManagerClass,
    root_logger: tmt.log.Logger,
    caplog: _pytest.logging.LogCaptureFixture,
) -> None:
    guest.show()

    def _test_discovery(expected: str, expected_discovery: str) -> None:
        caplog.clear()

        guest.facts.sync(guest)

        assert guest.facts.package_manager == expected

        assert_log(caplog, message=MATCH(rf"^Discovered package managers: {expected_discovery}$"))

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


def do_test_install(
    container_per_test: ContainerData,
    guest_per_test: GuestContainer,
    package_manager_class: PackageManagerClass,
    package: Package,
    expected_command: str,
    expected_output: Optional[str],
    root_logger: tmt.log.Logger,
    caplog: _pytest.logging.LogCaptureFixture,
) -> None:
    package_manager = create_package_manager(
        container_per_test, guest_per_test, package_manager_class, root_logger
    )

    output = package_manager.install(package)

    assert_log(
        caplog,
        message=MATCH(rf"(?sm)Run command: podman exec .+? /bin/bash -c '{expected_command}'"),
    )

    assert_output(expected_output, output.stdout, output.stderr)


def do_test_refresh_metadata(
    container_per_test: ContainerData,
    guest_per_test: GuestContainer,
    package_manager_class: PackageManagerClass,
    expected_command: str,
    expected_output: Optional[str],
    root_logger: tmt.log.Logger,
    caplog: _pytest.logging.LogCaptureFixture,
) -> None:
    package_manager = create_package_manager(
        container_per_test, guest_per_test, package_manager_class, root_logger
    )

    output = package_manager.refresh_metadata()

    assert_log(
        caplog, message=MATCH(rf"Run command: podman exec .+? /bin/bash -c '{expected_command}'")
    )

    assert_output(expected_output, output.stdout, output.stderr)


def do_test_install_nonexistent(
    container: ContainerData,
    guest: GuestContainer,
    package_manager_class: PackageManagerClass,
    expected_command: str,
    expected_output: Optional[str],
    root_logger: tmt.log.Logger,
    caplog: _pytest.logging.LogCaptureFixture,
) -> None:
    package_manager = create_package_manager(container, guest, package_manager_class, root_logger)

    with pytest.raises(tmt.utils.RunError) as excinfo:
        package_manager.install(Package('tree-but-spelled-wrong'))

    assert_log(
        caplog,
        message=MATCH(rf"(?sm)Run command: podman exec .+? /bin/bash -c '{expected_command}'"),
    )

    assert excinfo.type is RunError
    assert excinfo.value.returncode != 0

    assert_output(expected_output, excinfo.value.stdout, excinfo.value.stderr)


def do_test_install_nonexistent_skip(
    container: ContainerData,
    guest: GuestContainer,
    package_manager_class: PackageManagerClass,
    expected_command: str,
    expected_output: Optional[str],
    root_logger: tmt.log.Logger,
    caplog: _pytest.logging.LogCaptureFixture,
) -> None:
    package_manager = create_package_manager(container, guest, package_manager_class, root_logger)

    output = package_manager.install(
        Package('tree-but-spelled-wrong'), options=Options(skip_missing=True)
    )

    assert_log(
        caplog,
        message=MATCH(rf"(?sm)Run command: podman exec .+? /bin/bash -c '{expected_command}'"),
    )

    assert_output(expected_output, output.stdout, output.stderr)


def do_test_install_dont_check_first(
    container_per_test: ContainerData,
    guest_per_test: GuestContainer,
    package_manager_class: PackageManagerClass,
    package: Package,
    expected_command: str,
    expected_output: Optional[str],
    root_logger: tmt.log.Logger,
    caplog: _pytest.logging.LogCaptureFixture,
) -> None:
    package_manager = create_package_manager(
        container_per_test, guest_per_test, package_manager_class, root_logger
    )

    output = package_manager.install(package, options=Options(check_first=False))

    assert_log(
        caplog,
        message=MATCH(rf"(?sm)Run command: podman exec .+? /bin/bash -c '{expected_command}'"),
    )

    assert_output(expected_output, output.stdout, output.stderr)


def do_test_reinstall(
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
    package_manager = create_package_manager(
        container_per_test, guest_per_test, package_manager_class, root_logger
    )

    if supported:
        assert expected_command is not None

        output = package_manager.reinstall(package)

        assert_log(
            caplog,
            message=MATCH(rf"(?sm)Run command: podman exec .+? /bin/bash -c '{expected_command}'"),
        )

    else:
        with pytest.raises(tmt.utils.GeneralError) as excinfo:
            package_manager.reinstall(package)

        assert excinfo.value.message == "rpm-ostree does not support reinstall operation."

    if (
        expected_output and supported
    ):  # Only check output if the package manager supports reinstall
        assert_output(expected_output, output.stdout, output.stderr)


def do_test_reinstall_nonexistent(
    container: ContainerData,
    guest: GuestContainer,
    package_manager_class: PackageManagerClass,
    supported: bool,
    expected_command: Optional[str],
    expected_output: Optional[str],
    root_logger: tmt.log.Logger,
    caplog: _pytest.logging.LogCaptureFixture,
) -> None:
    package_manager = create_package_manager(container, guest, package_manager_class, root_logger)

    if supported:
        assert expected_command is not None

        with pytest.raises(RunError) as excinfo:
            package_manager.reinstall(Package('tree-but-spelled-wrong'))

        assert_log(
            caplog,
            message=MATCH(rf"(?sm)Run command: podman exec .+? /bin/bash -c '{expected_command}'"),
        )

        assert excinfo.type is RunError
        assert excinfo.value.returncode != 0

    else:
        with pytest.raises(tmt.utils.GeneralError) as excinfo:
            package_manager.reinstall(Package('tree-but-spelled-wrong'))

        assert excinfo.value.message == "rpm-ostree does not support reinstall operation."

    if expected_output and supported:
        assert_output(expected_output, excinfo.value.stdout, excinfo.value.stderr)


def do_test_check_presence(
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
    package_manager = create_package_manager(container, guest, package_manager_class, root_logger)

    assert package_manager.check_presence(installable) == {installable: expected_result}

    assert_log(
        caplog,
        message=MATCH(rf"(?sm)Run command: podman exec .+? /bin/bash -c '{expected_command}'"),
    )

    if expected_output:
        assert_log(caplog, remove_colors=True, message=MATCH(expected_output))


def do_test_install_filesystempath(
    container_per_test: ContainerData,
    guest_per_test: GuestContainer,
    package_manager_class: PackageManagerClass,
    installable: Installable,
    expected_command: str,
    expected_output: Optional[str],
    root_logger: tmt.log.Logger,
    caplog: _pytest.logging.LogCaptureFixture,
) -> None:
    package_manager = create_package_manager(
        container_per_test, guest_per_test, package_manager_class, root_logger
    )

    output = package_manager.install(installable)

    assert_log(
        caplog,
        message=MATCH(rf"(?sm)Run command: podman exec .+? /bin/bash -c '{expected_command}'"),
    )

    assert_output(expected_output, output.stdout, output.stderr)


def do_test_install_multiple(
    container_per_test: ContainerData,
    guest_per_test: GuestContainer,
    package_manager_class: PackageManagerClass,
    packages: tuple[Package, Package],
    expected_command: str,
    expected_output: Optional[str],
    root_logger: tmt.log.Logger,
    caplog: _pytest.logging.LogCaptureFixture,
) -> None:
    package_manager = create_package_manager(
        container_per_test, guest_per_test, package_manager_class, root_logger
    )

    output = package_manager.install(*packages)

    assert_log(
        caplog,
        message=MATCH(rf"(?sm)Run command: podman exec .+? /bin/bash -c '{expected_command}'"),
    )

    assert_output(expected_output, output.stdout, output.stderr)


def do_test_install_downloaded(
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
    package_manager = create_package_manager(
        container_per_test, guest_per_test, package_manager_class, root_logger
    )

    installables = tuple(PackagePath(f'/tmp/{package}.rpm') for package in packages)

    # TODO: move to a fixture
    guest_per_test.execute(
        ShellScript(
            f"""
        (yum download --destdir /tmp {packages[0]} {packages[1]} \\
        || (dnf install -y 'dnf-command(download)' && dnf download --destdir /tmp {packages[0]} {packages[1]}) \\
        || (dnf5 install -y 'dnf-command(download)' && dnf5 download --destdir /tmp {packages[0]} {packages[1]})) \\
        && mv /tmp/{artifacts[0]} /tmp/{packages[0]}.rpm && mv /tmp/{artifacts[1]} /tmp/{packages[1]}.rpm
        """  # noqa: E501
        )
    )

    # TODO: yum and downloaded packages results in post-install `rpm -q`
    # check to make sure packages were indeed installed - but that
    # breaks because that test uses original package paths, not package
    # names, and fails. Disable this check for now, but it's a sloppy
    # "solution".
    if package_manager_class is tmt.package_managers.dnf.Yum:
        output = package_manager.install(
            *installables, options=Options(check_first=False, skip_missing=True)
        )

    else:
        output = package_manager.install(*installables, options=Options(check_first=False))

    assert_log(
        caplog,
        message=MATCH(rf"(?sm)Run command: podman exec .+? /bin/bash -c '{expected_command}'"),
    )

    assert_output(expected_output, output.stdout, output.stderr)


def do_test_install_debuginfo(
    container_per_test: ContainerData,
    guest_per_test: GuestContainer,
    package_manager_class: PackageManagerClass,
    installables: tuple[Package, Package],
    expected_command: str,
    expected_output: Optional[str],
    root_logger: tmt.log.Logger,
    caplog: _pytest.logging.LogCaptureFixture,
) -> None:
    package_manager = create_package_manager(
        container_per_test, guest_per_test, package_manager_class, root_logger
    )

    output = package_manager.install_debuginfo(*installables)

    assert_log(
        caplog, message=MATCH(rf"Run command: podman exec .+? /bin/bash -c '{expected_command}'")
    )

    assert_output(expected_output, output.stdout, output.stderr)


def do_test_install_debuginfo_nonexistent(
    container_per_test: ContainerData,
    guest_per_test: GuestContainer,
    package_manager_class: PackageManagerClass,
    installables: tuple[Package, Package],
    expected_command: str,
    expected_output: Optional[str],
    root_logger: tmt.log.Logger,
    caplog: _pytest.logging.LogCaptureFixture,
) -> None:
    package_manager = create_package_manager(
        container_per_test, guest_per_test, package_manager_class, root_logger
    )

    with pytest.raises(RunError) as excinfo:
        package_manager.install_debuginfo(*installables)

    assert_log(
        caplog, message=MATCH(rf"Run command: podman exec .+? /bin/bash -c '{expected_command}'")
    )

    assert excinfo.type is RunError
    assert excinfo.value.returncode != 0

    assert_output(expected_output, excinfo.value.stdout, excinfo.value.stderr)


def do_test_install_debuginfo_nonexistent_skip(
    container_per_test: ContainerData,
    guest_per_test: GuestContainer,
    package_manager_class: PackageManagerClass,
    installables: tuple[Package, Package],
    expected_command: str,
    expected_output: Optional[str],
    root_logger: tmt.log.Logger,
    caplog: _pytest.logging.LogCaptureFixture,
) -> None:
    package_manager = create_package_manager(
        container_per_test, guest_per_test, package_manager_class, root_logger
    )

    output = package_manager.install_debuginfo(*installables, options=Options(skip_missing=True))

    assert_log(
        caplog, message=MATCH(rf"Run command: podman exec .+? /bin/bash -c '{expected_command}'")
    )

    assert_output(expected_output, output.stdout, output.stderr)
