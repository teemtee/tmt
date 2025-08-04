import threading
from unittest.mock import Mock, patch

import pytest

import tmt


class TestMrackThreadSafety:
    """Test thread safety of mrack provision plugin."""

    def test_multiple_beaker_api_instances_thread_safety(self, root_logger):
        """Test that multiple BeakerAPI instances can be created safely in parallel."""

        # Mock the required dependencies
        with (
            patch('tmt.steps.provision.mrack.import_and_load_mrack_deps'),
            patch('tmt.steps.provision.mrack.BeakerAPI') as mock_beaker_api,
        ):
            # Mock BeakerAPI to avoid actual initialization
            mock_api_instance = Mock()
            mock_beaker_api.return_value = mock_api_instance

            from tmt.steps.provision.mrack import BeakerGuestData, GuestBeaker

            # Create mock step
            mock_step = Mock()
            mock_step.workdir = "/tmp/test"
            mock_step.name = "test-provision"

            # Create sample guest data
            sample_data = BeakerGuestData(
                name="test-guest",
                role=None,
                whiteboard="Thread safety test",
                arch="x86_64",
                image="fedora-latest",
            )

            results = []
            exceptions = []

            def create_guest():
                try:
                    guest = GuestBeaker(
                        data=sample_data,
                        name="test-guest",
                        parent=mock_step,
                        logger=root_logger,
                    )
                    results.append(guest)
                except Exception as e:
                    exceptions.append(e)

            # Create multiple threads that create guests
            threads = []
            for _i in range(3):
                thread = threading.Thread(target=create_guest)
                threads.append(thread)

            # Start all threads
            for thread in threads:
                thread.start()

            # Wait for all threads to complete
            for thread in threads:
                thread.join()

            # Verify results
            assert len(exceptions) == 0, f"Exceptions occurred: {exceptions}"
            assert len(results) == 3, f"Expected 3 guests, got {len(results)}"

    def test_beaker_api_config_loading(self, root_logger):
        """Test that BeakerAPI configuration loading works correctly."""

        with (
            patch('tmt.steps.provision.mrack.import_and_load_mrack_deps'),
            patch('tmt.utils.yaml_to_dict') as mock_yaml_to_dict,
        ):
            # Mock YAML configuration data
            mock_config_data = {
                'beaker': {'url': 'http://beaker.example.com', 'username': 'testuser'}
            }
            mock_yaml_to_dict.return_value = mock_config_data

            from tmt.steps.provision.mrack import BeakerAPI, BeakerGuestData, GuestBeaker

            # Create mock guest
            mock_step = Mock()
            mock_step.workdir = "/tmp/test"
            mock_step.name = "test-provision"

            sample_data = BeakerGuestData(
                name="test-guest",
                role=None,
                whiteboard="Config test",
                arch="x86_64",
                image="fedora-latest",
            )

            guest = GuestBeaker(
                data=sample_data,
                name="test-guest",
                parent=mock_step,
                logger=root_logger,
            )

            # Test the config creation method directly
            api = BeakerAPI.__new__(BeakerAPI)
            api._guest = guest

            provider_config = api._create_provider_config(mock_config_data)

            assert 'beaker' in provider_config
            assert provider_config['beaker']['url'] == 'http://beaker.example.com'
            assert provider_config['beaker']['username'] == 'testuser'

    def test_beaker_api_missing_beaker_section(self, root_logger):
        """Test that proper error is raised when beaker section is missing."""

        from tmt.steps.provision.mrack import BeakerAPI, BeakerGuestData, GuestBeaker

        # Create mock guest
        mock_step = Mock()
        mock_step.workdir = "/tmp/test"
        mock_step.name = "test-provision"

        sample_data = BeakerGuestData(
            name="test-guest",
            role=None,
            whiteboard="Config test",
            arch="x86_64",
            image="fedora-latest",
        )

        guest = GuestBeaker.__new__(GuestBeaker)
        guest._guest = sample_data

        # Test configuration without beaker section
        api = BeakerAPI.__new__(BeakerAPI)
        api._guest = guest

        # Configuration missing beaker section
        invalid_config_data = {'aws': {'region': 'us-east-1'}}

        # Should raise error about missing beaker section
        with pytest.raises(tmt.utils.SpecificationError) as exc_info:
            api._create_provider_config(invalid_config_data)

        assert "No 'beaker' section found" in str(exc_info.value)

    def test_beaker_api_invalid_config_format(self, root_logger):
        """Test that proper error is raised when config format is invalid."""

        from tmt.steps.provision.mrack import BeakerAPI, BeakerGuestData, GuestBeaker

        # Create mock guest
        mock_step = Mock()
        mock_step.workdir = "/tmp/test"
        mock_step.name = "test-provision"

        sample_data = BeakerGuestData(
            name="test-guest",
            role=None,
            whiteboard="Config test",
            arch="x86_64",
            image="fedora-latest",
        )

        guest = GuestBeaker.__new__(GuestBeaker)
        guest._guest = sample_data

        # Test with invalid configuration format
        api = BeakerAPI.__new__(BeakerAPI)
        api._guest = guest

        # Should raise error about invalid format
        with pytest.raises(tmt.utils.SpecificationError) as exc_info:
            api._create_provider_config("invalid-string-instead-of-dict")

        assert "Invalid mrack provisioning configuration format" in str(exc_info.value)


if __name__ == "__main__":
    pytest.main([__file__])
