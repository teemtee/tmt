#!/usr/bin/env python3

# --- Start of importlib.metadata monkeypatch ---
import importlib.metadata
import sys
import os

_original_importlib_metadata_version = importlib.metadata.version

def _mock_tmt_version(distribution_name):
    # Only mock 'tmt' if an environment variable is set,
    # to avoid interfering when tmt is properly installed.
    if distribution_name == 'tmt' and os.environ.get('TMT_MOCK_VERSION_HACK') == '1':
        print("validate_mocks.py: Mocking tmt.__version__ to '0.0.0_mock'", file=sys.stderr)
        return '0.0.0_mock'
    return _original_importlib_metadata_version(distribution_name)

# Apply the patch only if the env var is set
if os.environ.get('TMT_MOCK_VERSION_HACK') == '1':
    importlib.metadata.version = _mock_tmt_version
# --- End of importlib.metadata monkeypatch ---

import argparse
import pathlib
import logging 
import yaml
import json 

# TMT and FMF imports
import fmf.utils
import tmt.log
import tmt.utils
from tmt.utils import SpecificationError, load_schema_store

# jsonschema for validation
from jsonschema import Draft7Validator, RefResolver
from jsonschema.exceptions import ValidationError as JsonSchemaValidationError

# Logger setup
logger = logging.getLogger("validate_mocks")
tmt_logger = logging.getLogger('tmt') 

def main():
    parser = argparse.ArgumentParser(
        description="Validate mock data files against TMT schemas.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="""
Example usage:
  PYTHONPATH=/app python3 tmt/mock_data/validate_mocks.py plan.yaml tmt/mock_data/schemas/plan.mock.yaml
  TMT_MOCK_VERSION_HACK=1 PYTHONPATH=/app python3 tmt/mock_data/validate_mocks.py discover/shell.yaml tmt/mock_data/schemas/discover_shell.mock.yaml -v
"""
    )
    parser.add_argument(
        "schema_name",
        help="Base name of the schema file (e.g., plan.yaml, discover/shell.yaml)."
    )
    parser.add_argument(
        "mock_data_file",
        type=pathlib.Path,
        help="Path to the .mock.yaml file to be validated."
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable debug logging."
    )

    args = parser.parse_args()

    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=logging.WARNING, format='%(levelname)-8s %(name)s: %(message)s') 
    logger.setLevel(log_level) 

    if args.verbose:
        tmt_logger.setLevel(logging.DEBUG)
    else:
        tmt_logger.setLevel(logging.INFO)


    logger.debug(f"Schema name input: {args.schema_name}")
    logger.debug(f"Mock data file: {args.mock_data_file}")

    # --- Schema Loading ---
    schema_id_key = args.schema_name.replace('.yaml', '')
    if not schema_id_key.startswith('/schemas/'):
        schema_id_key = f"/schemas/{schema_id_key}"

    logger.info(f"Normalized schema ID for lookup: {schema_id_key}")

    schema_store = None
    target_schema_object = None
    validator = None

    try:
        logger.debug(f"Loading schema store using tmt.utils.load_schema_store()...")
        schema_store = load_schema_store()
        logger.debug("Schema store loaded successfully.")

        if schema_id_key not in schema_store:
            logger.error(f"Schema ID '{schema_id_key}' not found in the schema store.")
            available_ids = "\n".join(sorted(schema_store.keys()))
            logger.error(f"Available schema IDs:\n{available_ids}")
            sys.exit(1)

        target_schema_object = schema_store[schema_id_key]
        logger.debug(f"Target schema object for '{schema_id_key}' retrieved from store.")

        # Create a resolver aware of the whole store
        # The base_uri for the resolver should be the URI of the schema being validated.
        # Schemas in the store should have '$id' like '/schemas/plan', etc.
        # The RefResolver needs a base URI to resolve relative refs if any,
        # and the store for absolute refs like '/schemas/common'.
        # The $id of target_schema_object can serve as its base URI.
        base_uri = target_schema_object.get('$id', '') # Fallback if $id is missing in a schema
        if not base_uri:
             logger.warning(f"Schema {schema_id_key} is missing a top-level '$id'. This might affect $ref resolution if it uses relative paths.")
        
        # For jsonschema >= 3.0.0, store is a mapping from URIs to schema documents.
        # The schema_store from tmt.utils.load_schema_store() is exactly this.
        resolver = RefResolver.from_schema(target_schema_object, store=schema_store)
        validator = Draft7Validator(target_schema_object, resolver=resolver)
        logger.debug("Draft7Validator created with schema store resolver.")


    except Exception as e:
        logger.error(f"Error loading schema store or creating validator: {e}", exc_info=args.verbose)
        sys.exit(1)

    # --- Mock Data Loading ---
    if not args.mock_data_file.exists():
        logger.error(f"Mock data file '{args.mock_data_file}' not found.")
        sys.exit(1)

    try:
        with open(args.mock_data_file, 'r') as f:
            mock_data_list = yaml.safe_load(f)
    except yaml.YAMLError as e:
        logger.error(f"Error parsing YAML mock data file '{args.mock_data_file}': {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error reading mock data file '{args.mock_data_file}': {e}", exc_info=args.verbose)
        sys.exit(1)

    if mock_data_list is None: 
        logger.info(f"Mock data file '{args.mock_data_file}' is empty. Nothing to validate.")
        print("0 out of 0 mock objects validated successfully.") 
        sys.exit(0)

    if not isinstance(mock_data_list, list):
        logger.error(f"Mock data file '{args.mock_data_file}' does not contain a YAML list of objects.")
        sys.exit(1)

    logger.info(f"Loaded {len(mock_data_list)} mock objects from '{args.mock_data_file}'.")

    # --- Validation Loop ---
    successful_validations = 0
    failed_validations = 0

    for i, mock_object_data in enumerate(mock_data_list):
        mock_object_number = i + 1
        logger.debug(f"Validating mock object #{mock_object_number}...")

        try:
            validator.validate(mock_object_data) # Use the validator instance
            logger.info(f"Mock object #{mock_object_number}: Validated successfully.")
            successful_validations += 1
        except JsonSchemaValidationError as e:
            logger.error(f"Mock object #{mock_object_number}: Validation FAILED.")
            error_path = list(e.path) if e.path else ["<root>"]
            logger.error(f"  Schema Path: {'.'.join(map(str, error_path))}")
            logger.error(f"  Message: {e.message}")
            # For more verbose output of the failing instance, especially with nested structures
            if args.verbose:
                # Convert non-serializable items (like Path objects if any) to str
                failing_instance_json = json.dumps(e.instance, indent=2, ensure_ascii=False, default=str)
                logger.debug(f"  Failing instance data:\n{failing_instance_json}")
                # logger.debug(f"  Validator context: {e.context}") # Can be very verbose
            failed_validations += 1
        except Exception as e: 
            logger.error(f"Mock object #{mock_object_number}: Validation FAILED with unexpected error.")
            logger.error(f"  Error: {e}", exc_info=args.verbose)
            failed_validations += 1
            
    # --- Reporting ---
    total_objects = len(mock_data_list)
    print(f"{successful_validations} out of {total_objects} mock objects validated successfully.")

    if failed_validations > 0:
        sys.exit(1)
    else:
        sys.exit(0)

if __name__ == "__main__":
    main()
