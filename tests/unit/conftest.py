import shutil
from pathlib import Path

import _pytest.logging
import pytest

from tmt.log import Logger


@pytest.fixture(name='root_logger')
def fixture_root_logger(caplog: _pytest.logging.LogCaptureFixture) -> Logger:
    return Logger.create(verbose=0, debug=0, quiet=False)


@pytest.fixture(scope='module')
def source_dir():
    """ Create dummy directory structure and remove it after tests """
    source_location = Path('/tmp/tmt_testing_source')
    (source_location / 'library').mkdir(parents=True)
    (source_location / 'lib_folder').mkdir()
    (source_location / 'tests').mkdir()
    for num in range(10):
        test_path = source_location / f'tests/bz{num}'
        test_path.mkdir()
        (test_path / 'runtests.sh').touch()
    yield source_location
    shutil.rmtree(source_location, ignore_errors=True)


@pytest.fixture()
def target_dir():
    """ Return target directory path and clean up after tests """
    target_path = Path('/tmp/tmt_testing_target')
    yield target_path
    shutil.rmtree(target_path, ignore_errors=True)
