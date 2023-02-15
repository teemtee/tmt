from pathlib import Path

import _pytest.logging
import pytest

from tmt.log import Logger


@pytest.fixture(name='root_logger')
def fixture_root_logger(caplog: _pytest.logging.LogCaptureFixture) -> Logger:
    return Logger.create(verbose=0, debug=0, quiet=False)


@pytest.fixture(scope='module')
def source_dir(tmpdir_factory):
    """ Create dummy directory structure and remove it after tests """
    source_location = Path(tmpdir_factory.mktemp('source'))
    (source_location / 'library').mkdir(parents=True)
    (source_location / 'lib_folder').mkdir()
    (source_location / 'tests').mkdir()
    for num in range(10):
        test_path = source_location / f'tests/bz{num}'
        test_path.mkdir()
        (test_path / 'runtests.sh').touch()
    yield source_location


@pytest.fixture()
def target_dir(tmpdir_factory):
    """ Return target directory path and clean up after tests """
    return Path(tmpdir_factory.mktemp('target'))
