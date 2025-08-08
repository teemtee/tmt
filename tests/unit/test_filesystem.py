import os
import stat
import time
from typing import Optional
from unittest import mock

import pytest

import tmt.log
import tmt.utils
import tmt.utils.filesystem
from tmt.utils import Path

# A dictionary mapping file paths to their content for test setup.
# This reduces duplication and improves readability in tests.
_EXPECTED_TEST_FILES = {
    ".fmf/version": "1",
    "file1.txt": "content1",
    "file2.txt": "content2",
    "subdir/file3.txt": "content3",
}

CopyTreePathConfig = tuple[Path, Path, bool]


@pytest.fixture(name="copy_tree_paths")
def fixture_copy_tree_paths(tmppath: Path) -> CopyTreePathConfig:
    """
    Prepare source and destination directories for copy_tree tests.

    This fixture creates a temporary source directory populated with various
    files, subdirectories, and a symlink. It also creates an empty destination
    directory.

    Returns a tuple containing the source path, destination path, and a boolean
    indicating if symlinks are supported on the platform.
    """
    source_dir = tmppath / "source"
    dest_dir = tmppath / "dest"
    source_dir.mkdir()
    dest_dir.mkdir()

    # Create test files and directories from the EXPECTED_FILES dictionary
    for path, content in _EXPECTED_TEST_FILES.items():
        file_path = source_dir / path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content)

    # Create a symlink if the platform supports it
    symlinks_supported = False
    try:
        (source_dir / "symlink.txt").symlink_to(source_dir / "file1.txt")
        symlinks_supported = True
    except (OSError, NotImplementedError):
        pass

    return source_dir, dest_dir, symlinks_supported


def _assert_permissions_copied(src_path: Path, dest_path: Path):
    """Assert that file/directory permissions are copied correctly."""
    src_mode = stat.S_IMODE(os.stat(src_path).st_mode)
    dest_mode = stat.S_IMODE(os.stat(dest_path).st_mode)
    assert src_mode == dest_mode, (
        f"Permission mismatch for {dest_path}. Expected {oct(src_mode)}, got {oct(dest_mode)}"
    )


def _assert_timestamps_copied(src_path: Path, dest_path: Path, delta_seconds=2):
    """
    Assert that file/directory timestamps (mtime) are copied within a tolerance.
    """
    src_stat = os.stat(src_path)
    dest_stat = os.stat(dest_path)

    assert abs(src_stat.st_mtime - dest_stat.st_mtime) <= delta_seconds, (
        f"mtime mismatch for {dest_path}. Expected {src_stat.st_mtime}, got {dest_stat.st_mtime}"
    )


def _setup_metadata_test_item(
    source_dir: Path, name: str, is_dir: bool, mode: int, atime: float, mtime: float
) -> Path:
    """Helper to create a file or directory with specific metadata."""
    item_path = source_dir / name
    if is_dir:
        item_path.mkdir()
    else:
        item_path.write_text(f"content of {name}")
    os.chmod(item_path, mode)
    os.utime(item_path, (atime, mtime))
    return item_path


def _run_metadata_test_for_item(
    dest_dir: Path, src_item: Path, delta_seconds: Optional[int] = None
):
    """Helper to run metadata assertions for a given item."""
    dest_item = dest_dir / src_item.name
    _assert_permissions_copied(src_item, dest_item)
    _assert_timestamps_copied(
        src_item, dest_item, delta_seconds=delta_seconds if delta_seconds is not None else 2
    )


def test_copy_tree_basic(copy_tree_paths: CopyTreePathConfig, root_logger: tmt.log.Logger):
    """Test basic copy operation with default parameters."""
    source_dir, dest_dir, symlinks_supported = copy_tree_paths
    tmt.utils.filesystem.copy_tree(source_dir, dest_dir, root_logger)

    # Check if all files were copied and their content is correct
    for path, content in _EXPECTED_TEST_FILES.items():
        dest_file = dest_dir / path
        assert dest_file.exists(), f"File '{path}' was not copied."
        assert dest_file.read_text() == content, f"Content mismatch for file '{path}'."

    # Check symlink if supported
    if symlinks_supported:
        symlink_path = dest_dir / "symlink.txt"
        assert symlink_path.is_symlink(), "Symlink was not created."
        target = symlink_path.readlink()
        assert Path(target).name == "file1.txt", "Symlink points to the wrong target."


def test_copy_empty_source_directory(tmppath: Path, root_logger: tmt.log.Logger):
    """Test copying an empty source directory."""
    empty_src = tmppath / "empty_src"
    empty_dst = tmppath / "empty_dst"
    empty_src.mkdir()

    tmt.utils.filesystem.copy_tree(empty_src, empty_dst, root_logger)

    # Verify the destination directory exists and is empty
    assert empty_dst.exists()
    assert empty_dst.is_dir()
    assert not list(empty_dst.iterdir())  # Directory is empty


def test_deeply_nested_directories(tmppath: Path, root_logger: tmt.log.Logger):
    """Test copying deeply nested directory structures."""
    deep_src = tmppath / "deep_src"
    deep_dst = tmppath / "deep_dst"
    deep_src.mkdir()
    test_content = "test content for deep copy"

    current_dir = deep_src
    for level in range(1, 11):
        current_dir = current_dir / f"level_{level}"
        current_dir.mkdir()
        (current_dir / f"file_at_level_{level}.txt").write_text(f"{test_content} at level {level}")

    tmt.utils.filesystem.copy_tree(deep_src, deep_dst, root_logger)

    # Check if the deepest directory and file exist in the copied structure
    deepest_path = Path(
        "level_1/level_2/level_3/level_4/level_5/level_6/level_7/level_8/level_9/level_10"
    )
    assert (deep_dst / deepest_path).exists()

    # Check content of a file in the deepest directory
    deepest_file = deep_dst / deepest_path / "file_at_level_10.txt"
    assert deepest_file.exists()
    assert deepest_file.read_text() == f"{test_content} at level 10"


@mock.patch('os.access', return_value=False)
@mock.patch('tmt.utils.filesystem._copy_tree_cp', return_value=False)
@mock.patch(
    'tmt.utils.filesystem._copy_tree_shutil',
    side_effect=PermissionError("Simulated permission error"),
)
def test_permission_error_handling(
    mock_shutil,
    mock_cp,
    mock_access,
    copy_tree_paths: CopyTreePathConfig,
    root_logger: tmt.log.Logger,
):
    """Test handling of permission errors during copy."""
    source_dir, dest_dir, _ = copy_tree_paths
    with pytest.raises(tmt.utils.GeneralError) as excinfo:
        tmt.utils.filesystem.copy_tree(source_dir, dest_dir, root_logger)

    assert (
        "permission error" in str(excinfo.value).lower()
        or "permission" in str(excinfo.value.__cause__).lower()
    )


def test_nonexistent_source_directory(tmppath: Path, root_logger: tmt.log.Logger):
    """Test error handling when source directory doesn't exist."""
    nonexistent_src = tmppath / "nonexistent_src"
    destination = tmppath / "destination"

    with pytest.raises(tmt.utils.GeneralError) as excinfo:
        tmt.utils.filesystem.copy_tree(nonexistent_src, destination, root_logger)

    assert "not a directory or does not exist" in str(excinfo.value)


@mock.patch('tmt.utils.filesystem._copy_tree_shutil', wraps=tmt.utils.filesystem._copy_tree_shutil)
@mock.patch('tmt.utils.filesystem._copy_tree_cp', return_value=False)
def test_fallback_to_shutil_copy_from_cp_failure(
    mock_copy_tree_cp,
    mock_copy_tree_shutil,
    copy_tree_paths: CopyTreePathConfig,
    root_logger: tmt.log.Logger,
):
    """Test fallback to shutil.copytree when _copy_tree_cp fails."""
    source_dir, dest_dir, _ = copy_tree_paths
    tmt.utils.filesystem.copy_tree(source_dir, dest_dir, root_logger)

    mock_copy_tree_cp.assert_called_once_with(source_dir, dest_dir, root_logger)
    mock_copy_tree_shutil.assert_called_once_with(source_dir, dest_dir, root_logger)

    # Verify files were copied using the fallback approach (shutil.copytree)
    for file_path in _EXPECTED_TEST_FILES:
        assert (dest_dir / file_path).exists(), f"Missing file: {file_path}"


def test_metadata_cp_reflink(copy_tree_paths: CopyTreePathConfig, root_logger: tmt.log.Logger):
    """Test metadata preservation with cp --reflink=auto strategy."""
    source_dir, dest_dir, _ = copy_tree_paths
    timestamp = time.time() - 3600  # One hour ago

    test_file = _setup_metadata_test_item(
        source_dir, "meta_file.txt", is_dir=False, mode=0o640, atime=timestamp, mtime=timestamp
    )
    test_dir = _setup_metadata_test_item(
        source_dir, "meta_dir", is_dir=True, mode=0o750, atime=timestamp, mtime=timestamp
    )

    tmt.utils.filesystem.copy_tree(source_dir, dest_dir, root_logger)

    _run_metadata_test_for_item(dest_dir, test_file)
    _run_metadata_test_for_item(dest_dir, test_dir)


@mock.patch('tmt.utils.filesystem._copy_tree_shutil', wraps=tmt.utils.filesystem._copy_tree_shutil)
@mock.patch('tmt.utils.filesystem._copy_tree_cp', return_value=False)
def test_metadata_preservation_on_cp_failure_fallback_to_shutil(
    mock_copy_tree_cp,
    mock_copy_tree_shutil,
    copy_tree_paths: CopyTreePathConfig,
    root_logger: tmt.log.Logger,
):
    """Test metadata preservation by shutil.copytree when cp command fails."""
    source_dir, dest_dir, _ = copy_tree_paths
    timestamp = time.time() - 7200  # Two hours ago

    test_file = _setup_metadata_test_item(
        source_dir,
        "meta_file_shutil.txt",
        is_dir=False,
        mode=0o400,
        atime=timestamp,
        mtime=timestamp,
    )
    test_dir = _setup_metadata_test_item(
        source_dir, "meta_dir_shutil", is_dir=True, mode=0o500, atime=timestamp, mtime=timestamp
    )

    tmt.utils.filesystem.copy_tree(source_dir, dest_dir, root_logger)

    mock_copy_tree_cp.assert_called_once_with(source_dir, dest_dir, root_logger)
    mock_copy_tree_shutil.assert_called_once_with(source_dir, dest_dir, root_logger)
    _run_metadata_test_for_item(dest_dir, test_file)
    _run_metadata_test_for_item(dest_dir, test_dir)


@mock.patch(
    'tmt.utils.filesystem._copy_tree_shutil',
    side_effect=OSError("Simulated shutil.copytree failure"),
)
@mock.patch('tmt.utils.filesystem._copy_tree_cp', return_value=False)
def test_all_strategies_fail(
    mock_copy_tree_cp,
    mock_copy_tree_shutil,
    copy_tree_paths: CopyTreePathConfig,
    root_logger: tmt.log.Logger,
):
    """Test GeneralError is raised when all copy strategies fail."""
    source_dir, dest_dir, _ = copy_tree_paths
    with pytest.raises(tmt.utils.GeneralError):
        tmt.utils.filesystem.copy_tree(source_dir, dest_dir, root_logger)

    mock_copy_tree_cp.assert_called_once()
    mock_copy_tree_shutil.assert_called_once()


def test_copy_to_existing_destination(
    copy_tree_paths: CopyTreePathConfig, root_logger: tmt.log.Logger
):
    """Test copying into a destination directory that already contains files."""
    source_dir, dest_dir, symlinks_supported = copy_tree_paths

    # Create some pre-existing items in the destination
    (dest_dir / "existing_file.txt").write_text("pre-existing content")
    (dest_dir / "subdir").mkdir(exist_ok=True)
    (dest_dir / "subdir" / "existing_in_subdir.txt").write_text("pre-existing in subdir")
    (dest_dir / "file1.txt").write_text("old file1 content")

    tmt.utils.filesystem.copy_tree(source_dir, dest_dir, root_logger)

    # Check that source files were copied and overwrite conflicting ones
    assert (dest_dir / "file1.txt").read_text() == _EXPECTED_TEST_FILES["file1.txt"]
    # Check that pre-existing non-conflicting files are still there
    assert (dest_dir / "existing_file.txt").read_text() == "pre-existing content"
    assert (dest_dir / "subdir" / "existing_in_subdir.txt").read_text() == "pre-existing in subdir"

    # Check symlink if supported
    if symlinks_supported:
        assert Path.is_symlink(dest_dir / "symlink.txt")
