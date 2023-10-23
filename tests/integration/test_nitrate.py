import os
import shutil
import tempfile

import nitrate
import pytest
from fmf import Tree
from requre import RequreTestCase
from ruamel.yaml import YAML

import tmt.base
import tmt.cli
import tmt.log
from tmt.utils import ConvertError, Path

from .. import CliRunner

# Prepare path to examples
TEST_DIR = Path(__file__).parent


class Base(RequreTestCase):
    EXAMPLES = TEST_DIR / "data" / "nitrate"

    def setUp(self):
        super().setUp()
        self.tmpdir = Path(tempfile.mktemp(prefix=str(TEST_DIR)))
        shutil.copytree(self.EXAMPLES, self.tmpdir)
        self.cwd = os.getcwd()
        self.runner_output = None

        # Disable nitrate cache
        nitrate.set_cache_level(0)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)
        os.chdir(self.cwd)
        super().tearDown()
        if hasattr(
                self.runner_output,
                "exit_code") and self.runner_output.exit_code != 0:
            print("Return code:", self.runner_output.exit_code)
            print("Output:", self.runner_output.output)
            print("Exception:", self.runner_output.exception)


# General test plan for this component is: TP#29309
class NitrateExport(Base):

    def test_create(self):
        fmf_node = Tree(self.tmpdir).find("/new_testcase")
        assert "extra-nitrate" not in fmf_node.data

        os.chdir(self.tmpdir / "new_testcase")
        runner = CliRunner()
        self.runner_output = runner.invoke(
            tmt.cli.main,
            ["test", "export", "--how", "nitrate", "--ignore-git-validation",
             "--create", "--general", "--append-summary", "."],
            catch_exceptions=False)
        # Reload the node data to see if it appears there
        fmf_node = Tree(self.tmpdir).find("/new_testcase")
        assert "extra-nitrate" in fmf_node.data

    def test_create_dryrun(self):
        fmf_node_before = Tree(self.tmpdir).find("/new_testcase")
        assert "extra-nitrate" not in fmf_node_before.data

        os.chdir(self.tmpdir / "new_testcase")
        runner = CliRunner()
        self.runner_output = runner.invoke(
            tmt.cli.main,
            ["test", "export", "--how", "nitrate", "--ignore-git-validation",
             "--create", "--dry", "--general", "--append-summary", "."],
            catch_exceptions=False)
        fmf_node = Tree(self.tmpdir).find("/new_testcase")
        assert "extra-nitrate" not in fmf_node.data
        assert fmf_node_before.data == fmf_node.data
        assert "summary: tmt /new_testcase - This i" in self.runner_output.output

    def test_existing(self):
        fmf_node = Tree(self.tmpdir).find("/existing_testcase")
        assert fmf_node.data["extra-nitrate"] == "TC#0609686"

        os.chdir(self.tmpdir / "existing_testcase")
        runner = CliRunner()
        self.runner_output = runner.invoke(
            tmt.cli.main,
            ["test", "export", "--how", "nitrate", "--ignore-git-validation",
             "--create", "--general", "--append-summary", "."],
            catch_exceptions=False)
        fmf_node = Tree(self.tmpdir).find("/existing_testcase")

    def test_existing_dryrun(self):
        fmf_node = Tree(self.tmpdir).find("/existing_dryrun_testcase")
        assert fmf_node.data["extra-nitrate"] == "TC#0609686"

        os.chdir(self.tmpdir / "existing_dryrun_testcase")
        runner = CliRunner()
        self.runner_output = runner.invoke(
            tmt.cli.main,
            ["test", "export", "--how", "nitrate", "--ignore-git-validation",
             "--debug", "--dry", "--general", "--bugzilla", "--append-summary", "."],
            catch_exceptions=False)
        assert "summary: tmt /existing_dryrun_testcase - ABCDEF" in self.runner_output.output

    def test_existing_release_dryrun(self):
        fmf_node = Tree(self.tmpdir).find("/existing_dryrun_release_testcase")
        assert fmf_node.data["extra-nitrate"] == "TC#0609686"

        os.chdir(self.tmpdir / "existing_dryrun_release_testcase")
        runner = CliRunner()
        self.runner_output = runner.invoke(tmt.cli.main,
                                           ["test",
                                            "export",
                                            "--how",
                                            "nitrate",
                                            "--debug",
                                            "--dry",
                                            "--ignore-git-validation",
                                            "--general",
                                            "--bugzilla",
                                            "--link-runs",
                                            "--append-summary",
                                            "."],
                                           catch_exceptions=False)
        assert "summary: tmt /existing_dryrun_release_testcase - ABCDEF" in \
               self.runner_output.output
        assert "Linked to general plan 'TP#28164 - tmt / General'" in self.runner_output.output
        assert "Link to plan 'TP#31698" in self.runner_output.output
        assert "Link to run 'TR#425023" in self.runner_output.output

    def test_coverage_bugzilla(self):
        fmf_node = Tree(self.tmpdir).find("/existing_testcase")
        assert fmf_node.data["extra-nitrate"] == "TC#0609686"

        os.chdir(self.tmpdir / "existing_testcase")
        runner = CliRunner()
        self.runner_output = runner.invoke(tmt.cli.main,
                                           ["test",
                                            "export",
                                            "--how",
                                            "nitrate",
                                            "--ignore-git-validation",
                                            "--bugzilla",
                                            "--append-summary",
                                            "."],
                                           catch_exceptions=False)
        assert self.runner_output.exit_code == 0

    def test_missing_user_dryrun(self):
        os.chdir(self.tmpdir / "existing_testcase_missing_user")
        runner = CliRunner()
        with pytest.raises(ConvertError):
            self.runner_output = runner.invoke(
                tmt.cli.main,
                ["test", "export", "--how", "nitrate",
                 "--debug", "--dry", "."],
                catch_exceptions=False)

    def test_export_blocked_by_validation(self):
        os.chdir(self.tmpdir / "validation")
        fmf_node = Tree(self.tmpdir).find("/validation")
        with fmf_node as data:
            data['test'] = 'echo hello world'
        runner = CliRunner()
        with pytest.raises(ConvertError) as error:
            self.runner_output = runner.invoke(
                tmt.cli.main,
                ["test", "export", "--nitrate", "--debug", "--dry", "--append-summary", "."],
                catch_exceptions=False)
        assert "Uncommitted changes" in str(error.value)

    def test_export_forced_validation(self):
        os.chdir(self.tmpdir / "validation")
        fmf_node = Tree(self.tmpdir).find("/validation")
        with fmf_node as data:
            data['extra-nitrate'] = 'TC#599605'

        runner = CliRunner()

        self.runner_output = runner.invoke(
            tmt.cli.main,
            ["test", "export", "--nitrate", "--debug", "--ignore-git-validation",
             "--append-summary", "."],
            catch_exceptions=False)

        assert "Exporting regardless 'Uncommitted changes" in self.runner_output.output


class NitrateImport(Base):

    def test_import_manual_confirmed(self):
        runner = CliRunner()
        # TODO: import does not respect --root param anyhow (could)
        self.runner_output = runner.invoke(
            tmt.cli.main,
            ['-vvvvdddd', '--root', self.tmpdir / "import_case",
             "test", "import", "--no-general", "--nitrate", "--manual", "--case=609704"],
            catch_exceptions=False)
        assert self.runner_output.exit_code == 0
        assert "Importing the 'Imported_Test_Case'" in self.runner_output.output
        assert "test case found 'TC#0609704'" in self.runner_output.output
        assert "Metadata successfully stored into" in self.runner_output.output
        filename = next(
            filter(
                lambda x: "Metadata successfully stored into" in x
                          and "main.fmf" in x,
                self.runner_output.output.splitlines())).split("'")[1]
        # /home/jscotka/git/tmt/Manual/Imported_Test_Case/main.fmf
        # TODO: not possible to specify, where to store data,
        # it always creates Manual subdir, I do not want it.
        assert "/Manual/Imported_Test_Case/main.fmf" in filename
        assert Path(filename).exists()
        with open(Path(filename)) as file:
            yaml = YAML(typ='safe')
            out = yaml.load(file)
            assert "Tier1" in out["tag"]
            assert "tmt_test_component" in out["component"]

    def test_import_manual_proposed(self):
        runner = CliRunner()
        self.runner_output = runner.invoke(
            tmt.cli.main, ['--root', self.tmpdir / "import_case", "test",
                           "import", "--no-general", "--nitrate", "--manual", "--case=609705"],
            catch_exceptions=False)
        assert self.runner_output.exit_code == 0
        # TODO: This is strange, expect at least some output in
        # case there is proper case, just case is not CONFIRMED
        # I can imagine also e.g. at least raise error but not pass,
        # with no output
        assert self.runner_output.output.strip() == ""
        fmf_node = Tree(self.tmpdir).find("/import_case")
        assert fmf_node is None


class NitrateImportAutomated(Base):
    test_md_content = """# Setup
Do this and that to setup the environment.

# Test

## Step
Step one.

Step two.

Step three.

## Expect
Expect one.

Expect two

Expect three.

# Cleanup
This is a breakdown.
"""
    main_fmf_content = """summary: Simple smoke test
description: |
    Just run 'tmt --help' to make sure the binary is sane.
    This is really that simple. Nothing more here. Really.
contact: Petr Šplíchal <psplicha@redhat.com>
component:
- tmt
test: ./runtest.sh
framework: beakerlib
require:
- fmf
recommend:
- tmt
duration: 5m
enabled: true
tag: []
link:
-   relates: https://bugzilla.redhat.com/show_bug.cgi?id=12345
-   relates: https://bugzilla.redhat.com/show_bug.cgi?id=1234567
adjust:
-   because: comment
    enabled: false
    when: distro == rhel-4, rhel-5
    continue: false
-   environment:
        PHASES: novalgrind
    when: arch == s390x
    continue: false
extra-nitrate: TC#0609926
extra-summary: /tmt/integration
extra-task: /tmt/integration
"""

    def test_basic(self):
        os.chdir(self.tmpdir / "import_case_automated")
        files = os.listdir()
        assert "Makefile" in files
        assert "main.fmf" not in files
        assert "test.md" not in files
        runner = CliRunner()
        self.runner_output = runner.invoke(
            tmt.cli.main, [
                "test", "import", "--nitrate"], catch_exceptions=False)
        assert self.runner_output.exit_code == 0
        files = os.listdir()
        assert "Makefile" in files
        assert "test.md" in files
        with open("test.md") as file:
            assert self.test_md_content in file.read()
        assert "main.fmf" in files
        with open("main.fmf") as file:
            yaml = YAML(typ='safe')
            generated = yaml.load(file)
            referenced = yaml.load(self.main_fmf_content)
            assert generated == referenced

    def test_old_relevancy(self):
        os.chdir(self.tmpdir / "import_old_relevancy")
        files = os.listdir()
        assert files == ["Makefile"]
        runner = CliRunner()
        self.runner_output = runner.invoke(
            tmt.cli.main, [
                "test", "import", "--nitrate", "--no-general"], catch_exceptions=False)
        assert self.runner_output.exit_code == 0

        tree_f36_intel = tmt.Tree(
            logger=tmt.log.Logger.create(),
            path='.',
            fmf_context={
                'distro': ['fedora-36'],
                'arch': ['x86_64']})

        found_tests = tree_f36_intel.tests(names=['/import_old_relevancy'])
        assert len(found_tests) == 1
        test = found_tests[0]
        assert test.enabled
        assert test.environment == {"ARCH": "not arch"}
        assert test.node.get("extra-nitrate") == "TC#0545993"

        tree_f35_intel = tmt.Tree(
            logger=tmt.log.Logger.create(),
            path='.',
            fmf_context={
                'distro': ['fedora-35'],
                'arch': ['x86_64']})

        found_tests = tree_f35_intel.tests(names=['/import_old_relevancy'])
        assert len(found_tests) == 1
        test = found_tests[0]
        assert not test.enabled
        # second rule is ignored if the order is correctly transferred
        assert test.environment == {}
        assert test.node.get("extra-nitrate") == "TC#0545993"
