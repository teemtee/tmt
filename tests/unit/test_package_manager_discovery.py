"""
Tests for package manager discovery
"""

from collections.abc import Iterator

import _pytest.logging
import pytest
from pytest_container.container import ContainerData

import tmt.log
import tmt.package_managers
from tmt.package_managers import PackageManagerClass
from tmt.steps.provision.podman import GuestContainer

from ._test_package_manager import (
    CONTAINER_DISCOVERY_MATRIX,
    do_test_discovery,
)


def _parametrize_test_discovery() -> Iterator[tuple[ContainerData, PackageManagerClass]]:
    yield from CONTAINER_DISCOVERY_MATRIX.values()


@pytest.mark.containers
@pytest.mark.parametrize(
    ('container', 'expected_package_manager'),
    list(_parametrize_test_discovery()),
    indirect=["container"],
    ids=[container.url for container, _ in CONTAINER_DISCOVERY_MATRIX.values()],
)
def test_discovery(
    container: ContainerData,
    guest: GuestContainer,
    expected_package_manager: PackageManagerClass,
    root_logger: tmt.log.Logger,
    caplog: _pytest.logging.LogCaptureFixture,
) -> None:
    """Test package manager discovery on various container types."""
    do_test_discovery(container, guest, expected_package_manager, root_logger, caplog)
