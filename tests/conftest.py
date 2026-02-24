import os
import pathlib
import shutil
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

import _pytest.logging
import _pytest.tmpdir
import pytest

from tests import CliRunner, RunTmt
from tmt.log import Logger
from tmt.steps.provision.podman import GuestContainer, PodmanGuestData
from tmt.utils import Path

if TYPE_CHECKING:
    from pytest_container.container import ContainerData


@pytest.fixture(name='root_logger')
def fixture_root_logger(caplog: _pytest.logging.LogCaptureFixture) -> Logger:
    """
    A logger to use for logging and/or spawning logger hierarchy.
    """

    return Logger.create(verbose=0, debug=0, quiet=False, apply_colors_logging=False)


@pytest.fixture(name='run_tmt')
def fixture_run_tmt() -> RunTmt:
    """
    Invoke a ``tmt`` command with given options.
    """

    return CliRunner().invoke


# Equivalent fixtures to `tmp_path_factory` and `tmp_path` recasting the paths
# to tmt's Path.
class TempPathFactory:
    def __init__(self, actual_factory: Any) -> None:
        self._actual_factory = actual_factory

    def getbasetemp(self) -> Path:
        return Path(str(self._actual_factory.getbasetemp()))

    def mktemp(self, basename: str, numbered: bool = True) -> Path:
        return Path(str(self._actual_factory.mktemp(basename, numbered=numbered)))


@pytest.fixture(scope='session')
def tmppath_factory(tmp_path_factory: _pytest.tmpdir.TempPathFactory) -> TempPathFactory:
    return TempPathFactory(tmp_path_factory)


@pytest.fixture
def tmppath(tmp_path: pathlib.Path) -> Path:  # noqa: TID251
    return Path(str(tmp_path))


@pytest.fixture
def test_path() -> Path:
    """Returns the path to the directory containing the tests."""
    return Path(__file__).parent / 'unit'


def create_path_helper(tmppath: Path, test_path: Path, name: str) -> Iterator[Path]:
    """
    The returned function creates a temporary directory, populates it with test
    data from a given subdirectory, and changes the current working directory to it.
    the original working directory is restored after the test.
    """
    path = tmppath / name
    shutil.copytree(test_path / name, path)

    original_directory = Path.cwd()
    os.chdir(path)

    try:
        yield path
    finally:
        os.chdir(original_directory)


@pytest.fixture(scope='module')
def source_dir(tmppath_factory: TempPathFactory) -> Path:
    """
    Create dummy directory structure and remove it after tests
    """

    source_location = tmppath_factory.mktemp('source')
    (source_location / 'library').mkdir(parents=True)
    (source_location / 'lib_folder').mkdir()
    (source_location / 'tests').mkdir()
    for num in range(10):
        test_path = source_location / f'tests/bz{num}'
        test_path.mkdir()
        (test_path / 'runtests.sh').touch()
    return source_location


@pytest.fixture
def target_dir(tmppath_factory: TempPathFactory) -> Path:
    """
    Return target directory path and clean up after tests
    """

    return tmppath_factory.mktemp('target')


@pytest.fixture(name='guest')
def fixture_guest(container: 'ContainerData', root_logger: Logger) -> GuestContainer:
    guest_data = PodmanGuestData(image=container.image_url_or_id, container=container.container_id)

    guest = GuestContainer(logger=root_logger, data=guest_data, name='dummy-container')

    guest.start()

    return guest


@pytest.fixture(name='guest_per_test')
def fixture_guest_per_test(
    container_per_test: 'ContainerData', root_logger: Logger
) -> GuestContainer:
    guest_data = PodmanGuestData(
        image=container_per_test.image_url_or_id, container=container_per_test.container_id
    )

    guest = GuestContainer(logger=root_logger, data=guest_data, name='dummy-container')

    guest.start()

    return guest
