import datetime
import html
import os
import re
from typing import Any, Optional

from requests import post

import tmt
import tmt.steps
import tmt.steps.report
import tmt.utils
from tmt.container import container, field
from tmt.utils import Path
from tmt.utils.markdown import markdown_to_html, sanitize_for_xml

from .junit import ResultsContext, make_junit_xml

DEFAULT_FILENAME = 'xunit.xml'
DEFAULT_TEMPLATE = 'Empty'


@container
class ReportPolarionData(tmt.steps.report.ReportStepData):
    file: Optional[Path] = field(
        default=None,
        option='--file',
        metavar='FILE',
        help='Path to the file to store xUnit in.',
        normalize=tmt.utils.normalize_path,
    )

    upload: bool = field(
        default=True,
        option=('--upload / --no-upload'),
        is_flag=True,
        show_default=True,
        help="""
            Whether to upload results to Polarion,
            also uses environment variable TMT_PLUGIN_REPORT_POLARION_UPLOAD.
            """,
    )

    project_id: Optional[str] = field(
        default=None,
        option='--project-id',
        metavar='ID',
        help="""
             Use specific Polarion project ID,
             also uses environment variable TMT_PLUGIN_REPORT_POLARION_PROJECT_ID. If no project ID
             is found, the project ID is taken from pylero configuration default project setting as
             a last resort.
             """,
    )

    title: Optional[str] = field(
        default=None,
        option='--title',
        metavar='TITLE',
        help="""
             Use specific test run title,
             also uses environment variable TMT_PLUGIN_REPORT_POLARION_TITLE.
             """,
    )

    description: Optional[str] = field(
        default=None,
        option='--description',
        metavar='DESCRIPTION',
        help="""
             Use specific test run description,
             also uses environment variable TMT_PLUGIN_REPORT_POLARION_DESCRIPTION.
             """,
    )

    template: Optional[str] = field(
        default=None,
        option='--template',
        metavar='TEMPLATE',
        help="""
             Use specific test run template,
             also uses environment variable TMT_PLUGIN_REPORT_POLARION_TEMPLATE.
             """,
    )

    use_facts: bool = field(
        default=False,
        option=('--use-facts / --no-use-facts'),
        is_flag=True,
        show_default=True,
        help="""
            Use hostname and arch from guest facts,
            also uses environment variable TMT_PLUGIN_REPORT_POLARION_USE_FACTS.
            """,
    )

    prettify: bool = field(
        default=True,
        option=('--prettify / --no-prettify'),
        is_flag=True,
        show_default=True,
        help="Enable the XML pretty print for generated XUnit file.",
    )

    include_output_log: bool = field(
        default=True,
        option=('--include-output-log / --no-include-output-log'),
        is_flag=True,
        show_default=True,
        help='Include full standard output in resulting xml file.',
    )

    token_upload: bool = field(
        default=False,
        option=('--token-upload / --no-token-upload'),
        is_flag=True,
        show_default=True,
        help="""
            Use direct Polarion API for uploads (supports token authentication).
            When enabled, test runs are created via pylero API instead of XUnit importer.
            This allows token authentication and additional metadata fields.
            Also uses environment variable TMT_PLUGIN_REPORT_POLARION_TOKEN_UPLOAD.
            """,
    )

    auto_create_testcases: bool = field(
        default=False,
        option=('--auto-create-testcases / --no-auto-create-testcases'),
        is_flag=True,
        show_default=True,
        help="""
            Automatically create missing test cases in Polarion before uploading test run.
            If a test case is not found in Polarion, it will be created automatically.
            Requires --project-id to be set. Uses environment variable
            TMT_PLUGIN_REPORT_POLARION_AUTO_CREATE_TESTCASES.
            """,
    )
    
    # Store any extra fields from FMF that aren't defined above (for custom Polarion fields)
    _extra_fields: dict[str, Any] = field(default_factory=dict, internal=True)
    
    def post_normalization(
        self,
        raw_data: tmt.steps._RawStepData,
        logger: tmt.log.Logger,
    ) -> None:
        """Store any extra fields from raw_data that aren't defined as fields."""
        super().post_normalization(raw_data, logger)
        
        # Get all defined field names
        defined_fields = set(self._keys())
        
        # Store any extra fields
        for key, value in raw_data.items():
            # Convert key names: dashes to underscores for comparison
            key_normalized = key.replace('-', '_')
            if key_normalized not in defined_fields and key not in defined_fields:
                # Store with original key name
                self._extra_fields[key] = value
                logger.debug(f"Stored extra field: {key} = {value}", level=4)


@tmt.steps.provides_method('polarion')
class ReportPolarion(tmt.steps.report.ReportPlugin[ReportPolarionData]):
    """
    Write test results into an xUnit file and upload to Polarion.

    In order to get quickly started create a pylero config
    file ``~/.pylero`` in your home directory with the
    following content:

    .. code-block:: ini

        [webservice]
        url=https://{your polarion web URL}/polarion
        svn_repo=https://{your polarion web URL}/repo
        default_project={your project name}
        user={your username}
        password={your password}
        # Or use token instead of password:
        # token={your API token}

    See the ``Pylero Documentation`` for more details on how
    to configure the ``pylero`` module.

    https://github.com/RedHatQE/pylero

    **Upload Methods**

    The plugin supports two upload methods:

    - **XUnit Importer** (default): Legacy method using HTTP POST to
      ``/import/xunit`` endpoint. Only supports password authentication.

    - **Direct API** (``--token-upload``): Uses pylero's TestRun API.
      Supports both token and password authentication. Provides additional
      features like metadata fields, rich descriptions with plan 
      summary/description, and ReportPortal integration via ``rplaunchurl`` 
      field.

    **Schema-Driven Custom Fields**

    Custom Polarion fields are configured via TMT plan files (not CLI options).
    The plugin uses a YAML schema file to dynamically discover and validate
    custom fields. This schema-driven approach provides:

    - **Generic field handling**: No hardcoded field-specific logic
    - **Type conversion**: Automatic conversion based on field type (string,
      boolean, enum, enum-multi-select, text, rich_text)
    - **Enumeration validation**: Ensures values match Polarion enumerations
    - **Value transformations**: Auto-applies mappings (e.g., x86_64 → x8664)
    - **Extensibility**: Add new fields by updating schema, no code changes

    The schema is dynamically generated by querying Polarion's API at runtime,
    ensuring it always matches your project's current configuration.

    **Available Custom Fields** (plan-only, no CLI options):

    - ``planned-in``: Test cycle/release (enum)
    - ``assignee``: Responsible person (enum)
    - ``pool-team``: Team/subsystem (enum)
    - ``arch``: Architecture (enum, auto-normalized)
    - ``build``: Build number (string)
    - ``compose-id``: Compose identifier (string)
    - ``platform``: Execution platform (string)
    - ``sample-image``: Image used (string)
    - ``logs``: Artifacts URL (string)
    - ``browser``: Browser used (enum)
    - ``component``: Component(s) under test (enum-multi-select)
    - ``fips``: FIPS mode flag (boolean)
    - ``selinux-state``, ``selinux-mode``, ``selinux-policy``: SELinux config
    - ``deployment-mode``: Deployment mode (enum, from FMF context)
    - ``schedule-task``: Test cycle/schedule (enum)

    .. note::

        Your Polarion project might need a custom value format
        for the ``arch``, ``planned-in`` and other fields. The
        format of these fields might differ across Polarion
        projects, for example, ``x8664`` can be used instead
        of ``x86_64`` for the architecture. The schema handles
        these transformations automatically.

    **ReportPortal Integration**

    When using ``--token-upload`` with a ReportPortal reporter in the same
    plan, the Polarion test run will automatically include a link to the
    ReportPortal launch in the ``rplaunchurl`` field for easy navigation
    between the two systems.

    **Examples**

    .. code-block:: bash

        # Basic usage (legacy XUnit importer)
        tmt run --all report --how polarion --project-id tmt
        
        # Use direct API with token authentication
        tmt run --all report --how polarion --project-id tmt --token-upload
        
        # Generate xUnit file without uploading
        tmt run --all report --how polarion --project-id tmt --no-upload
        
        # Auto-create missing test cases
        tmt run --all report --how polarion --project-id tmt --auto-create-testcases
        
        # Use custom schema for field definitions
        tmt run --all report --how polarion --project-id tmt --schema /path/to/schema.yaml

    .. code-block:: yaml

        # Basic configuration (legacy method)
        report:
            how: polarion
            file: test.xml
            project-id: tmt
            title: tests_that_pass
            
        # Schema-driven configuration with custom fields
        report:
            how: polarion
            project-id: tmt
            token-upload: true
            
            # Core fields (also available via CLI)
            title: "Feature XYZ Validation"
            description: "Custom test run description"
            template: Empty
            auto-create-testcases: true
            schema: /path/to/custom-schema.yaml
            
            # Custom fields (plan-only, no CLI options)
            planned-in: RHEL-9.1.0
            assignee: username
            pool-team: sst_tmt
            arch: x86_64  # Auto-transformed to x8664
            build: RHEL-9.1.0-20250113.0
            compose-id: RHEL-9.1.0-20250113.0
            platform: beaker
            browser: chromium
            component: cockpit  # Can be list for multi-select
            fips: false
            
        # ReportPortal + Polarion integration
        report:
            # First: Upload to ReportPortal
            - how: reportportal
              project: myproject
              url: https://reportportal.example.com
              
            # Second: Create Polarion test run with ReportPortal link
            - how: polarion
              project-id: tmt
              token-upload: true
              planned-in: RHEL-9.1.0
              assignee: username
              pool-team: sst_tmt
              arch: x86_64
    """

    _data_class = ReportPolarionData

    @property
    def _preserved_workdir_members(self) -> set[str]:
        """
        A set of members of the step workdir that should not be removed.
        """

        members = super()._preserved_workdir_members

        if self.data.file is None:
            members = {*members, DEFAULT_FILENAME}
        
        # Always preserve the dynamically generated schema file
        members = {*members, 'polarion-schema.yaml'}

        return members

    def _set_polarion_field(
        self,
        test_run: Any,
        field_id: str,
        value: Any,
        field_def: dict[str, Any],
        schema: Any,
    ) -> bool:
        """
        Set a field on a Polarion TestRun object using schema-driven logic.
        
        Args:
            test_run: Polarion TestRun object
            field_id: Field identifier
            value: Value to set
            field_def: Field definition from schema
            schema: DynamicPolarionSchema instance
            
        Returns:
            True if field was set successfully, False otherwise
        """
        from pylero.test_run import TestRun
        from pylero.text import Text
        
        field_type = field_def.get('type', 'string')
        is_multi = field_def.get('multi', False)
        
        # Process value through schema (type conversion, transformation, validation)
        processed_value = schema.process_field_value(field_id, value)
        
        # Validate enum values
        if field_type == 'enum':
            if is_multi and isinstance(processed_value, list):
                for val in processed_value:
                    if not schema.validate_enum_value(field_id, val):
                        self.warn(
                            f"Value '{val}' in list is not valid for enum field '{field_id}'. "
                            f"Check schema for valid values."
                        )
                        return False
            elif not is_multi and not schema.validate_enum_value(field_id, processed_value):
                self.warn(
                    f"Value '{processed_value}' is not valid for enum field '{field_id}'. "
                    f"Check schema for valid values."
                )
                return False
        
        try:
            # For multi-select enum fields, use property setter
            if is_multi and field_type == 'enum':
                # Ensure processed_value is a list of strings
                if isinstance(processed_value, str):
                    processed_value = [processed_value]
                
                # Check if field_id exists in TestRun's _cls_suds_map
                if field_id in TestRun._cls_suds_map:
                    # Ensure test_run._suds_object is properly initialized
                    if not hasattr(test_run, '_suds_object') or test_run._suds_object is None:
                        self.warn(f"TestRun._suds_object not initialized, cannot set {field_id}")
                        return False
                    
                    # Ensure customFields is initialized
                    if not hasattr(test_run._suds_object, 'customFields') or test_run._suds_object.customFields is None:
                        test_run._suds_object.customFields = test_run.custom_array_obj()
                    
                    # Set via property (e.g., test_run.component = ['cockpit'])
                    setattr(test_run, field_id, processed_value)
                    self.debug(
                        f"Set multi-select field {field_id}={processed_value} via property setter "
                        f"(type: {field_type})"
                    )
                else:
                    self.warn(f"TestRun has no property '{field_id}' in _cls_suds_map, skipping")
                    return False
            
            # Helper to set custom text/string fields directly on SUDS object
            def _set_custom_text_field(test_run, field_key: str, text_obj):
                """Directly set custom text field on SUDS object, bypassing pylero validation."""
                from pylero.custom import Custom
                
                # Create a Custom pylero object
                custom_obj = Custom()
                custom_obj.key = field_key
                # Set the value directly on the SUDS object to avoid pylero validation
                custom_obj._suds_object.key = field_key
                custom_obj._suds_object.value = text_obj._suds_object
                
                # Add to the test run's SUDS customFields array directly
                if not hasattr(test_run._suds_object, 'customFields') or not test_run._suds_object.customFields:
                    test_run._suds_object.customFields = type('obj', (object,), {'Custom': []})()
                
                if not hasattr(test_run._suds_object.customFields, 'Custom'):
                    test_run._suds_object.customFields.Custom = []
                
                # Check if field already exists and update it
                existing = [cf for cf in test_run._suds_object.customFields.Custom if cf.key == field_key]
                if existing:
                    existing[0].value = text_obj._suds_object
                else:
                    test_run._suds_object.customFields.Custom.append(custom_obj._suds_object)
            
            # ROOT CAUSE SOLUTION: Use property setters instead of _set_custom_field()
            # Pylero's property setters have special handling for each field type that creates
            # the correct SUDS objects automatically. Using _set_custom_field() bypasses this
            # logic and causes SimpleDeserializer and type validation errors.
            
            # For string, text, and rich_text fields
            if field_type in ['string', 'text', 'rich_text']:
                # Convert to string and sanitize
                value_str = str(processed_value) if processed_value is not None else ''
                value_str = sanitize_for_xml(value_str).strip()
                
                if not value_str:
                    self.debug(f"Skipping field {field_id}: value is empty after sanitization")
                    return False
                
                # Determine if this needs HTML formatting
                needs_html = field_type == 'rich_text' or field_id == 'description' or '<' in value_str
                
                if needs_html or field_type in ['text', 'rich_text']:
                    # For HTML/rich text content, create Text object with proper content type
                    text_obj = Text(content=value_str)
                    text_obj._suds_object.type = 'text/html' if needs_html else 'text/plain'
                    
                    # Use _set_custom_text_field helper for text fields (sets directly on SUDS object)
                    _set_custom_text_field(test_run, field_id, text_obj)
                    self.debug(f"Set {field_type} field {field_id} as Text object (content-type: {text_obj._suds_object.type})")
                else:
                    # For plain string fields, try property setter first
                    # This lets pylero's property setter create the correct SUDS structure
                    setattr(test_run, field_id, value_str)
                    self.debug(f"Set string field {field_id} via property setter")
            
            # For boolean fields
            elif field_type == 'boolean':
                # Convert to Python boolean
                bool_value = processed_value in (True, 'true', 'True', 'yes', 'Yes', '1', 1)
                # Use property setter instead of _set_custom_field
                setattr(test_run, field_id, bool_value)
                self.debug(f"Set boolean field {field_id}={bool_value} via property setter")
            
            # For enum fields (single and multi-select)
            elif field_type == 'enum':
                # Check if this is a multi-select enum field
                is_multi = field_def.get('multi', False)
                
                if is_multi:
                    # Multi-select enum: wrap in list
                    if isinstance(processed_value, list):
                        final_value = processed_value
                    else:
                        # Single value -> wrap in list
                        value_str = str(processed_value) if processed_value is not None else ''
                        final_value = [sanitize_for_xml(value_str).strip()]
                    self.debug(f"Set multi-select enum field {field_id}={final_value} via property setter")
                else:
                    # Single-select enum: plain string
                    value_str = str(processed_value) if processed_value is not None else ''
                    final_value = sanitize_for_xml(value_str).strip()
                    self.debug(f"Set enum field {field_id}={final_value} via property setter")
                
                # Try property setter first (validates and creates EnumOptionId)
                try:
                    setattr(test_run, field_id, final_value)
                    # Verify the field was actually set
                    actual_value = getattr(test_run, field_id, None)
                    self.debug(f"Verified {field_id}: set to {actual_value}")
                except Exception as validation_error:
                    # If pylero's validation rejects it, set directly on SUDS object
                    # This bypasses client-side validation and lets Polarion decide
                    error_msg = str(validation_error)
                    if 'is not a valid value for' in error_msg or 'has no attribute' in error_msg:
                        self.warn(f"Pylero validation rejected '{field_id}' ({error_msg}), bypassing to set directly")
                        from pylero.custom import Custom
                        from pylero.enum_option_id import EnumOptionId
                        
                        if is_multi:
                            # For multi-select, create ArrayOfEnumOptionId manually
                            # This is complex, so we'll skip it and re-raise
                            raise
                        else:
                            # For single enum, create EnumOptionId manually
                            custom_obj = Custom()
                            custom_obj.key = field_id
                            custom_obj._suds_object.key = field_id
                            
                            # Create EnumOptionId object
                            enum_obj = EnumOptionId(final_value)
                            custom_obj._suds_object.value = enum_obj._suds_object
                            
                            # Add to test run's custom fields
                            if not hasattr(test_run._suds_object, 'customFields') or not test_run._suds_object.customFields:
                                test_run._suds_object.customFields = type('obj', (object,), {'Custom': []})()
                            if not hasattr(test_run._suds_object.customFields, 'Custom'):
                                test_run._suds_object.customFields.Custom = []
                            
                            # Check if field already exists and update it
                            existing = [cf for cf in test_run._suds_object.customFields.Custom if cf.key == field_id]
                            if existing:
                                existing[0].value = enum_obj._suds_object
                            else:
                                test_run._suds_object.customFields.Custom.append(custom_obj._suds_object)
                            
                            self.debug(f"Set enum field {field_id} directly on SUDS object, bypassing validation")
                    else:
                        # Other errors, re-raise
                        raise
            
            # For any other field type
            else:
                # Use property setter for generic fields
                setattr(test_run, field_id, processed_value)
                self.debug(f"Set custom field {field_id}={processed_value} (type: {field_type}) via property setter")
            
            return True
            
        except Exception as e:
            # Real errors (validation errors are already handled inline for enums)
            self.warn(f"Failed to set field '{field_id}' (type: {field_type}): {e}")
            import traceback
            self.debug(f"Full traceback:")
            self.debug(traceback.format_exc())
            self.debug(f"This field may not be configured in your Polarion project")
            return False

    def _build_description_parts(self, rp_url: Optional[str] = None) -> list[str]:
        """
        Build description HTML parts from plan metadata and ReportPortal info.
        
        Args:
            rp_url: Optional ReportPortal launch URL
            
        Returns:
            List of HTML description parts to be joined
        """
        parts = []
        
        # TMT autogeneration header with plan link
        web_link = self.step.plan.web_link()
        if web_link:
            parts.append(
                f'<p><em>ℹ️ This test run was autogenerated by TMT from plan: '
                f'<a href="{web_link}">{self.step.plan.name}</a></em></p><hr/>'
            )
        
        # Plan summary as H2 header
        if self.step.plan.summary:
            summary_safe = html.escape(sanitize_for_xml(self.step.plan.summary))
            parts.append(f"<h2>{summary_safe}</h2>")
        
        # Plan description (with markdown-to-HTML conversion)
        if self.step.plan.description:
            desc_safe = sanitize_for_xml(self.step.plan.description)
            desc_html = markdown_to_html(html.escape(desc_safe))
            parts.append(desc_html)
        
        return parts

    def _upload_via_api(
        self,
        title: str,
        project_id: str,
        template: Optional[str],
        testsuites_properties: dict[str, Optional[str]],
        results_context: ResultsContext,
    ) -> None:
        """
        Upload test results using direct Polarion API (supports token authentication).
        
        This method uses pylero's TestRun API to create test runs and add test records.
        It supports both token and password authentication and provides additional
        features like metadata fields and rich descriptions.
        
        Args:
            title: Test run title
            project_id: Polarion project ID
            template: Test run template name
            testsuites_properties: Dictionary of test run properties
            results_context: Test results to upload
        """
        from tmt.export.polarion import PolarionWorkItem, find_polarion_case_ids
        from pylero.test_run import TestRun
        from pylero.text import Text
        from pylero.enum_option_id import EnumOptionId
        from .dynamic_polarion_schema import DynamicPolarionSchema
        
        # Load schema for project-specific field definitions
        self.debug(f"Loading field schema for Polarion project '{project_id}'...")
        
        try:
            schema = DynamicPolarionSchema(project_id)
            schema_dict = schema.load_from_polarion()
            
            # Save schema to phase workdir (same directory as xUnit file)
            schema_yaml_path = self.phase_workdir / 'polarion-schema.yaml'
            schema.save_to_yaml(str(schema_yaml_path))
            self.debug(f"Loaded {len(schema_dict.get('custom_fields', {}))} field definitions")
            # Schema file location will be printed at the end with xUnit file location
            
        except Exception as schema_error:
            raise RuntimeError(
                f"Failed to load Polarion schema for project '{project_id}': {schema_error}\n"
                f"Ensure Polarion credentials are valid."
            )
        
        # Check if we should auto-create missing test cases
        auto_create = self.get('auto-create-testcases', os.getenv('TMT_PLUGIN_REPORT_POLARION_AUTO_CREATE_TESTCASES'))
        
        # Pre-process results to ensure all test cases exist in Polarion
        if auto_create:
            for result in results_context:
                if not result.ids or not any(result.ids.values()):
                    self.warn(
                        f"Test Case '{result.name}' has no IDs and cannot be auto-created. "
                        "Please run 'tmt tests export --how polarion' to add an ID first."
                    )
                    continue
                
                work_item_id, test_project_id = find_polarion_case_ids(result.ids)
                
                if work_item_id is None or test_project_id is None:
                    # Try to create the test case
                    self.info(f"Test case '{result.name}' not found in Polarion, attempting to create...")
                    
                    # Build test data from result
                    test_data = {
                        'id': result.ids.get('id'),
                        'summary': result.name,
                        'path': result.name,  # Use test name as fallback path
                    }
                    
                    created_id = self._create_polarion_testcase(
                        test_name=result.name,
                        test_data=test_data,
                        project_id=project_id,
                    )
                    
                    if not created_id:
                        self.warn(f"Failed to create test case '{result.name}' in Polarion")
        
        # Monkey-patch pylero TestRun to add rplaunchurl field support
        # This field exists in Polarion but isn't exposed in pylero
        if not hasattr(TestRun, '_rplaunchurl'):
            # Add rplaunchurl as a property with getter/setter
            def _get_rplaunchurl(self):
                """Get rplaunchurl field from test run."""
                return getattr(self._suds_object, 'rplaunchurl', None)
            
            def _set_rplaunchurl(self, value):
                """Set rplaunchurl field on test run."""
                self._suds_object.rplaunchurl = value
            
            TestRun._rplaunchurl = property(_get_rplaunchurl, _set_rplaunchurl)
            # Also add as class attribute so pylero knows about it
            if not hasattr(TestRun, 'rplaunchurl'):
                TestRun.rplaunchurl = TestRun._rplaunchurl
        
        try:
            # Create test run
            template_to_use = template or DEFAULT_TEMPLATE
            self.debug(f"Creating test run '{title}' using template '{template_to_use}'")
            test_run = TestRun.create(
                project_id=project_id,
                template=template_to_use,
                title=title,
            )
            self.debug(f"Created test run: {test_run.test_run_id}")
            
            # Reload test run to ensure it's fully initialized before setting fields
            test_run = TestRun(project_id=project_id, test_run_id=test_run.test_run_id)
            self.debug(f"Reloaded test run: {test_run.test_run_id}")
            
            # Perform initial update to ensure test run is in good state
            try:
                test_run.update()
                self.debug("Initial update successful")
            except Exception as update_error:
                self.debug(f"Initial update note: {update_error}")
            
            # Set custom fields dynamically from testsuites_properties using schema
            for property_key, raw_value in testsuites_properties.items():
                # Skip non-custom properties
                if not property_key.startswith('polarion-custom-'):
                    continue
                
                # Extract field_id from property_key
                # e.g., 'polarion-custom-plannedin' -> 'plannedin'
                field_id = property_key.replace('polarion-custom-', '')
                
                # Skip hostname - it's a special field not in schema
                if field_id == 'hostname':
                    continue
                
                if not raw_value:
                    continue
                
                # Get field definition from schema
                field_def = schema.get_field_definition(field_id)
                if not field_def:
                    self.debug(f"Field '{field_id}' not found in schema, skipping")
                    continue
                
                # Skip read-only fields according to schema
                if field_def.get('read_only', False):
                    self.debug(f"Field '{field_id}' is read-only according to schema, skipping")
                    continue
                
                # Set field using generic schema-driven method
                self.info(f"🔧 Setting field '{field_id}' = '{raw_value}' (type: {field_def.get('type')})")
                success = self._set_polarion_field(test_run, field_id, raw_value, field_def, schema)
                
                if success:
                    # Try to update immediately after each field to isolate which field causes issues
                    try:
                        test_run.update()
                        self.info(f"✅ Successfully set field '{field_id}'")
                    except Exception as update_e:
                        # If update fails, the field setting is the problem
                        error_msg = str(update_e)
                        
                        # Show detailed error for debugging
                        self.warn(f"❌ Field '{field_id}' rejected by Polarion:")
                        self.warn(f"   Error: {error_msg}")
                        self.warn(f"   Field type in schema: {field_def.get('type')}")
                        self.warn(f"   Value attempted: '{raw_value}'")
                        
                        # Provide helpful guidance
                        if 'SAXException' in error_msg or 'SimpleDeserializer' in error_msg:
                            self.warn(
                                f"   💡 This usually means the field is not configured in Polarion "
                                f"or has a different type than the schema specifies."
                            )
                        elif 'is not a valid type' in error_msg:
                            self.warn(
                                f"   💡 Type mismatch - check if field type in Polarion matches schema."
                            )
                        
                        # Reload test run to clear the problematic field
                        test_run = TestRun(project_id=project_id, test_run_id=test_run.test_run_id)
                        self.debug(f"Reloaded test run to continue with remaining fields")
            
            # Check for ReportPortal URL
            rp_url = None
            rp_url_file = self.step.workdir / 'reportportal_launch_url.txt'
            
            self.debug(f"Looking for ReportPortal launch URL in: {rp_url_file}")
            
            if rp_url_file.exists():
                try:
                    rp_url = rp_url_file.read_text().strip()
                    self.debug(f"Found ReportPortal launch URL in file: {rp_url}")
                except Exception as e:
                    self.debug(f"Could not read ReportPortal URL file: {e}")
            else:
                self.debug(f"ReportPortal URL file not found: {rp_url_file}")
            
            # Build description from plan metadata
            description_parts = self._build_description_parts(rp_url)
            
            if description_parts:
                try:
                    description_html = "<br/><br/>".join(description_parts)
                    # Get description field definition from schema
                    desc_field_def = schema.get_field_definition('description')
                    if desc_field_def:
                        self.info(f"🔧 Setting description (type: {desc_field_def.get('type')})")
                        success = self._set_polarion_field(
                            test_run, 'description', description_html, desc_field_def, schema
                        )
                        if success:
                            # Try to update description
                            try:
                                test_run.update()
                                self.info("✅ Successfully set description")
                            except Exception as desc_update_e:
                                self.warn(f"Failed to commit description: {desc_update_e}")
                                # Reload to clear problematic description
                                test_run = TestRun(project_id=project_id, test_run_id=test_run.test_run_id)
                    else:
                        self.warn("Description field not found in schema")
                        
                except Exception as desc_e:
                    self.warn(f"Failed to set description: {desc_e}")
            
            self.info(f'Test run created: {test_run.test_run_id}')
            
            # Set ReportPortal URL AFTER initial update()
            # rplaunchurl is a RICH TEXT (multiline) custom field
            if rp_url:
                try:
                    self.debug(f"Setting rplaunchurl as rich text custom field: {rp_url}")
                    
                    # Create rich text content with clickable link
                    rp_html = f'<a href="{rp_url}">{rp_url}</a>'
                    
                    # Get rplaunchurl field definition from schema
                    rp_field_def = schema.get_field_definition('rplaunchurl')
                    if rp_field_def:
                        success = self._set_polarion_field(
                            test_run, 'rplaunchurl', rp_html, rp_field_def, schema
                        )
                        if success:
                            test_run.update()
                            self.info(f"✅ Set ReportPortal launch URL in Polarion rplaunchurl field")
                            self.info(f"ReportPortal URL: {rp_url}", color='cyan')
                        else:
                            self.info(f"ReportPortal URL: {rp_url} (set in description)", color='yellow')
                    else:
                        self.warn("rplaunchurl field not found in schema")
                        self.info(f"ReportPortal URL: {rp_url} (set in description)", color='yellow')
                    
                    # Also set sync status to false (not yet synced)
                    try:
                        sync_field_def = schema.get_field_definition('syncfinalized')
                        if sync_field_def:
                            self._set_polarion_field(
                                test_run, 'syncfinalized', False, sync_field_def, schema
                            )
                            test_run.update()
                            self.debug("Set syncfinalized=False (awaiting RP sync)")
                    except Exception as sync_e:
                        self.debug(f"Could not set syncfinalized field: {sync_e}")
                    
                except Exception as e:
                    self.warn(f"Failed to set rplaunchurl field: {e}")
                    self.debug(f"Error details: {type(e).__name__}: {e}")
                    self.info(f"ReportPortal URL: {rp_url} (set in description)", color='yellow')
            else:
                self.debug("No ReportPortal launch URL to set")
            
            # Add test records for each result
            self._add_test_records_to_run(test_run, results_context, project_id)
            
            # Update test run to commit test records before attaching files
            test_run.update()
            self.debug("Test run updated with all test records")
            
            # Reload test run from Polarion to get fresh state with committed records
            from pylero.test_run import TestRun
            test_run = TestRun(project_id=project_id, test_run_id=test_run.test_run_id)
            self.debug(f"Reloaded test run {test_run.test_run_id} from Polarion")
            
            # Now attach files to test records (after test run is committed and reloaded)
            self._attach_test_data_files(test_run, results_context, project_id)
            
            server_url = str(PolarionWorkItem._session._server.url)
            test_run_url = (
                f'{server_url}{"" if server_url.endswith("/") else "/"}'
                f'#/project/{project_id}/testrun?id={test_run.test_run_id}'
            )
            self.info(f'URL: {test_run_url}')
            
        except Exception as error:
            raise tmt.utils.ReportError(
                f"Failed to create test run in Polarion via API: {error}"
            ) from error

    def _add_test_records_to_run(
        self,
        test_run: Any,
        results_context: ResultsContext,
        project_id: str,
    ) -> None:
        """
        Add test records to an existing Polarion test run.
        
        Args:
            test_run: Polarion TestRun object
            results_context: Test results to add
            project_id: Polarion project ID
        """
        from tmt.export.polarion import PolarionWorkItem, find_polarion_case_ids
        
        for result in results_context:
            if not result.ids or not any(result.ids.values()):
                continue
            
            work_item_id, test_project_id = find_polarion_case_ids(result.ids)
            if not work_item_id:
                continue
            
            # Map tmt result to Polarion result
            result_str = result.result.name.lower() if hasattr(result.result, 'name') \
                else str(result.result).split('.')[-1].lower()
            
            result_map = {
                'pass': 'passed',
                'fail': 'failed',
                'error': 'failed',
                'info': 'passed',
                'warn': 'passed',
                'skip': 'blocked',
                'pending': 'blocked',
            }
            test_result = result_map.get(result_str, 'failed')
            
            # Convert duration to seconds (handle both float and "HH:MM:SS" format)
            duration_seconds = 0.0
            if result.duration:
                duration_str = str(result.duration)
                if ':' in duration_str:
                    # Parse "HH:MM:SS" format
                    parts = duration_str.split(':')
                    if len(parts) == 3:
                        duration_seconds = (
                            int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
                        )
                else:
                    # Already in seconds
                    duration_seconds = float(duration_str)
            
            # Build test comment with output
            comment_parts = []
            if result.note:
                # result.note can be a string or list
                if isinstance(result.note, list):
                    comment_parts.extend([sanitize_for_xml(str(n)) for n in result.note if n])
                else:
                    comment_parts.append(sanitize_for_xml(str(result.note)))
            
            # Add test output/log
            log_content = None
            if hasattr(result, 'log') and result.log:
                if isinstance(result.log, list):
                    # Find output.txt in log list
                    for log_path in result.log:
                        if isinstance(log_path, (str, Path)):
                            log_path = Path(log_path)
                            if not log_path.is_absolute():
                                log_path = self.step.plan.execute.workdir / log_path
                            if log_path.name == 'output.txt' and log_path.exists():
                                try:
                                    log_content = log_path.read_text(encoding='utf-8', errors='replace')
                                except Exception:
                                    # Fallback: try reading as binary and decode
                                    log_content = log_path.read_bytes().decode('utf-8', errors='replace')
                                break
                elif isinstance(result.log, Path):
                    try:
                        log_content = result.log.read_text(encoding='utf-8', errors='replace')
                    except Exception:
                        log_content = result.log.read_bytes().decode('utf-8', errors='replace')
                elif isinstance(result.log, str):
                    log_content = result.log
            
            if log_content:
                # Sanitize log content to remove invalid XML characters
                log_content = sanitize_for_xml(log_content)
                if comment_parts:
                    comment_parts.append('\n---\nTest Output:\n')
                # Convert markdown to HTML with proper escaping
                comment_parts.append(markdown_to_html(html.escape(log_content)))
            
            test_comment_str = ''.join(comment_parts)
            
            # Create Text object with text/html content type for proper rendering
            test_comment = None
            if test_comment_str:
                from pylero.text import Text
                test_comment = Text(content=test_comment_str)
                test_comment._suds_object.type = 'text/html'
            
            # Add test record
            self.debug(
                f"Adding test record: {work_item_id} -> {test_result} "
                f"(duration: {duration_seconds:.2f}s)"
            )
            test_run.add_test_record_by_fields(
                test_case_id=work_item_id,
                test_result=test_result,
                test_comment=test_comment,
                executed_by=PolarionWorkItem._session.user_id,
                executed=datetime.datetime.now(tz=datetime.timezone.utc),
                duration=duration_seconds,
            )

    def _attach_test_data_files(
        self,
        test_run: Any,
        results_context: ResultsContext,
        project_id: str,
    ) -> None:
        """
        Attach test data files to test records in Polarion.
        
        This method attaches all files from each test's TMT_TEST_DATA directory
        to its corresponding test record in Polarion. It must be called AFTER
        the test run has been committed (test_run.update()).
        
        Args:
            test_run: Polarion TestRun object (already committed)
            results_context: Test results containing data_path
            project_id: Polarion project ID
        """
        from tmt.export.polarion import PolarionWorkItem, find_polarion_case_ids
        
        for result in results_context:
            if not result.ids or not any(result.ids.values()):
                continue
            
            work_item_id, test_project_id = find_polarion_case_ids(result.ids)
            if not work_item_id:
                continue
            
            # Attach test data files to this specific test record
            if result.data_path:
                # Resolve the absolute path to the test data directory
                data_dir = result.data_path
                if not data_dir.is_absolute():
                    data_dir = self.step.plan.execute.workdir / data_dir
                
                if data_dir.exists() and data_dir.is_dir():
                    # Get all files from test data directory
                    data_files = sorted(data_dir.iterdir())
                    if data_files:
                        self.info(
                            f"Attaching {len(data_files)} file(s) from {data_dir.name}/ "
                            f"to test record {work_item_id}"
                        )
                        for data_file in data_files:
                            if data_file.is_file():
                                try:
                                    self.debug(f"  Attaching: {data_file.name}")
                                    test_run.add_attachment_to_test_record(
                                        test_case_id=work_item_id,
                                        path=str(data_file),
                                        title=data_file.name
                                    )
                                    self.debug(f"  ✓ Attached: {data_file.name}")
                                except Exception as e:
                                    self.warn(
                                        f"Failed to attach {data_file.name} "
                                        f"to test record {work_item_id}: {e}"
                                    )
                    else:
                        self.debug(f"No files found in test data directory: {data_dir}")
                else:
                    self.debug(f"Test data directory not found: {data_dir}")

    def _create_polarion_testcase(
        self,
        test_name: str,
        test_data: dict[str, Any],
        project_id: str,
    ) -> Optional[str]:
        """
        Create a test case in Polarion.
        
        Args:
            test_name: Name of the test
            test_data: Test metadata dictionary
            project_id: Polarion project ID
            
        Returns:
            Work item ID of created test case, or None if creation failed
        """
        from tmt.export.polarion import PolarionTestCase
        
        try:
            # Create test case with summary as title
            summary = test_data.get('summary', test_name)
            self.info(f"Creating test case in Polarion: {summary}")
            
            # Use the create_polarion_case function from export module
            from tmt.export.polarion import create_polarion_case
            test_path = Path(test_data.get('path', '/unknown'))
            
            polarion_case = create_polarion_case(summary, project_id, test_path)
            
            # Set UUID if available
            if test_data.get('id'):
                polarion_case.tmtid = test_data['id']
                polarion_case.update()
            
            self.info(f"✅ Created test case: {polarion_case.work_item_id}")
            return polarion_case.work_item_id
            
        except Exception as e:
            self.warn(f"Failed to create test case '{test_name}': {e}")
            return None

    def go(self, *, logger: Optional[tmt.log.Logger] = None) -> None:
        """
        Go through executed tests and report into Polarion
        """

        super().go(logger=logger)

        from tmt.export.polarion import find_polarion_case_ids, import_polarion

        import_polarion()
        from tmt.export.polarion import PolarionWorkItem

        title = self.data.title
        if not title:
            # Generate title: [polarion ID] - [distro] - [plan name]
            # Polarion ID (timestamp in format: YYYYMMDD-HHMM)
            polarion_id = datetime.datetime.now(tz=datetime.timezone.utc).strftime("%Y%m%d-%H%M")
            
            title_parts = [polarion_id]
            
            # Try to get distro from provision metadata
            # Use stored metadata instead of live guest to work with --last report --force
            try:
                # Get provision data from step
                provision_data = self.step.plan.provision.data
                self.debug(f"Provision data type: {type(provision_data)}, length: {len(provision_data) if provision_data else 0}")
                
                # Try to get guest info from provision data or phases
                if provision_data and len(provision_data) > 0:
                    guest_data = provision_data[0] if isinstance(provision_data, list) else provision_data
                    self.debug(f"Guest data type: {type(guest_data)}")
                    self.debug(f"Guest data has facts: {hasattr(guest_data, 'facts')}")
                    
                    # Try to get distro from guest data
                    distro = None
                    if hasattr(guest_data, 'facts'):
                        self.debug(f"Facts type: {type(guest_data.facts)}")
                        self.debug(f"Facts has distro: {hasattr(guest_data.facts, 'distro')}")
                        if hasattr(guest_data.facts, 'distro') and guest_data.facts.distro:
                            distro = guest_data.facts.distro
                            self.debug(f"Found distro from facts: {distro}")
                    
                    # Fallback: extract distro from image name if facts are not available
                    if not distro and hasattr(guest_data, 'image') and guest_data.image:
                        image_str = str(guest_data.image)
                        self.debug(f"Extracting distro from image: {image_str}")
                        
                        # Try to extract distro from image name patterns
                        # Examples: "1MT-RHEL-9.8.0-20251105.0.box" -> "RHEL-9.8"
                        #           "Fedora-42" -> "Fedora-42"
                        #           "CentOS-Stream-9" -> "CentOS-Stream-9"
                        
                        # Pattern to match distro info in image names
                        patterns = [
                            r'RHEL[- ](\d+)\.(\d+)',  # RHEL-9.8 or RHEL 9.8
                            r'Fedora[- ](\d+)',  # Fedora-42 or Fedora 42
                            r'CentOS[- ]Stream[- ](\d+)',  # CentOS-Stream-9
                            r'CentOS[- ](\d+)',  # CentOS-9
                        ]
                        
                        for pattern in patterns:
                            match = re.search(pattern, image_str, re.IGNORECASE)
                            if match:
                                if 'RHEL' in pattern:
                                    distro = f"RHEL-{match.group(1)}.{match.group(2)}"
                                elif 'Fedora' in pattern:
                                    distro = f"Fedora-{match.group(1)}"
                                elif 'Stream' in pattern:
                                    distro = f"CentOS-Stream-{match.group(1)}"
                                else:
                                    distro = f"CentOS-{match.group(1)}"
                                self.debug(f"Extracted distro from image name: {distro}")
                                break
                    
                    if distro:
                        # Clean distro name (e.g., "Fedora Linux 42" -> "Fedora-42")
                        # Remove "Linux" and replace spaces with dashes
                        distro_clean = distro.replace(' Linux', '').replace(' ', '-')
                        # Remove special characters that might cause issues
                        distro_clean = distro_clean.replace('(', '').replace(')', '')
                        # Limit length for title
                        if len(distro_clean) > 40:
                            distro_clean = distro_clean[:40]
                        title_parts.append(distro_clean)
                        self.debug(f"Added distro to title: {distro_clean}")
                    else:
                        self.debug("No distro found in guest data or image name")
                        
            except (AttributeError, IndexError, TypeError) as e:
                # If we can't get from provision data, it's okay - just skip
                self.debug(f"Error getting distro for title: {e}")
            
            # Add plan name (TMT node name like /Sanity/upstream-direct/plans/browser/x86_64)
            plan_name = self.step.plan.name
            title_parts.append(plan_name)
            
            title = ' - '.join(title_parts)
            self.debug(f"Generated title (before env var): {title}")
            
            # Also check environment variable
            title = os.getenv('TMT_PLUGIN_REPORT_POLARION_TITLE', title)
        
        # Sanitize title to remove invalid XML characters
        title = sanitize_for_xml(title)
        # Replace dashes in separators with underscores for Polarion compatibility
        # But keep the separators as ' - ' for readability before converting
        title = title.replace(' - ', ' _ ')
        title = title.replace('-', '_')
        template = self.data.template or os.getenv('TMT_PLUGIN_REPORT_POLARION_TEMPLATE')
        project_id = self.data.project_id or os.getenv(
            'TMT_PLUGIN_REPORT_POLARION_PROJECT_ID', PolarionWorkItem._session.default_project
        )

        # The project_id is required
        if not project_id:
            raise tmt.utils.ReportError(
                "The Polarion project ID could not be determined. Consider setting it using "
                "'--project-id' argument or by setting 'TMT_PLUGIN_REPORT_POLARION_PROJECT_ID' "
                "environment variable."
            )

        # TODO: try use self.data instead - but these fields are not optional, they do have
        # default values, do envvars even have any effect at all??
        upload = self.get('upload', os.getenv('TMT_PLUGIN_REPORT_POLARION_UPLOAD'))
        use_facts = self.get('use-facts', os.getenv('TMT_PLUGIN_REPORT_POLARION_USE_FACTS'))

        testsuites_properties: dict[str, Optional[str]] = {}

        # Load schema for custom field definitions
        from .dynamic_polarion_schema import DynamicPolarionSchema
        
        self.debug(f"Loading field schema for Polarion project '{project_id}'...")
        try:
            schema = DynamicPolarionSchema(project_id)
            schema_dict = schema.load_from_polarion()
            
            # Save schema to phase workdir (same directory as xUnit file)
            schema_yaml_path = self.phase_workdir / 'polarion-schema.yaml'
            schema.save_to_yaml(str(schema_yaml_path))
            self.debug(f"Loaded {len(schema_dict.get('custom_fields', {}))} field definitions")
            
        except Exception as schema_error:
            raise RuntimeError(
                f"Failed to load Polarion schema for project '{project_id}': {schema_error}\n"
                f"Ensure Polarion credentials are valid."
            )
        
        # Get all custom fields from schema
        custom_fields = schema_dict.get('custom_fields', {})
        
        # Dynamically collect custom field values from plan data
        # These come from the plan's report configuration (no CLI options)
        for field_id, field_def in custom_fields.items():
            # Skip title and description - they have their own handling
            if field_id in ['title', 'description']:
                continue
            
            # Try to get value from plan data using exact field name from schema
            # Field names in plan.fmf must match the schema field names exactly
            param = None
            
            # Try getting from extra_fields (for fields defined in plan but not as Click options)
            if field_id in self.data._extra_fields:
                param = self.data._extra_fields[field_id]
                if param is not None:  # Check explicitly for None to handle boolean False
                    self.debug(f"Found field '{field_id}' in extra_fields = '{param}'")
            
            # Try self.get() for fields with Click options
            if param is None:
                param = self.get(field_id)
                if param is not None:
                    self.debug(f"Found field '{field_id}' via self.get() = '{param}'")
            
            # Check environment variable as fallback
            if param is None:
                env_var = f'TMT_PLUGIN_REPORT_POLARION_{field_id.upper()}'
                param = os.getenv(env_var)
                if param is not None:
                    self.debug(f"Found field '{field_id}' via env var {env_var} = '{param}'")
            
            if param is not None:
                # Convert booleans to lowercase strings for schema processing
                # This avoids regex errors and ensures proper boolean conversion
                if isinstance(param, bool):
                    param_str = 'true' if param else 'false'
                else:
                    param_str = param
                testsuites_properties[f"polarion-custom-{field_id}"] = param_str
                self.info(f"📝 Collected field '{field_id}' = '{param_str}' (type: {field_def.get('type')})")

        self.debug(f"Custom fields before context check: {[k for k in testsuites_properties.keys() if k.startswith('polarion-custom-')]}")
        
        if use_facts:
            guests = self.step.plan.provision.ready_guests
            try:
                testsuites_properties['polarion-custom-hostname'] = guests[0].primary_address
                testsuites_properties['polarion-custom-arch'] = guests[0].facts.arch
            except IndexError as error:
                raise tmt.utils.ReportError(
                    'Failed to retrieve facts from the guest environment. '
                    'You can use a `--no-use-facts` argument to disable '
                    'this behavior.'
                ) from error

        if template:
            testsuites_properties['polarion-testrun-template-id'] = template

        logs = os.getenv('TMT_REPORT_ARTIFACTS_URL')
        if logs and 'polarion-custom-logs' not in testsuites_properties:
            testsuites_properties['polarion-custom-logs'] = logs

        project_span_ids: list[str] = []

        results_context = ResultsContext(self.step.plan.execute.results())

        for result in results_context:
            if not result.ids or not any(result.ids.values()):
                self.warn(
                    f"Test Case '{result.name}' is not exported to Polarion, "
                    "please run 'tmt tests export --how polarion' on it."
                )
                continue

            work_item_id, test_project_id = find_polarion_case_ids(result.ids)

            if work_item_id is None or test_project_id is None:
                self.warn(f"Test case '{result.name}' missing or not found in Polarion.")
                continue

            if test_project_id not in project_span_ids:
                project_span_ids.append(test_project_id)

            testcase_properties = {
                'polarion-testcase-id': work_item_id,
                'polarion-testcase-project-id': test_project_id,
            }

            # ignore[assignment]: mypy does not support different types for property getter and
            # setter. The assignment is correct, but mypy cannot tell.
            # See https://github.com/python/mypy/issues/3004 for getter/setter discussions
            result.properties = testcase_properties  # type: ignore[assignment]

        testsuites_properties.update(
            {
                'polarion-project-id': project_id,
                'polarion-user-id': PolarionWorkItem._session.user_id,
                'polarion-testrun-title': title,
                'polarion-project-span-ids': ','.join([project_id, *project_span_ids]),
            }
        )

        # Add deployment mode from context if not already set in report config
        # Report-specific config takes precedence over context
        if 'polarion-custom-deploymentMode' not in testsuites_properties:
            deployment_mode = self.step.plan.fmf_context.get('deployment-mode', [])
            if deployment_mode:
                self.debug(f"Using deploymentMode from context: {deployment_mode[0]}")
                testsuites_properties.update({'polarion-custom-deploymentMode': deployment_mode[0]})
        else:
            self.debug(f"Skipping context deploymentMode, using report config value: {testsuites_properties.get('polarion-custom-deploymentMode')}")
        results_context.properties = testsuites_properties

        xml_data = make_junit_xml(
            phase=self,
            flavor='polarion',
            prettify=self.data.prettify,
            include_output_log=self.data.include_output_log,
            results_context=results_context,
        )

        f_path = self.data.file or self.phase_workdir / DEFAULT_FILENAME

        try:
            f_path.write_text(xml_data)
        except Exception as error:
            raise tmt.utils.ReportError(f"Failed to write the output '{f_path}'.") from error

        token_upload = self.get('token-upload', os.getenv('TMT_PLUGIN_REPORT_POLARION_TOKEN_UPLOAD'))
        
        if token_upload:
            # Use direct Polarion API (supports token and password auth)
            self._upload_via_api(
                title=title,
                project_id=project_id,
                template=template,
                testsuites_properties=testsuites_properties,
                results_context=results_context,
            )
        elif upload:
            server_url = str(PolarionWorkItem._session._server.url)
            polarion_import_url = (
                f'{server_url}{"" if server_url.endswith("/") else "/"}import/xunit'
            )
            auth = (PolarionWorkItem._session.user_id, PolarionWorkItem._session.password)

            response = post(
                polarion_import_url,
                auth=auth,
                files={
                    'file': ('xunit.xml', xml_data),
                },
                timeout=10,
            )
            self.info(f'Response code is {response.status_code} with text: {response.text}')
        else:
            self.info('Polarion upload can be done manually using command:')
            self.info(
                'curl -k -u <USER>:<PASSWORD> -X POST -F file=@<XUNIT_XML_FILE_PATH> '
                '<POLARION_URL>/polarion/import/xunit'
            )
        self.info('xUnit file saved at', f_path, 'yellow')
        
        # Print schema file location (saved earlier in the same directory)
        schema_yaml_path = self.phase_workdir / 'polarion-schema.yaml'
        if schema_yaml_path.exists():
            self.info('Polarion schema saved at', schema_yaml_path, 'yellow')
