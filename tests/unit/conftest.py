import pathlib
from typing import Any

import _pytest.logging
import _pytest.tmpdir
import fmf
import py.path
import pytest

from tmt.log import Logger
from tmt.utils import Path


@pytest.fixture(name='root_logger')
def fixture_root_logger(caplog: _pytest.logging.LogCaptureFixture) -> Logger:
    return Logger.create(verbose=0, debug=0, quiet=False)


# Temporary directories and paths
#
# * the recommended way is to use `tmp_path` and `tmp_path_factory` fixtures
# * `tmp_path*` fixtures are not available in RHEL-8, `tmpdir` (and `tmpdir_factory`)
#   fixtures are - but these return `py.path.local` instead of a lovely `pathlib.Path`
# * `pathlib.Path` is also not good enough, as it may lack some methods in older
#   Python versions, that's why we have our own `tmt.utils.Path`.
#
# So, what we need:
#
# * a single name, we can't switch between `tmp_path` and `tmpdir` in every test
# * `tmt.utils.Path`, no strings, no `py.path.local`
# * works across all supported Python versions, from 3.6 in RHEL8 till 3.11 or so
#
# To solve this, we add here:
#
# * a wrapper class, representing the "tmp path factory". It's initialized with an
#   actual factory, has the same public API, but returns our `tmt.utils.Path`
# * two new fixtures, `tmppath` and `tmppath_factory` that consume available fixtures
#   and return corresponding `tmt.utils.Path`.
# * tests using `tmppath*` instead of pytest's own `tmp_path*` and `tmpdir*` fixtures
#
class TempPathFactory:
    def __init__(self, actual_factory: Any) -> None:
        self._actual_factory = actual_factory

    def getbasetemp(self) -> Path:
        return Path(str(self._actual_factory.getbasetemp()))

    def mktemp(self, basename: str, numbered: bool = True) -> Path:
        return Path(str(self._actual_factory.mktemp(basename, numbered=numbered)))


try:
    # If the import succeeds, we're about to wrap `Path` by `tmp_path`...
    from _pytest.tmpdir import tmp_path_factory  # noqa: F401

    @pytest.fixture(scope='session')
    def tmppath_factory(
        tmp_path_factory: '_pytest.tmpdir.TempPathFactory') -> TempPathFactory:  # noqa: F811
        return TempPathFactory(tmp_path_factory)

    @pytest.fixture()
    def tmppath(tmp_path: pathlib.Path) -> Path:
        return Path(str(tmp_path))

except ImportError:
    # ... and if the import fails, we're wrapping `py.path.local` from `tmpdir` family.

    # ignore[name-defined]: when inspected with our daily Python 3.9 or something,
    # the pytest is probably way newer than the one in RHEL8, and therefore the
    # name indeed would not exist. But this whole branch applies only with the old
    # pytest, therefore things are safe.
    @pytest.fixture(scope='session')
    def tmppath_factory(
            tmpdir_factory: '_pytest.tmpdir.TempdirFactory'  # type: ignore[name-defined]
            ) -> TempPathFactory:
        return TempPathFactory(tmpdir_factory)

    @pytest.fixture()
    def tmppath(tmpdir: py.path.local) -> Path:
        return Path(str(tmpdir))


@pytest.fixture(scope='module')
def source_dir(tmppath_factory: TempPathFactory) -> Path:
    """ Create dummy directory structure and remove it after tests """
    source_location = tmppath_factory.mktemp('source')
    (source_location / 'library').mkdir(parents=True)
    (source_location / 'lib_folder').mkdir()
    (source_location / 'tests').mkdir()
    for num in range(10):
        test_path = source_location / f'tests/bz{num}'
        test_path.mkdir()
        (test_path / 'runtests.sh').touch()
    return source_location


@pytest.fixture()
def target_dir(tmppath_factory: TempPathFactory) -> Path:
    """ Return target directory path and clean up after tests """
    return tmppath_factory.mktemp('target')


# Present two trees we have for identifier unit tests as fixtures, to make them
# usable in other tests as well.
@pytest.fixture(name='id_tree_defined')
def fixture_id_tree_defined() -> fmf.Tree:
    return fmf.Tree(Path(__file__).parent / 'id' / 'defined')


@pytest.fixture(name='id_tree_empty')
def fixture_id_tree_empty() -> fmf.Tree:
    return fmf.Tree(Path(__file__).parent / 'id' / 'empty')
