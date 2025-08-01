from collections.abc import Iterator

import pytest

from tests.unit.conftest import create_path_helper
from tmt.export.nitrate import convert_manual_to_nitrate
from tmt.utils import Path


@pytest.fixture(name="manual_test_path")
def fixture_manual_test_path(tmppath: Path, test_path: Path) -> Iterator[Path]:
    """Provides a temporary directory populated with 'manual_test' data."""
    yield from create_path_helper(tmppath, test_path, "manual_test")


def test_export_to_nitrate_step(manual_test_path: Path):
    """Verify that the 'step' content is correctly converted to HTML."""
    file_name = 'test.md'
    assert Path(file_name).is_file()

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


def test_export_to_nitrate_expect(manual_test_path: Path):
    """Verify that the 'expect' content is correctly converted to HTML."""
    file_name = 'test.md'
    assert Path(file_name).is_file()

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


def test_export_to_nitrate_empty_file(manual_test_path: Path):
    """Check that an empty file results in empty HTML output."""
    file_name = 'test_empty.md'
    assert Path(file_name).is_file()

    html = convert_manual_to_nitrate(Path(file_name))
    html_generated = ('', '', '', '')
    assert html == html_generated


def test_export_to_nitrate_setup_doesnt_exist(manual_test_path: Path):
    """Verify that 'setup' is empty when not present in the source."""
    file_name = 'test.md'
    assert Path(file_name).is_file()

    setup = convert_manual_to_nitrate(Path(file_name))[2]
    assert setup == ''


def test_export_to_nitrate_cleanup_latest_heading(manual_test_path: Path):
    """Ensure 'cleanup' content under the last heading is converted."""
    file_name = 'test.md'
    assert Path(file_name).is_file()

    cleanup = convert_manual_to_nitrate(Path(file_name))[3]
    html_generated = """<p>Optionally remove temporary directory created \
in the first step
2 line of cleanup
3 line of cleanup</p>
"""
    assert cleanup == html_generated
