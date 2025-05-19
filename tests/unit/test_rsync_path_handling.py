import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from tmt.utils import Command, Path


class TestRsyncPathHandling(unittest.TestCase):
    """
    Test suite for verifying rsync path handling, especially trailing slashes
    behavior in tmt push operations. This specifically tests the fix for PR #3669.
    """

    def setUp(self):
        """Set up test environment"""
        # Create a temporary test directory
        self.test_dir = Path(tempfile.mkdtemp())

        # Create source directories and files for testing
        self.source_dir = self.test_dir / 'source'
        self.source_dir.mkdir()

        # Create a file in the source directory
        self.test_file = self.source_dir / 'test_file.txt'
        with open(self.test_file, 'w') as f:
            f.write('Test content')

        # Create a subdirectory with a file
        self.sub_dir = self.source_dir / 'subdir'
        self.sub_dir.mkdir()
        self.sub_file = self.sub_dir / 'sub_file.txt'
        with open(self.sub_file, 'w') as f:
            f.write('Subdirectory test content')

    def tearDown(self):
        """Clean up test environment"""
        shutil.rmtree(self.test_dir)

    @patch('tmt.steps.provision.GuestSsh._run_guest_command')
    def test_directory_trailing_slash(self, mock_run_command):
        """
        Test that a trailing slash is added to directory sources to ensure
        rsync copies contents rather than the directory itself.
        """
        # Create mock objects needed for the test
        mock_step = MagicMock()
        mock_plan = MagicMock()
        mock_step.plan = mock_plan
        mock_step.plan.workdir = self.test_dir

        # Create a mock guest
        from tmt.steps.provision import GuestData, GuestSsh

        mock_guest_data = GuestData(primary_address='test-host')
        guest = GuestSsh(
            logger=MagicMock(), data=mock_guest_data, name='test-guest', parent=mock_step
        )

        # Mock the ssh command property
        guest._ssh_guest = 'user@test-host'
        type(guest)._ssh_command = MagicMock(return_value=Command('ssh'))

        # Define a custom command extraction function since we can't index Command objects
        def extract_source_from_command(cmd_obj):
            # The command should be something like:
            # rsync [options] /path/to/source/ user@test-host:/destination/
            # We need to extract the source path
            cmd_str = str(cmd_obj)
            parts = cmd_str.split()

            # Find the part that matches our source directory
            for part in parts:
                if str(self.source_dir) in part:
                    return part
            return None

        # Test case 1: Push source without trailing slash
        guest.push(source=self.source_dir, destination=Path('/dest'))

        # Check if _run_guest_command was called
        mock_run_command.assert_called_once()

        # Extract the command that was used
        command = mock_run_command.call_args[0][0]
        source_arg = extract_source_from_command(command)

        # Verify source has trailing slash (synchronize directory contents)
        assert source_arg is not None
        assert source_arg.endswith('/'), f"Source path '{source_arg}' should end with '/'"

        # Reset mock for next test
        mock_run_command.reset_mock()

        # Test case 2: Push source with explicit trailing slash
        source_with_slash = Path(f"{self.source_dir}/")
        guest.push(source=source_with_slash, destination=Path('/dest'))

        # Check command was called again
        mock_run_command.assert_called_once()

        # Extract command and source
        command = mock_run_command.call_args[0][0]
        source_arg = extract_source_from_command(command)

        # Verify source still has trailing slash
        assert source_arg is not None
        assert source_arg.endswith('/'), f"'{source_arg}' should maintain trailing slash"


if __name__ == '__main__':
    unittest.main()
