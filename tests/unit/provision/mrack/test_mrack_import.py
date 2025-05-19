import logging
import sys
from unittest import mock

import pytest

# Import tmt.utils first to ensure ProvisionError is available
from tmt.utils import ProvisionError

# Create mock for the real mrack module before importing our module
mock_mrack = mock.MagicMock()
mock_mrack.errors = mock.MagicMock()
mock_mrack.errors.MrackError = Exception
mock_mrack.errors.ProvisioningError = Exception
mock_mrack.errors.ConfigError = Exception
mock_mrack.errors.NotAuthenticatedError = Exception
mock_mrack.context = mock.MagicMock()
mock_mrack.context.global_context = mock.MagicMock()

# Add the mock to sys.modules so imports will return our mock
sys.modules['mrack'] = mock_mrack
sys.modules['mrack.errors'] = mock_mrack.errors
sys.modules['mrack.providers'] = mock.MagicMock()
sys.modules['mrack.providers.beaker'] = mock.MagicMock()
sys.modules['mrack.transformers.beaker'] = mock.MagicMock()
sys.modules['mrack.context'] = mock_mrack.context

# Patch the FileHandler before importing mrack to avoid file creation during tests
original_file_handler = logging.FileHandler
logging.FileHandler = mock.MagicMock()

# Import the module under test after we've set up the mocks
from tmt.steps.provision import mrack  # noqa: E402

# Restore original FileHandler after import
logging.FileHandler = original_file_handler


@pytest.fixture
def reset_mrack_state():
    """Reset mrack's global state before each test"""
    # Store original state
    original_imported = mrack._MRACK_IMPORTED
    original_args = mrack._MRACK_IMPORT_ARGS
    original_version = mrack.MRACK_VERSION

    # Reset state for test
    mrack._MRACK_IMPORTED = False
    mrack._MRACK_IMPORT_ARGS = None
    mrack.MRACK_VERSION = None
    mrack.mrack = None
    mrack.ProvisioningError = None
    mrack.NotAuthenticatedError = None

    yield

    # Restore original state after test
    mrack._MRACK_IMPORTED = original_imported
    mrack._MRACK_IMPORT_ARGS = original_args
    mrack.MRACK_VERSION = original_version


def test_ensure_mrack_imported_decorator(reset_mrack_state):
    """Test that the decorator triggers import when needed"""
    with mock.patch('tmt.steps.provision.mrack.import_and_load_mrack_deps') as mock_import:
        # Set up import args
        logger = mock.MagicMock()
        mrack._MRACK_IMPORT_ARGS = ('/tmp/workdir', 'test', logger)

        # Create a decorated function
        @mrack.ensure_mrack_imported
        def test_function():
            return "function called"

        # Call the function, which should trigger the import
        result = test_function()

        # Verify import was called
        mock_import.assert_called_once_with('/tmp/workdir', 'test', logger)
        assert result == "function called"


def test_ensure_mrack_imported_only_imports_once(reset_mrack_state):
    """Test that the decorator only imports mrack once"""
    with mock.patch('tmt.steps.provision.mrack.import_and_load_mrack_deps') as mock_import:
        # Set up import args
        logger = mock.MagicMock()
        mrack._MRACK_IMPORT_ARGS = ('/tmp/workdir', 'test', logger)

        # Create a decorated function
        @mrack.ensure_mrack_imported
        def test_function():
            return "function called"

        # First call should trigger import
        test_function()
        mock_import.assert_called_once()

        # Set the imported flag
        mrack._MRACK_IMPORTED = True

        # Second call should not trigger import again
        mock_import.reset_mock()
        test_function()
        mock_import.assert_not_called()


def test_import_and_load_mrack_deps(reset_mrack_state):
    """Test that import_and_load_mrack_deps properly stores args and imports modules"""
    # Use a single with statement with multiple contexts
    with (
        mock.patch('importlib.metadata.version', return_value='1.22.0'),
        mock.patch('logging.FileHandler'),
        mock.patch('tmt.steps.provision.mrack.importlib.import_module', return_value=mock_mrack),
    ):
        # Call the import function
        logger = mock.MagicMock()
        mrack.import_and_load_mrack_deps('/tmp/workdir', 'test', logger)

        # Verify the global variables are set
        assert mrack._MRACK_IMPORTED is True
        assert mrack.MRACK_VERSION == '1.22.0'
        assert mrack.mrack is not None


def test_mrack_constructs_ks_pre(reset_mrack_state):
    """Test that mrack_constructs_ks_pre triggers the import if needed"""
    # Set up import args but don't import yet
    logger = mock.MagicMock()
    mrack._MRACK_IMPORT_ARGS = ('/tmp/workdir', 'test', logger)

    with mock.patch('tmt.steps.provision.mrack.import_and_load_mrack_deps') as mock_import:
        # Make sure import_and_load_mrack_deps sets MRACK_VERSION
        def side_effect(*args, **kwargs):
            mrack.MRACK_VERSION = '1.22.0'
            mrack._MRACK_IMPORTED = True

        mock_import.side_effect = side_effect

        # This should trigger the import
        result = mrack.mrack_constructs_ks_pre()

        # Verify import was called
        mock_import.assert_called_once_with('/tmp/workdir', 'test', logger)
        assert result is True  # 1.22.0 >= 1.21.0


def test_property_decorator():
    """Test that property decorators work correctly with ensure_mrack_imported"""
    # Set up import args
    logger = mock.MagicMock()
    mrack._MRACK_IMPORT_ARGS = ('/tmp/workdir', 'test', logger)
    mrack._MRACK_IMPORTED = False

    # Create a class with a decorated property that mimics the pattern we use
    class TestClass:
        def _get_value(self):
            return "property value"

        # Use the same pattern as in the fixed code
        value = property(mrack.ensure_mrack_imported(_get_value))

    # Create an instance
    instance = TestClass()

    # Patch the import function to track calls
    with mock.patch('tmt.steps.provision.mrack.import_and_load_mrack_deps') as mock_import:
        # Access the property - this should trigger the decorator
        result = instance.value

        # Verify import was triggered
        mock_import.assert_called_once_with('/tmp/workdir', 'test', logger)
        assert result == "property value"


def test_handling_missing_mrack(reset_mrack_state):
    """Test handling when mrack import raises ImportError"""
    # Set up arguments for import
    logger = mock.MagicMock()
    mrack._MRACK_IMPORT_ARGS = ('/tmp/workdir', 'test', logger)
    mrack._MRACK_IMPORTED = False

    # Create a decorated function
    @mrack.ensure_mrack_imported
    def test_function():
        return "function called"

    # Mock import_and_load_mrack_deps to raise ProvisionError and capture the expected exception
    with (
        mock.patch(
            'tmt.steps.provision.mrack.import_and_load_mrack_deps',
            side_effect=ProvisionError(
                "Install 'tmt+provision-beaker' to provision using this method."
            ),
        ),
        pytest.raises(ProvisionError),
    ):
        test_function()
