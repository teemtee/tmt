import tempfile
from unittest import TestCase, mock

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

    # We've removed the symlinks parameter, so this test is no longer needed

    @mock.patch('subprocess.run')
    def test_reflink_copy(self, mock_run):
        """Test that reflink copy is attempted first"""
        mock_run.return_value = mock.Mock(returncode=0)

        tmt.utils.filesystem.copy_tree(self.source_dir, self.dest_dir, self.logger)

        # Verify cp with reflink was called
        assert mock_run.call_count == 1
        args, kwargs = mock_run.call_args
        cp_args = args[0]
        assert '--reflink=auto' in cp_args

    @mock.patch('subprocess.run')
    def test_fallback_to_hardlink(self, mock_run):
        """Test fallback to hardlink strategy when reflink fails"""
        # Make subprocess.run raise an exception to trigger fallback
        mock_run.side_effect = Exception("reflink not supported")

        # Execute the function and check that it doesn't crash
        tmt.utils.filesystem.copy_tree(self.source_dir, self.dest_dir, self.logger)

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
