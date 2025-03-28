"""
Tests for package managers - entry point for all package manager tests
"""

import pytest
from pytest_container.container import ContainerData

import tmt.log
import tmt.plugins
from tmt.steps.provision.podman import GuestContainer, PodmanGuestData

# We will need a logger...
logger = tmt.log.Logger.create()
logger.add_console_handler()

# Explore available plugins
tmt.plugins.explore(logger)


@pytest.fixture(name='guest')
def fixture_guest(container: ContainerData, root_logger: tmt.log.Logger) -> GuestContainer:
    guest_data = PodmanGuestData(image=container.image_url_or_id, container=container.container_id)

    guest = GuestContainer(logger=root_logger, data=guest_data, name='dummy-container')

    guest.start()

    return guest


@pytest.fixture(name='guest_per_test')
def fixture_guest_per_test(
    container_per_test: ContainerData, root_logger: tmt.log.Logger
) -> GuestContainer:
    guest_data = PodmanGuestData(
        image=container_per_test.image_url_or_id, container=container_per_test.container_id
    )

    guest = GuestContainer(logger=root_logger, data=guest_data, name='dummy-container')

    guest.start()

    return guest
