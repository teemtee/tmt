import os
import shutil
import stat
import tempfile
import time
from typing import Optional
from unittest import TestCase, mock

import pytest

import tmt.log
import tmt.utils
import tmt.utils.filesystem
from tmt._compat.pathlib import Path


class TestCopyTree(TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.source_dir = self.temp_dir / "source"
        self.dest_dir = self.temp_dir / "dest"
        self.source_dir.mkdir()
        self.dest_dir.mkdir()
        self.logger = tmt.log.Logger.create()

        # Create test files in source directory
        (self.source_dir / ".fmf").mkdir()
        (self.source_dir / ".fmf" / "version").write_text("1")
        (self.source_dir / "file1.txt").write_text("content1")
        (self.source_dir / "file2.txt").write_text("content2")
        (self.source_dir / "subdir").mkdir()
        (self.source_dir / "subdir" / "file3.txt").write_text("content3")

        # Create a symlink if the platform supports it
        try:
            (self.source_dir / "symlink.txt").symlink_to(self.source_dir / "file1.txt")
        except (OSError, NotImplementedError):
            self.symlinks_supported = False
        else:
            self.symlinks_supported = True

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_copy_tree_basic(self):
        """Test basic copy operation with default parameters"""
        tmt.utils.filesystem.copy_tree(self.source_dir, self.dest_dir, self.logger)

        # Check if all files were copied
        assert (self.dest_dir / ".fmf" / "version").exists()
        assert (self.dest_dir / "file1.txt").exists()
        assert (self.dest_dir / "file2.txt").exists()
        assert (self.dest_dir / "subdir" / "file3.txt").exists()

        # Check file contents
        assert (self.dest_dir / ".fmf" / "version").read_text() == "1"
        assert (self.dest_dir / "file1.txt").read_text() == "content1"
        assert (self.dest_dir / "file2.txt").read_text() == "content2"
        assert (self.dest_dir / "subdir" / "file3.txt").read_text() == "content3"

        # Check symlink if supported
        if self.symlinks_supported:
            assert Path.is_symlink(self.dest_dir / "symlink.txt")
            target = Path.readlink(self.dest_dir / "symlink.txt")
            assert Path(target).name == "file1.txt"

    def test_copy_empty_source_directory(self):
        """Test copying an empty source directory."""
        # Create an empty directory
        empty_src = self.temp_dir / "empty_src"
        empty_dst = self.temp_dir / "empty_dst"
        empty_src.mkdir()

        # Copy the empty directory
        tmt.utils.filesystem.copy_tree(empty_src, empty_dst, self.logger)

        # Verify the destination directory exists and is empty
        assert empty_dst.exists()
        assert empty_dst.is_dir()
        assert not list(empty_dst.iterdir())  # Directory is empty

    def test_deeply_nested_directories(self):
        """Test copying deeply nested directory structures."""
        # Create a deeply nested directory structure
        deep_src = self.temp_dir / "deep_src"
        deep_dst = self.temp_dir / "deep_dst"
        deep_src.mkdir()

        # Create nested structure (10 levels deep)
        current_dir = deep_src
        test_content = "test content for deep copy"

        for level in range(1, 11):
            current_dir = current_dir / f"level_{level}"
            current_dir.mkdir()

            # Add a file at each level
            test_file = current_dir / f"file_at_level_{level}.txt"
            test_file.write_text(f"{test_content} at level {level}")

            if level == 10:
                pass

        # Copy the deep directory structure
        tmt.utils.filesystem.copy_tree(deep_src, deep_dst, self.logger)

        # Check if the deepest directory and file exist in the copied structure
        assert (
            deep_dst
            / "level_1"
            / "level_2"
            / "level_3"
            / "level_4"
            / "level_5"
            / "level_6"
            / "level_7"
            / "level_8"
            / "level_9"
            / "level_10"
        ).exists()

        # Check content of a file in the deepest directory
        deepest_file = (
            deep_dst
            / "level_1"
            / "level_2"
            / "level_3"
            / "level_4"
            / "level_5"
            / "level_6"
            / "level_7"
            / "level_8"
            / "level_9"
            / "level_10"
            / "file_at_level_10.txt"
        )
        assert deepest_file.exists()
        assert deepest_file.read_text() == f"{test_content} at level 10"

    @mock.patch('os.access')
    def test_permission_error_handling(self, mock_access):
        """Test handling of permission errors during copy."""
        # Create test directory with restricted permissions
        restricted_src = self.temp_dir / "restricted_src"
        restricted_dst = self.temp_dir / "restricted_dst"
        restricted_src.mkdir()

        # Create a test file
        test_file = restricted_src / "restricted_file.txt"
        test_file.write_text("content that should be inaccessible")

        # Mock os.access to simulate permission error for all files
        mock_access.return_value = False

        # Test with both cp and shutil failing due to permissions
        with (
            mock.patch('tmt.utils.filesystem._copy_tree_cp', return_value=False),
            mock.patch(
                'tmt.utils.filesystem._copy_tree_shutil',
                side_effect=PermissionError("Simulated permission error"),
            ),
        ):
            # Use pytest.raises only around the statement that raises the exception
            with pytest.raises(tmt.utils.GeneralError) as excinfo:
                tmt.utils.filesystem.copy_tree(restricted_src, restricted_dst, self.logger)

            # Verify the error message contains information about permission error
            assert (
                "permission error" in str(excinfo.value).lower()
                or "permission" in str(excinfo.value.__cause__).lower()
            )

    def test_nonexistent_source_directory(self):
        """Test error handling when source directory doesn't exist."""
        # Create a non-existent source path
        nonexistent_src = self.temp_dir / "nonexistent_src"
        destination = self.temp_dir / "destination"

        # Attempt copy operation which should raise GeneralError
        with pytest.raises(tmt.utils.GeneralError) as excinfo:
            tmt.utils.filesystem.copy_tree(nonexistent_src, destination, self.logger)

        # Verify the error message indicates the source doesn't exist
        assert "not a directory or does not exist" in str(excinfo.value)

    def test_reflink_copy(self):
        """Test copy outcome when the 'cp' (reflink-aware) strategy is used."""
        # Note: Verifying reflink specifically without mocking is system-dependent.
        # This test primarily checks if copy succeeds when reflink is attempted.
        tmt.utils.filesystem.copy_tree(self.source_dir, self.dest_dir, self.logger)

        # Basic check that files were copied (outcome)
        assert (self.dest_dir / "file1.txt").exists()
        assert (self.dest_dir / "subdir" / "file3.txt").exists()
        if self.symlinks_supported:
            assert Path.is_symlink(self.dest_dir / "symlink.txt")

    @mock.patch(
        'tmt.utils.filesystem._copy_tree_shutil', wraps=tmt.utils.filesystem._copy_tree_shutil
    )
    @mock.patch('tmt.utils.filesystem._copy_tree_cp')
    def test_fallback_to_shutil_copy_from_cp_failure(
        self, mock_copy_tree_cp, mock_copy_tree_shutil
    ):
        """Test fallback to shutil.copytree when _copy_tree_cp fails."""
        # Make _copy_tree_cp return False to trigger fallback
        mock_copy_tree_cp.return_value = False

        # Execute the function
        tmt.utils.filesystem.copy_tree(self.source_dir, self.dest_dir, self.logger)

        # Verify _copy_tree_cp was called once
        mock_copy_tree_cp.assert_called_once_with(self.source_dir, self.dest_dir, self.logger)
        # Verify _copy_tree_shutil was called
        mock_copy_tree_shutil.assert_called_once_with(self.source_dir, self.dest_dir, self.logger)

        # Verify files were copied using the fallback approach (shutil.copytree)
        assert (self.dest_dir / ".fmf" / "version").exists()
        assert (self.dest_dir / "file1.txt").exists()
        assert (self.dest_dir / "file2.txt").exists()
        assert (self.dest_dir / "subdir" / "file3.txt").exists()

    def _assert_permissions_copied(self, src_path: Path, dest_path: Path):
        """Assert that file/directory permissions are copied."""
        src_mode = stat.S_IMODE(os.stat(src_path).st_mode)
        dest_mode = stat.S_IMODE(os.stat(dest_path).st_mode)
        assert src_mode == dest_mode, (
            f"Permission mismatch for {dest_path}. Expected {oct(src_mode)}, got {oct(dest_mode)}"
        )

    def _assert_timestamps_copied(self, src_path: Path, dest_path: Path, delta_seconds=2):
        """
        Assert that file/directory timestamps (mtime) are copied.
        atime is too unreliable to assert precisely in cross-platform unit tests.
        """
        src_stat = os.stat(src_path)
        dest_stat = os.stat(dest_path)

        assert abs(src_stat.st_mtime - dest_stat.st_mtime) <= delta_seconds, (
            f"mtime mismatch for {dest_path}. Expected {src_stat.st_mtime}, got {dest_stat.st_mtime}"  # noqa: E501
        )

    def _setup_metadata_test_item(
        self, name: str, is_dir: bool, mode: int, atime: float, mtime: float
    ):
        item_path = self.source_dir / name
        if is_dir:
            item_path.mkdir()
        else:
            item_path.write_text(f"content of {name}")
        os.chmod(item_path, mode)
        os.utime(item_path, (atime, mtime))
        return item_path

    def _run_metadata_test_for_item(self, src_item: Path, delta_seconds: Optional[int] = None):
        dest_item = self.dest_dir / src_item.name
        self._assert_permissions_copied(src_item, dest_item)
        if delta_seconds is not None:
            self._assert_timestamps_copied(src_item, dest_item, delta_seconds=delta_seconds)
        else:
            self._assert_timestamps_copied(src_item, dest_item)

    def test_metadata_cp_reflink(self):
        """Test metadata preservation with cp --reflink=auto strategy."""
        file_mode = 0o640
        dir_mode = 0o750
        timestamp = time.time() - 3600  # One hour ago

        test_file = self._setup_metadata_test_item(
            "meta_file.txt", False, file_mode, timestamp, timestamp
        )
        test_dir = self._setup_metadata_test_item("meta_dir", True, dir_mode, timestamp, timestamp)

        tmt.utils.filesystem.copy_tree(self.source_dir, self.dest_dir, self.logger)

        # permissions and mtime should be preserved.
        self._run_metadata_test_for_item(test_file)
        self._run_metadata_test_for_item(test_dir)

    @mock.patch(
        'tmt.utils.filesystem._copy_tree_shutil', wraps=tmt.utils.filesystem._copy_tree_shutil
    )
    @mock.patch('tmt.utils.filesystem._copy_tree_cp')
    def test_metadata_preservation_on_cp_failure_fallback_to_shutil(
        self, mock_copy_tree_cp, mock_copy_tree_shutil_wrapper
    ):
        """Test metadata preservation by shutil.copytree when cp command fails."""
        # Simulate _copy_tree_cp failing
        mock_copy_tree_cp.return_value = False

        file_mode = 0o400
        dir_mode = 0o500
        timestamp = time.time() - 7200

        # Clear dest_dir to ensure a clean state
        shutil.rmtree(self.dest_dir)
        self.dest_dir.mkdir()

        test_file = self._setup_metadata_test_item(
            "meta_file_shutil_fallback.txt", False, file_mode, timestamp, timestamp
        )
        test_dir = self._setup_metadata_test_item(
            "meta_dir_shutil_fallback", True, dir_mode, timestamp, timestamp
        )
        (self.source_dir / "another_file_for_shutil_fallback.txt").write_text(
            "shutil fallback test"
        )

        tmt.utils.filesystem.copy_tree(self.source_dir, self.dest_dir, self.logger)

        # Verify _copy_tree_cp was called
        mock_copy_tree_cp.assert_called_once_with(self.source_dir, self.dest_dir, self.logger)
        # Verify _copy_tree_shutil (via wrapper) was called
        mock_copy_tree_shutil_wrapper.assert_called_once_with(
            self.source_dir, self.dest_dir, self.logger
        )

        # Verify metadata preservation for the specific items by shutil.copytree
        self._run_metadata_test_for_item(test_file)
        self._run_metadata_test_for_item(test_dir)
        assert (self.dest_dir / "another_file_for_shutil_fallback.txt").exists()

    @mock.patch(
        'tmt.utils.filesystem._copy_tree_shutil', wraps=tmt.utils.filesystem._copy_tree_shutil
    )
    @mock.patch('tmt.utils.filesystem._copy_tree_cp', return_value=False)
    def test_fallback_to_shutil_copy(self, mock_copy_tree_cp, mock_copy_tree_shutil_actual):
        """Test fallback to shutil.copytree strategy when cp fails."""
        # Ensure dest_dir is clean for this test
        shutil.rmtree(self.dest_dir)
        self.dest_dir.mkdir()

        # Setup items with metadata to check shutil.copytree's preservation
        file_mode = 0o660
        dir_mode = 0o770
        timestamp = time.time() - 10800
        test_file = self._setup_metadata_test_item(
            "shutil_file.txt", False, file_mode, timestamp, timestamp
        )
        test_dir = self._setup_metadata_test_item(
            "shutil_dir", True, dir_mode, timestamp, timestamp
        )

        tmt.utils.filesystem.copy_tree(self.source_dir, self.dest_dir, self.logger)

        # Verify cp attempt failed
        mock_copy_tree_cp.assert_called_once_with(self.source_dir, self.dest_dir, self.logger)
        # Verify shutil.copytree was called
        mock_copy_tree_shutil_actual.assert_called_once_with(
            self.source_dir, self.dest_dir, self.logger
        )

        # Verify files were copied by shutil.copytree
        assert (self.dest_dir / ".fmf" / "version").exists()
        assert (self.dest_dir / "file1.txt").exists()
        assert (self.dest_dir / "shutil_file.txt").exists()
        assert (self.dest_dir / "shutil_dir").exists()

        # Verify metadata preservation by shutil.copytree (which uses copy2)
        self._run_metadata_test_for_item(test_file)
        self._run_metadata_test_for_item(test_dir)

    @mock.patch(
        'tmt.utils.filesystem._copy_tree_shutil',
        side_effect=OSError("Simulated shutil.copytree failure"),
    )
    @mock.patch('tmt.utils.filesystem._copy_tree_cp', return_value=False)
    def test_all_strategies_fail(self, mock_copy_tree_cp, mock_copy_tree_shutil_failing):
        """Test GeneralError is raised when all copy strategies fail."""
        with pytest.raises(tmt.utils.GeneralError):
            tmt.utils.filesystem.copy_tree(self.source_dir, self.dest_dir, self.logger)

        # Verify all mocks were called as expected
        mock_copy_tree_cp.assert_called_once_with(self.source_dir, self.dest_dir, self.logger)
        mock_copy_tree_shutil_failing.assert_called_once_with(
            self.source_dir, self.dest_dir, self.logger
        )

    # The test_basic_copy_metadata_preservation is no longer needed as _copy_tree_basic is removed.
    # Metadata preservation for shutil.copytree is implicitly tested in
    # test_metadata_preservation_on_cp_failure_fallback_to_shutil and test_fallback_to_shutil_copy.

    def test_copy_to_existing_destination(self):
        """Test copying into a destination directory that already contains files."""
        # Create some pre-existing items in the destination
        (self.dest_dir / "existing_file.txt").write_text("pre-existing content")
        (self.dest_dir / "subdir").mkdir(exist_ok=True)  # Ensure subdir exists
        (self.dest_dir / "subdir" / "existing_in_subdir.txt").write_text("pre-existing in subdir")
        # This file from source will conflict with a pre-existing file
        (self.dest_dir / "file1.txt").write_text("old file1 content")

        tmt.utils.filesystem.copy_tree(self.source_dir, self.dest_dir, self.logger)

        # Check that source files were copied and overwrite conflicting ones
        assert (self.dest_dir / ".fmf" / "version").read_text() == "1"
        assert (self.dest_dir / "file1.txt").read_text() == "content1"  # Should be overwritten
        assert (self.dest_dir / "file2.txt").read_text() == "content2"
        assert (self.dest_dir / "subdir" / "file3.txt").read_text() == "content3"

        # Check that pre-existing non-conflicting files are still there
        assert (self.dest_dir / "existing_file.txt").read_text() == "pre-existing content"
        assert (
            self.dest_dir / "subdir" / "existing_in_subdir.txt"
        ).read_text() == "pre-existing in subdir"

        # Check symlink if supported
        if self.symlinks_supported:
            assert Path.is_symlink(self.dest_dir / "symlink.txt")
            target = Path.readlink(self.dest_dir / "symlink.txt")
            assert Path(target).name == "file1.txt"
