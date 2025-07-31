from collections.abc import Iterator

import fmf
import pytest

import tmt
import tmt.cli._root
from tests import CliRunner
from tests.unit.conftest import create_path_helper
from tmt.identifier import ID_KEY, add_uuid_if_not_defined
from tmt.utils import Path

# Common setup for tests in this file
runner = CliRunner()


@pytest.fixture(name='test_path')
def fixture_test_path(test_path) -> Path:
    """Provides the path to the test data for 'id' tests"""
    return test_path / "id"


@pytest.fixture
def defined_path(
    tmppath: Path,
    test_path: Path,
) -> Iterator[Path]:
    """Fixture for tests requiring the 'defined' test data."""
    yield from create_path_helper(tmppath, test_path, "defined")


@pytest.fixture
def empty_path(
    tmppath: Path,
    test_path: Path,
) -> Iterator[Path]:
    """Fixture for tests requiring the 'empty' test data."""
    yield from create_path_helper(tmppath, test_path, "empty")


def test_base(empty_path: Path, root_logger: tmt.log.Logger):
    """The 'id' attribute should be None initially"""
    base_tree = fmf.Tree(empty_path)
    node = base_tree.find("/some/structure")
    test = tmt.Test(logger=root_logger, node=node)
    assert test.id is None


def test_manually_add_id(empty_path: Path, root_logger: tmt.log.Logger):
    """A new id can be generated and applied manually"""
    base_tree = fmf.Tree(empty_path)
    node = base_tree.find("/some/structure")
    test = tmt.Test(logger=root_logger, node=node)
    assert test.id is None

    # Generate and apply a new ID
    identifier = add_uuid_if_not_defined(node, False, root_logger)
    assert isinstance(identifier, str)
    assert len(identifier) > 10

    # After reloading the fmf tree, the test should have the new ID
    new_tree = fmf.Tree(empty_path)
    node = new_tree.find("/some/structure")
    test = tmt.Test(logger=root_logger, node=node)
    assert test.id == identifier


def test_defined_dry(defined_path: Path):
    """--dry run should report a new id"""
    result = runner.invoke(tmt.cli._root.main, ["test", "id", "--dry", "^/no"])
    assert "added to test '/no" in result.output
    # A second dry run should report the same
    result = runner.invoke(tmt.cli._root.main, ["test", "id", "--dry", "^/no"])
    assert "added to test '/no" in result.output


def test_defined_real(defined_path: Path):
    """A real run should persist the new id"""
    # Check that there is no id before the run
    node = fmf.Tree(defined_path).find("/no")
    assert node.get(ID_KEY) is None

    # The first run should generate and persist the id
    result = runner.invoke(tmt.cli._root.main, ["test", "id", "^/no"])
    assert "added to test '/no" in result.output

    # The second run should not add it again
    result = runner.invoke(tmt.cli._root.main, ["test", "id", "^/no"])
    assert "added to test '/no" not in result.output

    # Verify that the id has been defined in the file
    node = fmf.Tree(defined_path).find("/no")
    assert node.get(ID_KEY) is not None
    assert isinstance(node.data[ID_KEY], str)
    assert len(node.data[ID_KEY]) > 10


def test_empty_dry(empty_path: Path):
    """--dry run should report a new id"""
    result = runner.invoke(tmt.cli._root.main, ["test", "id", "--dry"])
    assert "added to test '/some/structure'" in result.output
    # A second dry run should report the same
    result = runner.invoke(tmt.cli._root.main, ["test", "id", "--dry"])
    assert "added to test '/some/structure'" in result.output


def test_empty_real(empty_path: Path):
    """A real run should persist the new id"""
    # The first run should generate and persist the id
    result = runner.invoke(tmt.cli._root.main, ["test", "id"])
    assert "added to test '/some/structure'" in result.output

    # The second run should not add it again
    result = runner.invoke(tmt.cli._root.main, ["test", "id"])
    assert "added to test '/some/structure'" not in result.output

    # Verify that the id has been defined in the file
    base_tree = fmf.Tree(empty_path)
    node = base_tree.find("/some/structure")
    assert node.get(ID_KEY) is not None
    assert len(node.data[ID_KEY]) > 10
