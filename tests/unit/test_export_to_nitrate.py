import os
import shutil
import tempfile
from unittest import TestCase

from tmt.export.nitrate import convert_manual_to_nitrate
from tmt.utils import Path

TEST_DIR = Path(__file__).parent


class NitrateExportAutomated(TestCase):
    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp(prefix=str(TEST_DIR)))
        shutil.copytree(TEST_DIR, self.tmp_dir, dirs_exist_ok=True)
        self.cwd = os.getcwd()
        self.dir_name = 'manual_test'

    def test_export_to_nitrate_step(self):
        os.chdir(self.tmp_dir / self.dir_name)
        files = os.listdir()
        file_name = 'test.md'
        assert file_name in files

        step = convert_manual_to_nitrate(Path(file_name))[0]
        html_generated = """<b>Test</b>\
<p>Step 1.</p><p>Verify tmt shows help page
<code>bash
tmt --help</code></p>
<p>Step 2.</p><p>Check that error about missing metadata is sane
<code>bash
tmt tests ls</code></p>
<p>Step 3.</p><p>Initialize metadata structure
<code>bash
tmt init</code></p>
<b>Test one</b><p>Step 4.</p><p>description for step 1-1</p>
<p>Step 5.</p><p>description for step 1-2</p>
<b>Test two</b><p>Step 6.</p><p>description for step 2-1</p>
<p>Step 7.</p><p>description for step 2-2</p>
"""
        assert step == html_generated

    def test_export_to_nitrate_expect(self):
        os.chdir(self.tmp_dir / self.dir_name)
        files = os.listdir()
        file_name = 'test.md'
        assert file_name in files

        expect = convert_manual_to_nitrate(Path(file_name))[1]
        html_generated = """<b>Test</b>\
<p>Step 1.</p><p>Text similar to the one below is displayed
```
Usage: tmt [OPTIONS] COMMAND [ARGS]...</p>
<p>Test Management Tool</p>
<p>Options:
...
```</p>
<p>Step 2.</p><p><code>ERROR  No metadata found in the '.' directory. \
Use 'tmt init' to get started.</code></p>
<p>Step 3.</p><ol>
<li>Metadata structure was created
<code>bash
$ cat .fmf/version
1</code></li>
<li>Tool prints advice about next steps
<code>To populate it with example content, use --template with mini, \
base or full.</code></li>
</ol>
<b>Test one</b><p>Step 4.</p><p>description for result 1-1</p>
<p>Step 5.</p><p>description for Expected Result 1-2</p>
<b>Test two</b><p>Step 6.</p><p>description for result 2-1</p>
<p>Step 7.</p><p>description for Expected Result 2-2</p>
"""
        assert expect == html_generated

    def test_export_to_nitrate_empty_file(self):
        os.chdir(self.tmp_dir / self.dir_name)
        files = os.listdir()
        file_name = 'test_empty.md'
        assert file_name in files
        html = convert_manual_to_nitrate(Path(file_name))
        html_generated = ('', '', '', '')
        assert html == html_generated

    def test_export_to_nitrate_setup_doesnt_exist(self):
        os.chdir(self.tmp_dir / self.dir_name)
        files = os.listdir()
        file_name = 'test.md'
        assert file_name in files
        cleanup = convert_manual_to_nitrate(Path(file_name))[2]
        html_generated = ''
        assert cleanup == html_generated

    def test_export_to_nitrate_cleanup_latest_heading(self):
        os.chdir(self.tmp_dir / self.dir_name)
        files = os.listdir()
        file_name = 'test.md'
        assert file_name in files

        cleanup = convert_manual_to_nitrate(Path(file_name))[3]
        html_generated = """<p>Optionally remove temporary directory created \
in the first step
2 line of cleanup
3 line of cleanup</p>
"""
        assert cleanup == html_generated

    def tearDown(self):
        shutil.rmtree(self.tmp_dir)
        os.chdir(self.cwd)
        super().tearDown()
