import os
import shutil
import tempfile
from unittest import TestCase

import fmf

import tmt
import tmt.cli
import tmt.log
from tests import CliRunner
from tmt.identifier import ID_KEY
from tmt.utils import Path

runner = CliRunner()
test_path = Path(__file__).parent / "id"
root_logger = tmt.log.Logger.create()


class IdEmpty(TestCase):

    def setUp(self):
        self.path = Path(tempfile.mkdtemp()) / "empty"
        shutil.copytree(test_path / "empty", self.path)
        self.original_directory = Path.cwd()
        os.chdir(self.path)
        self.base_tree = fmf.Tree(self.path)

    def tearDown(self):
        os.chdir(self.original_directory)
        shutil.rmtree(self.path)

    def test_base(self):
        node = self.base_tree.find("/some/structure")
        test = tmt.Test(logger=root_logger, node=node)
        assert test.id is None

    def test_manually_add_id(self):
        # TODO: it's really not possible to use fixtures with methods??
        from tmt.log import Logger
        root_logger = Logger.create(verbose=0, debug=0, quiet=False)

        node = self.base_tree.find("/some/structure")
        test = tmt.Test(logger=root_logger, node=node)
        assert test.id is None
        identifier = tmt.identifier.add_uuid_if_not_defined(node, False, root_logger)
        assert len(identifier) > 10

        self.base_tree = fmf.Tree(self.path)
        node = self.base_tree.find("/some/structure")
        test = tmt.Test(logger=root_logger, node=node)
        assert test.id == identifier


class TestGeneratorDefined(TestCase):

    def setUp(self):
        self.path = Path(tempfile.mkdtemp()) / "defined"
        shutil.copytree(test_path / "defined", self.path)
        self.original_directory = Path.cwd()
        os.chdir(self.path)

    def tearDown(self):
        os.chdir(self.original_directory)
        shutil.rmtree(self.path)

    def test_test_dry(self):
        result = runner.invoke(
            tmt.cli.main, ["test", "id", "--dry", "^/no"])
        assert "added to test '/no" in result.output
        result = runner.invoke(
            tmt.cli.main, ["test", "id", "--dry", "^/no"])
        assert "added to test '/no" in result.output

    def test_test_real(self):
        # Empty before
        node = fmf.Tree(self.path).find("/no")
        assert node.get(ID_KEY) is None

        # Generate only when called for the first time
        result = runner.invoke(tmt.cli.main, ["test", "id", "^/no"])
        assert "added to test '/no" in result.output
        result = runner.invoke(tmt.cli.main, ["test", "id", "^/no"])
        assert "added to test '/no" not in result.output

        # Defined after
        node = fmf.Tree(self.path).find("/no")
        assert len(node.data[ID_KEY]) > 10


class TestGeneratorEmpty(TestCase):

    def setUp(self):
        self.path = Path(tempfile.mkdtemp()) / "empty"
        shutil.copytree(test_path / "empty", self.path)
        self.original_directory = Path.cwd()
        os.chdir(self.path)

    def tearDown(self):
        os.chdir(self.original_directory)
        shutil.rmtree(self.path)

    def test_test_dry(self):
        result = runner.invoke(
            tmt.cli.main, ["test", "id", "--dry"])
        assert "added to test '/some/structure'" in result.output
        result = runner.invoke(
            tmt.cli.main, ["test", "id", "--dry"])
        assert "added to test '/some/structure'" in result.output

    def test_test_real(self):
        result = runner.invoke(tmt.cli.main, ["test", "id"])
        assert "added to test '/some/structure'" in result.output

        result = runner.invoke(tmt.cli.main, ["test", "id"])
        assert "added to test '/some/structure'" not in result.output

        base_tree = fmf.Tree(self.path)
        node = base_tree.find("/some/structure")
        assert len(node.data[ID_KEY]) > 10
