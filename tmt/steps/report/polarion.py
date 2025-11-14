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

from .junit import ResultsContext, make_junit_xml

DEFAULT_FILENAME = 'xunit.xml'
DEFAULT_TEMPLATE = 'Empty'


def format_as_html(text: str) -> str:
    """
    Format text as HTML with proper line breaks and code blocks.
    
    Preserves formatting from multi-line text and converts common patterns
    to HTML elements for better display in Polarion.
    """
    if not text:
        return ''
    
    # HTML escape the text first
    text = html.escape(text)
    
    # Detect and format code blocks (indented lines)
    lines = text.split('\n')
    html_lines = []
    in_code_block = False
    
    for line in lines:
        # Consider lines starting with 4+ spaces or tab as code
        if line.startswith('    ') or line.startswith('\t'):
            if not in_code_block:
                html_lines.append('<pre><code>')
                in_code_block = True
            html_lines.append(line)
        else:
            if in_code_block:
                html_lines.append('</code></pre>')
                in_code_block = False
            html_lines.append(line)
    
    # Close code block if still open
    if in_code_block:
        html_lines.append('</code></pre>')
    
    # Join with <br/> for line breaks
    return '<br/>'.join(html_lines)


def normalize_arch(arch: str) -> str:
    """
    Normalize architecture string for Polarion compatibility.
    
    Polarion often uses x8664 instead of x86_64.
    """
    if arch == 'x86_64':
        return 'x8664'
    return arch


def sanitize_for_xml(text: str) -> str:
    """
    Remove invalid XML characters from text.
    
    XML 1.0 only allows certain characters. This function removes
    or replaces characters that would cause XML parsing errors.
    
    Valid chars: #x9 | #xA | #xD | [#x20-#xD7FF] | [#xE000-#xFFFD] | [#x10000-#x10FFFF]
    """
    if not text:
        return ''
    
    # Remove null bytes and other control characters (except tab, newline, carriage return)
    # These are invalid in XML and cause SAXParseException
    valid_chars = []
    for char in text:
        code = ord(char)
        # Allow: tab (0x9), newline (0xA), carriage return (0xD), and chars >= 0x20
        # Exclude: control chars (0x0-0x8, 0xB-0xC, 0xE-0x1F)
        # Also exclude Unicode surrogate pairs and other invalid ranges
        if (code == 0x9 or code == 0xA or code == 0xD or
            (0x20 <= code <= 0xD7FF) or
            (0xE000 <= code <= 0xFFFD) or
            (0x10000 <= code <= 0x10FFFF)):
            valid_chars.append(char)
        else:
            # Replace invalid chars with a placeholder or skip them
            if code == 0x0:
                # Null byte - skip it
                continue
            else:
                # Other control char - replace with space
                valid_chars.append(' ')
    
    return ''.join(valid_chars)


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

    planned_in: Optional[str] = field(
        default=None,
        option='--planned-in',
        metavar='PLANNEDIN',
        help="""
             Select a specific release to mark this test run with,
             also uses environment variable TMT_PLUGIN_REPORT_POLARION_PLANNED_IN.
             """,
    )

    assignee: Optional[str] = field(
        default=None,
        option='--assignee',
        metavar='ASSIGNEE',
        help="""
             Who is responsible for this test run,
             also uses environment variable TMT_PLUGIN_REPORT_POLARION_ASSIGNEE.
             """,
    )

    pool_team: Optional[str] = field(
        default=None,
        option='--pool-team',
        metavar='POOLTEAM',
        help="""
             Which subsystem is this test run relevant for,
             also uses environment variable TMT_PLUGIN_REPORT_POLARION_POOL_TEAM.
             """,
    )

    arch: Optional[str] = field(
        default=None,
        option='--arch',
        metavar='ARCH',
        help="""
             Which architecture was this run executed on,
             also uses environment variable TMT_PLUGIN_REPORT_POLARION_ARCH.
             """,
    )

    platform: Optional[str] = field(
        default=None,
        option='--platform',
        metavar='PLATFORM',
        help="""
             Which platform was this run executed on,
             also uses environment variable TMT_PLUGIN_REPORT_POLARION_PLATFORM.
             """,
    )

    build: Optional[str] = field(
        default=None,
        option='--build',
        metavar='BUILD',
        help="""
             Which build was this run executed on,
             also uses environment variable TMT_PLUGIN_REPORT_POLARION_BUILD.
             """,
    )

    sample_image: Optional[str] = field(
        default=None,
        option='--sample-image',
        metavar='SAMPLEIMAGE',
        help="""
             Which sample image was this run executed on,
             also uses environment variable TMT_PLUGIN_REPORT_POLARION_SAMPLE_IMAGE.
             """,
    )

    logs: Optional[str] = field(
        default=None,
        option='--logs',
        metavar='LOGLOCATION',
        help="""
             Location of the logs for this test run,
             also uses environment variable TMT_PLUGIN_REPORT_POLARION_LOGS.
             Ultimately also uses environment variable TMT_REPORT_ARTIFACTS_URL.
             """,
    )

    compose_id: Optional[str] = field(
        default=None,
        option='--compose-id',
        metavar='COMPOSEID',
        help="""
             Compose ID of image used for this run,
             also uses environment variable TMT_PLUGIN_REPORT_POLARION_COMPOSE_ID.
             """,
    )

    fips: bool = field(
        default=False,
        option=('--fips / --no-fips'),
        is_flag=True,
        show_default=True,
        help='FIPS mode enabled or disabled for this run.',
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
      features like metadata fields (planned-in, assignee, pool-team, arch),
      rich descriptions with plan summary/description, and ReportPortal
      integration via ``rplaunchurl`` field.

    .. note::

        Your Polarion project might need a custom value format
        for the ``arch``, ``planned-in`` and other fields. The
        format of these fields might differ across Polarion
        projects, for example, ``x8664`` can be used instead
        of ``x86_64`` for the architecture.

    **ReportPortal Integration**

    When using ``--token-upload`` with a ReportPortal reporter in the same
    plan, the Polarion test run will automatically include a link to the
    ReportPortal launch in the ``rplaunchurl`` field for easy navigation
    between the two systems.

    Examples:

    .. code-block:: bash

        # Enable polarion report from the command line (legacy XUnit importer)
        tmt run --all report --how polarion --project-id tmt
        
        # Use direct API with token authentication
        tmt run --all report --how polarion --project-id tmt --token-upload
        
        # Generate xUnit file without uploading
        tmt run --all report --how polarion --project-id tmt --no-upload --file test.xml
        
        # Auto-create missing test cases
        tmt run --all report --how polarion --project-id tmt --auto-create-testcases

    .. code-block:: yaml

        # Use polarion as the default report for given plan (legacy method)
        report:
            how: polarion
            file: test.xml
            project-id: tmt
            title: tests_that_pass
            
        # Use direct API with metadata fields and ReportPortal integration
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
              auto-create-testcases: true  # Auto-create missing test cases
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

        return members

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
        
        # Normalize architecture values for Polarion compatibility
        if testsuites_properties.get('polarion-custom-arch'):
            testsuites_properties['polarion-custom-arch'] = normalize_arch(
                testsuites_properties['polarion-custom-arch']
            )
        
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
        
        # Helper to set custom text fields directly on SUDS object
        # This works around pylero limitation where _obj_setter rejects Text types for custom fields
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
            
            # Set test run metadata
            # Set group_id (direct attribute)
            if testsuites_properties.get('polarion-custom-poolteam'):
                pool_team = testsuites_properties['polarion-custom-poolteam']
                test_run.group_id = pool_team
                self.debug(f"Set group_id (pool-team)={pool_team}")
            
            # Set custom fields for metadata
            # Only use confirmed working fields (enum types work, string types cause errors)
            custom_field_mapping = {
                'polarion-custom-plannedin': 'plannedin',       # Test Cycle / Planned In (enum)
                'polarion-custom-assignee': 'assignee',         # Assignee (enum)
                'polarion-custom-arch': 'arch',                 # Architecture (enum)
            }
            # Note: build, composeid, logs cause "SimpleDeserializer" errors despite being
            # defined in Polarion. This appears to be a Polarion/pylero limitation.
            
            for property_key, field_name in custom_field_mapping.items():
                value = testsuites_properties.get(property_key)
                if value:
                    # Normalize arch value for Polarion compatibility
                    if field_name == 'arch':
                        value = normalize_arch(value)
                    test_run._set_custom_field(field_name, value)
                    self.debug(f"Set custom field {field_name}={value}")
            
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
            
            # Set description from plan summary and description
            description_parts = []
            
            # Add header indicating TMT autogeneration with link to plan metadata
            web_link = self.step.plan.web_link()
            if web_link:
                description_parts.append(
                    f'<p><em>ℹ️ This test run was autogenerated by TMT from plan: '
                    f'<a href="{web_link}">{self.step.plan.name}</a></em></p>'
                    f'<hr/>'
                )
            
            # Add ReportPortal launch info for Polarion sync linking
            if rp_url:
                # Extract launch name from file for linking
                rp_name_file = self.step.workdir / 'reportportal_launch_name.txt'
                rp_launch_name = None
                if rp_name_file.exists():
                    try:
                        rp_launch_name = rp_name_file.read_text().strip()
                    except Exception:
                        pass
                
                description_parts.append(
                    f'<p><strong>📊 ReportPortal Launch:</strong> <a href="{rp_url}">{rp_launch_name or "View Results"}</a></p>'
                )
                if rp_launch_name:
                    description_parts.append(
                        f'<p><strong>🔗 Launch ID for Sync:</strong> <code>{rp_launch_name}</code></p>'
                    )
                description_parts.append('<hr/>')
            
            if self.step.plan.summary:
                description_parts.append(f"<strong>Summary:</strong> {html.escape(sanitize_for_xml(self.step.plan.summary))}")
            if self.step.plan.description:
                description_parts.append(f"<strong>Description:</strong><br/>{format_as_html(sanitize_for_xml(self.step.plan.description))}")
            
            # Add environment variables from plan
            if self.step.plan.environment:
                env_items = []
                for key, value in self.step.plan.environment.items():
                    env_items.append(f"<code>{html.escape(sanitize_for_xml(key))}={html.escape(sanitize_for_xml(str(value)))}</code>")
                if env_items:
                    description_parts.append(f"<strong>Environment:</strong><br/>{'<br/>'.join(env_items)}")
            
            # Add provision information - display whatever is available
            try:
                provision_data = self.step.plan.provision.data
                if provision_data and len(provision_data) > 0:
                    guest_data = provision_data[0] if isinstance(provision_data, list) else provision_data
                    
                    prov_items = []
                    
                    # Define fields to display in order, with their display names
                    # This list works across all provision methods (testcloud, beaker, artemis, etc.)
                    fields_to_display = [
                        ('how', 'Method'),
                        ('ansible', 'Ansible'),
                        ('image', 'Image'),
                        ('image_url', 'Image URL'),
                        ('instance_name', 'Name'),
                        ('hardware', 'Effective Hardware'),
                        ('memory', 'Memory'),
                        ('disk', 'Disk'),
                        ('key', 'Key'),
                        ('primary_address', 'Primary Address'),
                        ('topology_address', 'Topology Address'),
                        ('port', 'Port'),
                        ('role', 'Multihost Name'),
                        ('compose', 'Compose'),
                        ('pool', 'Pool'),  # For beaker/artemis
                        ('api_url', 'API URL'),  # For artemis
                    ]
                    
                    # Display regular fields
                    for field_name, display_name in fields_to_display:
                        if hasattr(guest_data, field_name):
                            value = getattr(guest_data, field_name)
                            # Skip None, empty strings, empty lists, empty dicts
                            if value is not None and value != '' and value != [] and value != {}:
                                if isinstance(value, list):
                                    # For lists, join or take first element
                                    if len(value) > 0:
                                        value_str = str(value[0]) if len(value) == 1 else ', '.join(str(v) for v in value)
                                        prov_items.append(f"<strong>{display_name}:</strong> {html.escape(sanitize_for_xml(value_str))}")
                                else:
                                    prov_items.append(f"<strong>{display_name}:</strong> {html.escape(sanitize_for_xml(str(value)))}")
                    
                    # Display facts if available
                    if hasattr(guest_data, 'facts') and guest_data.facts:
                        facts_fields = [
                            ('arch', 'Arch'),
                            ('distro', 'Distro'),
                            ('kernel_release', 'Kernel'),
                        ]
                        for field_name, display_name in facts_fields:
                            if hasattr(guest_data.facts, field_name):
                                value = getattr(guest_data.facts, field_name)
                                if value is not None and value != '':
                                    prov_items.append(f"<strong>{display_name}:</strong> {html.escape(sanitize_for_xml(str(value)))}")
                    
                    if prov_items:
                        description_parts.append(f"<strong>Provision:</strong><br/>{'<br/>'.join(prov_items)}")
            except (AttributeError, TypeError) as e:
                self.debug(f"Error extracting provision information: {e}")
            
            if description_parts:
                description_html = "<br/><br/>".join(description_parts)
                desc_text = Text(content=description_html)
                _set_custom_text_field(test_run, 'description', desc_text)
                self.debug("Set description from plan summary and description")
            
            # Update test run with custom fields
            test_run.update()
            self.info(f'Test run created: {test_run.test_run_id}')
            
            # Set ReportPortal URL AFTER initial update()
            # rplaunchurl is a RICH TEXT (multiline) custom field
            if rp_url:
                try:
                    self.debug(f"Setting rplaunchurl as rich text custom field: {rp_url}")
                    
                    # Create rich text content with clickable link
                    rp_html = f'<a href="{rp_url}">{rp_url}</a>'
                    rp_text = Text(content=rp_html)
                    rp_text._suds_object.type = 'text/html'
                    
                    _set_custom_text_field(test_run, 'rplaunchurl', rp_text)
                    test_run.update()
                    
                    self.info(f"✅ Set ReportPortal launch URL in Polarion rplaunchurl field")
                    self.info(f"ReportPortal URL: {rp_url}", color='cyan')
                    
                    # Also set sync status to false (not yet synced)
                    try:
                        test_run._set_custom_field('syncfinalized', False)
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
                comment_parts.append(format_as_html(log_content))
            
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

        other_testrun_fields = [
            'arch',
            'assignee',
            'build',
            'compose_id',
            'description',
            'fips',
            'logs',
            'planned_in',
            'platform',
            'pool_team',
            'sample_image',
        ]

        testsuites_properties: dict[str, Optional[str]] = {}

        for tr_field in other_testrun_fields:
            param = self.get(tr_field, os.getenv(f'TMT_PLUGIN_REPORT_POLARION_{tr_field.upper()}'))
            # TODO: remove the os.getenv when envvars in click work with steps in plans as well
            # as with steps on cmdline
            if param:
                # Normalize arch for Polarion compatibility (x86_64 -> x8664)
                if tr_field == 'arch':
                    param = normalize_arch(param)
                testsuites_properties[f"polarion-custom-{tr_field.replace('_', '')}"] = param

        if use_facts:
            guests = self.step.plan.provision.ready_guests
            try:
                testsuites_properties['polarion-custom-hostname'] = guests[0].primary_address
                testsuites_properties['polarion-custom-arch'] = normalize_arch(guests[0].facts.arch)
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

        # Add deployment mode if provided as a context variable
        deployment_mode = self.step.plan.fmf_context.get('deployment-mode', [])
        if deployment_mode:
            testsuites_properties.update({'polarion-custom-deploymentMode': deployment_mode[0]})
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
