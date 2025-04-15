import subprocess
import tempfile
from unittest import TestCase, mock

import filelock

import tmt.log
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
            Path.symlink_to(self.source_dir / "file1.txt", self.source_dir / "symlink.txt")
        except (OSError, NotImplementedError):
            self.symlinks_supported = False
        else:
            self.symlinks_supported = True

    def tearDown(self):
        import shutil

        shutil.rmtree(self.temp_dir)

    def test_copy_tree_basic(self):
        """Test basic copy operation with default parameters"""
        tmt.utils.filesystem.copy_tree(self.source_dir, self.dest_dir, self.logger, self.temp_dir)

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

    # We've removed the symlinks parameter, so this test is no longer needed

    @mock.patch('subprocess.run')
    def test_reflink_copy(self, mock_run):
        """Test that reflink copy is attempted first"""
        mock_run.return_value = mock.Mock(returncode=0)

        tmt.utils.filesystem.copy_tree(self.source_dir, self.dest_dir, self.logger, self.temp_dir)

        # Verify cp with reflink was called
        assert mock_run.call_count == 1
        args, kwargs = mock_run.call_args
        cp_args = args[0]
        assert '--reflink=auto' in cp_args

    @mock.patch('subprocess.run')
    def test_fallback_error_handling(self, mock_run):
        """Test fallback to hardlink strategy when cp command fails"""
        # Make subprocess.run raise CalledProcessError to trigger fallback
        mock_run.side_effect = subprocess.CalledProcessError(
            cmd=['cp', '-a', '--reflink=auto', f"{self.source_dir}/./", str(self.dest_dir)],
            returncode=1,
        )

        # Execute the function and check that it doesn't crash
        tmt.utils.filesystem.copy_tree(self.source_dir, self.dest_dir, self.logger, self.temp_dir)

        # Verify files were copied using the fallback approach
        assert (self.dest_dir / ".fmf" / "version").exists()
        assert (self.dest_dir / "file1.txt").exists()
        assert (self.dest_dir / "file2.txt").exists()
        assert (self.dest_dir / "subdir" / "file3.txt").exists()

    def test_relative_path_to_cache_key(self):
        """Test the path to cache key conversion function"""
        path1 = Path("some/path/to/file.txt")
        path2 = Path("different/path.txt")

        key1 = tmt.utils.filesystem.relative_path_to_cache_key(path1)
        key2 = tmt.utils.filesystem.relative_path_to_cache_key(path2)

        # Keys should be hexadecimal strings
        assert all(c in "0123456789abcdef" for c in key1)

        # Different paths should produce different keys
        assert key1 != key2

        # Same path should produce the same key
        key1_again = tmt.utils.filesystem.relative_path_to_cache_key(path1)
        assert key1 == key1_again

    @mock.patch('tmt.utils.filesystem.filelock.FileLock')
    @mock.patch('subprocess.run')
    @mock.patch('shutil.copy2')  # Mock copy2 to check if it's called on timeout
    def test_lock_timeout(self, mock_copy2, mock_run, mock_filelock_class):
        """Test fallback to regular copy when filelock times out"""

        # Make subprocess.run raise an exception to trigger fallback
        mock_run.side_effect = subprocess.CalledProcessError(cmd=['cp'], returncode=1)

        # Configure the mock FileLock instance to raise Timeout on acquire
        mock_lock_instance = mock.Mock()
        mock_lock_instance.acquire.side_effect = filelock.Timeout("Lock timed out")
        mock_filelock_class.return_value = mock_lock_instance

        tmt.utils.filesystem.copy_tree(self.source_dir, self.dest_dir, self.logger, self.temp_dir)

        # Verify that acquire was called
        mock_lock_instance.acquire.assert_called()
        # Verify that shutil.copy2 was called for the files due to timeout
        # Check calls for file1.txt, file2.txt, subdir/file3.txt
        expected_copy_calls = [
            mock.call(self.source_dir / "file1.txt", self.dest_dir / "file1.txt"),
            mock.call(self.source_dir / "file2.txt", self.dest_dir / "file2.txt"),
            mock.call(
                self.source_dir / "subdir" / "file3.txt", self.dest_dir / "subdir" / "file3.txt"
            ),
        ]
        # Allow for potential extra calls if .fmf/version is handled as a file
        assert mock_copy2.call_count >= 3
        mock_copy2.assert_has_calls(expected_copy_calls, any_order=True)

    @mock.patch('tmt.utils.filesystem.filelock.FileLock')
    @mock.patch('subprocess.run')
    def test_lock_acquired(self, mock_run, mock_filelock_class):
        """Test that filelock is acquired during fallback"""
        if filelock is None:
            self.skipTest("filelock library is not installed.")

        mock_run.side_effect = subprocess.CalledProcessError(cmd=['cp'], returncode=1)

        # Configure the mock FileLock class to return a mock instance
        mock_lock_instance = mock.Mock()
        mock_filelock_class.return_value = mock_lock_instance

        # Configure the acquire method to return a MagicMock that can act as a context manager
        mock_context_manager = mock.MagicMock()
        mock_lock_instance.acquire.return_value = mock_context_manager

        # Configure the __enter__ method to return the MagicMock itself
        mock_context_manager.__enter__.return_value = mock_context_manager
        # Configure the __exit__ method (important for the 'with' statement)
        mock_context_manager.__exit__.return_value = None

        tmt.utils.filesystem.copy_tree(self.source_dir, self.dest_dir, self.logger, self.temp_dir)

        # Verify acquire was called for each file being processed in fallback
        # Expect calls for .fmf/version, file1.txt, file2.txt, subdir/file3.txt
        assert mock_lock_instance.acquire.call_count >= 4
        # Verify the context manager methods were called
        assert mock_context_manager.__enter__.call_count >= 4
        assert mock_context_manager.__exit__.call_count >= 4

    @mock.patch('tmt.utils.filesystem.filelock.FileLock')
    @mock.patch('subprocess.run')
    @mock.patch('os.link')
    @mock.patch('tmt._compat.pathlib.Path.rename')
    @mock.patch('shutil.copy2')  # Mock copy2 to ensure it's called
    def test_cache_update_atomicity(
        self, mock_copy2, mock_rename, mock_os_link, mock_run, mock_filelock_class
    ):
        """Test atomic cache update using temporary file and rename"""
        if filelock is None:
            self.skipTest("filelock library is not installed.")

        mock_run.side_effect = subprocess.CalledProcessError(cmd=['cp'], returncode=1)

        # Setup mock lock
        mock_lock_instance = mock.Mock()
        mock_filelock_class.return_value = mock_lock_instance
        # Use MagicMock for the context manager returned by acquire
        mock_context_manager = mock.MagicMock()
        mock_lock_instance.acquire.return_value = mock_context_manager
        # Configure the context manager methods
        mock_context_manager.__enter__.return_value = mock_context_manager
        mock_context_manager.__exit__.return_value = None

        # Mock os.link to simulate linking dst_item to temp cache path
        # We need to track calls carefully
        link_calls = []

        def os_link_side_effect(src, dst):
            link_calls.append((src, dst))
            # Simulate potential error during linking to real cache path if needed
            # if 'tmp' not in str(dst): raise OSError("Cannot link")

        mock_os_link.side_effect = os_link_side_effect

        # Mock Path.rename
        rename_calls = []

        def rename_side_effect(target):
            rename_calls.append((self, target))  # self here is the Path instance

        mock_rename.side_effect = rename_side_effect

        # Ensure copy2 is called (simulating cache miss or failed hardlink)
        tmt.utils.filesystem.copy_tree(self.source_dir, self.dest_dir, self.logger, self.temp_dir)

        # Verify copy2 was called for files
        assert mock_copy2.call_count >= 3

        # Verify os.link was called to link dst_item to a temporary cache file
        # Check that at least one call has '.tmp' in the destination path
        assert any('.tmp' in str(dst) for src, dst in link_calls)

        # Verify Path.rename was called to move the temp file to the final cache path
        # Check that at least one rename call happened
        assert len(rename_calls) >= 3  # One for each file copied
        # Check that the rename target (cache_path) doesn't have '.tmp'
        assert all('.tmp' not in str(target) for _, target in rename_calls)
