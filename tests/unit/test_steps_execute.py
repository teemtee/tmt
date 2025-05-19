import os
import shutil
import tempfile
from unittest.mock import MagicMock, PropertyMock, patch

from tmt.steps.execute import ExecutePlugin, Script, ScriptTemplate
from tmt.steps.provision import Guest, GuestData, GuestSsh
from tmt.utils import Command, Path


class TestScript:
    """Test Script class functionality"""

    def setup_method(self):
        """Set up test environment"""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.mock_scripts_dir = self.temp_dir / 'scripts'
        self.mock_scripts_dir.mkdir()
        self.script_content = "#!/bin/bash\\necho 'Hello World'\\n"
        self.script_name = 'test_script.sh'
        (self.mock_scripts_dir / self.script_name).write_text(self.script_content)

    def teardown_method(self):
        """Clean up after tests"""
        shutil.rmtree(self.temp_dir)

    def test_script_copy_into(self):
        """Test Script.copy_into method"""
        with patch('tmt.steps.execute.SCRIPTS_SRC_DIR', self.mock_scripts_dir):
            script = Script(
                source_filename=self.script_name,
                destination_path=None,
                aliases=[],
                related_variables=[],
                enabled=lambda _: True,
            )
            dest_dir = self.temp_dir / 'dest'
            dest_dir.mkdir()
            dest_path = dest_dir / self.script_name
            returned_path = script.copy_into(dest_path)
            assert returned_path is None
            assert dest_path.exists()
            assert dest_path.read_text() == self.script_content


class TestScriptTemplate:
    """Test ScriptTemplate class functionality"""

    def setup_method(self):
        """Set up test environment"""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.template_content = "#!/bin/bash\\necho '{{ message }}'\\n"
        self.rendered_content = "#!/bin/bash\\necho 'Hello'\\n"
        # ScriptTemplate internally appends .j2 to source_filename to find the template
        self.template_base_name = 'test_template.sh'
        self.template_file_name = f"{self.template_base_name}.j2"  # File on disk must have .j2
        self.mock_template_source_dir = self.temp_dir / 'templates'
        self.mock_template_source_dir.mkdir()
        (self.mock_template_source_dir / self.template_file_name).write_text(self.template_content)

    def teardown_method(self):
        """Clean up after tests"""
        shutil.rmtree(self.temp_dir)

    def test_script_template_copy_into(self):
        """Test ScriptTemplate.copy_into method"""
        with patch('tmt.steps.execute.SCRIPTS_SRC_DIR', self.mock_template_source_dir):
            script_template = ScriptTemplate(
                source_filename=self.template_base_name,  # Pass base name, .j2 is added internally
                destination_path=None,
                aliases=[],
                related_variables=[],
                enabled=lambda _: True,
                context={'message': 'Hello'},
            )
            # Use the context manager to ensure _rendered_script_path is set and cleaned up
            with script_template:
                # Verify that the rendered_source_path (which is _rendered_script_path) was created
                assert script_template._rendered_script_path is not None
                assert script_template._rendered_script_path.exists()
                assert script_template._rendered_script_path.read_text() == self.rendered_content

                dest_dir = self.temp_dir / 'dest'
                dest_dir.mkdir()
                # Destination name should be based on the original source_filename (without .j2)
                dest_path = dest_dir / self.template_base_name

                returned_path = script_template.copy_into(dest_path)

                # ScriptTemplate.copy_into returns the path to the rendered template it copied
                assert returned_path == script_template._rendered_script_path
                assert dest_path.exists()
                assert dest_path.read_text() == self.rendered_content

            # After exiting 'with script_template', _rendered_script_path should be cleaned up
            assert (
                script_template._rendered_script_path is None
                or not script_template._rendered_script_path.exists()
            )


class TestExecutePlugin:
    """Test ExecutePlugin script handling functionality"""

    def setup_method(self):
        """Set up test environment"""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.actual_mock_scripts_dir = self.temp_dir / 'actual_mock_scripts'
        self.actual_mock_scripts_dir.mkdir()
        self.script1_content = "#!/bin/bash\\necho 'Script 1'\\n"
        self.script1_name = 'script1.sh'
        (self.actual_mock_scripts_dir / self.script1_name).write_text(self.script1_content)
        self.script2_content = "#!/bin/bash\\necho 'Script 2'\\n"
        self.script2_name = 'script2.sh'
        (self.actual_mock_scripts_dir / self.script2_name).write_text(self.script2_content)

    def teardown_method(self):
        """Clean up after tests"""
        shutil.rmtree(self.temp_dir)

    @patch('shutil.rmtree')  # Patch to prevent cleanup of staging_root during test
    @patch('tmt.steps.execute.SCRIPTS_SRC_DIR')
    def test_prepare_scripts_staging(
        self, mock_global_scripts_src_dir_object, mock_shutil_rmtree
    ):  # Added mock_shutil_rmtree
        """Test prepare_scripts method creates staging directory correctly"""
        mock_global_scripts_src_dir_object.__truediv__.side_effect = (
            lambda filename: self.actual_mock_scripts_dir / filename
        )
        mock_global_scripts_src_dir_object.exists.return_value = True
        mock_global_scripts_src_dir_object.__fspath__.return_value = str(
            self.actual_mock_scripts_dir
        )

        mock_plan = MagicMock()
        mock_plan.workdir = self.temp_dir / 'workdir'
        mock_plan.workdir.mkdir(parents=True, exist_ok=True)
        mock_logger = MagicMock()
        mock_step = MagicMock()
        mock_step.plan = mock_plan
        mock_step.name = "test-execute-step"
        mock_step.framework = None

        from tmt.steps.execute import ExecuteStepData

        data = ExecuteStepData(how='internal', name='test-execute-data', order=50)

        execute_plugin = ExecutePlugin(step=mock_step, data=data, logger=mock_logger)
        script1_dest_path_on_guest = Path('/opt/special/script1.sh')
        script2_alias = 's2_alias'
        script1 = Script(
            source_filename=self.script1_name,
            destination_path=script1_dest_path_on_guest,
            aliases=[],
            related_variables=[],
            enabled=lambda _: True,
        )
        script2 = Script(
            source_filename=self.script2_name,
            destination_path=None,
            aliases=[script2_alias],
            related_variables=[],
            enabled=lambda _: True,
        )
        execute_plugin.scripts = [script1, script2]
        mock_guest = MagicMock(spec=Guest)
        mock_guest.scripts_path = Path('/opt/tmt/scripts')
        mock_guest.facts = MagicMock()
        mock_guest.facts.is_superuser = False
        mock_guest.push = MagicMock()

        execute_plugin.prepare_scripts(mock_guest)

        # --- Assertions ---
        mock_guest.push.assert_called_once()

        # Assert that cleanup was attempted on a path
        mock_shutil_rmtree.assert_called_once()
        assert isinstance(mock_shutil_rmtree.call_args[0][0], Path), (
            "shutil.rmtree was not called with a Path object"
        )

        actual_kwargs = mock_guest.push.call_args.kwargs
        assert 'source' in actual_kwargs, (
            "Call to guest.push did not include 'source' keyword argument."
        )

        pushed_source_object = actual_kwargs['source']

        # Print for debugging (can be removed once test passes)
        print(f"DEBUG: Type of pushed_source_object: {type(pushed_source_object)}")
        print(f"DEBUG: Value of pushed_source_object: '{pushed_source_object}'")
        print(f"DEBUG: String representation: '{pushed_source_object!s}'")

        assert isinstance(pushed_source_object, Path), (
            f"Expected 'source' argument to be a Path object, got {type(pushed_source_object)}"
        )

        # Check that the source dir (pushed_source_object) still exists and has the expected name
        # This should now pass as shutil.rmtree is mocked.
        assert pushed_source_object.is_dir(), (
            f"Pushed source path '{pushed_source_object}' is not a directory."
        )
        assert pushed_source_object.name.startswith('tmt-scripts-staging-'), (
            f"Pushed src dir name '{pushed_source_object.name}' does not have the expected prefix."
        )

        # The Path object passed to push should be constructed from a string with a trailing slash
        # in the main code as Path(f"{staging_root}/"), but Path objects don't preserve
        # trailing slashes in their string representation.
        # We've already verified it's a directory above, which is the important part.
        pushed_source_path_str = str(pushed_source_object)
        assert pushed_source_object.is_dir(), (
            f"Pushed source path '{pushed_source_path_str}' should be a directory."
        )

        # pushed_source_object already represents the directory with
        # the trailing slash context if applicable from Path()
        pushed_source_staging_dir = pushed_source_object

        assert actual_kwargs['destination'] == Path('/')
        expected_script1_in_staging = pushed_source_staging_dir / str(
            script1_dest_path_on_guest
        ).lstrip('/')
        assert expected_script1_in_staging.exists(), (
            f"Script1 not found at {expected_script1_in_staging}"
        )
        assert expected_script1_in_staging.read_text() == self.script1_content
        expected_script2_in_staging = (
            pushed_source_staging_dir
            / str(mock_guest.scripts_path).lstrip('/')
            / self.script2_name
        )
        assert expected_script2_in_staging.exists(), (
            f"Script2 not found at {expected_script2_in_staging}"
        )
        assert expected_script2_in_staging.read_text() == self.script2_content
        expected_alias_in_staging = (
            pushed_source_staging_dir / str(mock_guest.scripts_path).lstrip('/') / script2_alias
        )
        assert expected_alias_in_staging.is_symlink(), (
            f"Alias not found or not a symlink at {expected_alias_in_staging}"
        )
        link_target_on_fs = os.readlink(expected_alias_in_staging)
        expected_target_in_staging = str(
            Path(expected_script2_in_staging).relative_to(expected_alias_in_staging.parent)
        )
        assert link_target_on_fs == expected_target_in_staging
        assert '--links' in actual_kwargs['options']
        assert '--chmod=755' in actual_kwargs['options']
        assert '-a' in actual_kwargs['options']


class TestRsyncHandling:
    """Test rsync path handling in push method"""

    def setup_method(self):
        """Set up test environment"""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.source_dir = self.temp_dir / 'source'
        self.source_dir.mkdir()
        (self.source_dir / 'file1.txt').write_text("Content 1")
        subdir = self.source_dir / 'subdir'
        subdir.mkdir()
        (subdir / 'file2.txt').write_text("Content 2")

    def teardown_method(self):
        """Clean up after tests"""
        shutil.rmtree(self.temp_dir)

    @patch('tmt.steps.provision.GuestSsh._run_guest_command')
    def test_push_directory_trailing_slash(self, mock_run_command):
        """Test push method adds trailing slash to source directory"""
        mock_step = MagicMock()
        mock_plan_workdir = self.temp_dir / "plan_workdir"
        mock_plan_workdir.mkdir(exist_ok=True)
        mock_step.plan = MagicMock()
        mock_step.plan.workdir = mock_plan_workdir
        mock_step.plan.safe_name = (
            "mock_plan"  # GuestSsh might use this for logging if source is None
        )

        # Corrected: Removed logger from GuestData init
        guest_data = GuestData(primary_address='dummy')
        guest = GuestSsh(logger=MagicMock(), data=guest_data, name='test', parent=mock_step)
        guest._ssh_guest = 'test@localhost'  # Ensure this is set before push is called
        with patch.object(
            GuestSsh, '_ssh_command', new_callable=PropertyMock
        ) as mock_ssh_cmd_prop:
            mock_ssh_cmd_prop.return_value = Command('ssh', '-o', 'BatchMode=yes')
            guest.push(source=self.source_dir, destination=Path('/dest'))
            mock_run_command.assert_called_once()
            called_command_obj = mock_run_command.call_args[0][0]
            cmd_parts = called_command_obj.to_popen()
            source_arg = None
            # Heuristic to find rsync source argument: it's before the remote destination
            for i in range(len(cmd_parts) - 1):
                # A basic check for remote destination format: user@host:path or host:path
                is_destination_like = ':' in cmd_parts[i + 1] and (
                    '@' in cmd_parts[i + 1] or not os.path.isabs(cmd_parts[i + 1])  # noqa: TID251
                )
                if is_destination_like:
                    potential_source = cmd_parts[i]
                    # Ensure it's not an option like '-e' and matches expected source
                    if not potential_source.startswith('-') and str(
                        self.source_dir
                    ) == potential_source.rstrip('/'):
                        source_arg = potential_source
                        break

            # Fallback if the above isn't robust enough for all cmd structures
            if source_arg is None:
                for part in cmd_parts:
                    # Compare full path string to avoid partial matches in filenames/paths
                    if str(self.source_dir) == part.rstrip('/'):
                        source_arg = part
                        break
            assert source_arg is not None, (
                f"Source argument not found or not matching"
                f" {self.source_dir}' in rsync command: {cmd_parts}"
            )
            assert source_arg.endswith('/'), (
                f"Source path '{source_arg}' should end with '/' to copy directory contents"
            )
