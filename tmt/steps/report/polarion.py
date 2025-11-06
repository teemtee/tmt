import datetime
import html
import os
from typing import Optional

from requests import post

import tmt
import tmt.steps
import tmt.steps.report
import tmt.utils
from tmt.container import container, field
from tmt.utils import Path

from .junit import ResultsContext, make_junit_xml

DEFAULT_FILENAME = 'xunit.xml'
DEFAULT_TEMPLATE = 'Empty'  # Default Polarion test run template


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
             Use specific test run template (default: 'Empty'),
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


def format_as_html(text: str) -> str:
    """
    Format text as HTML with proper escaping and preformatted styling.
    
    Args:
        text: Plain text to format
        
    Returns:
        HTML-formatted text with proper escaping
    """
    if not text:
        return ""
    escaped = html.escape(text)
    return f'<pre>{escaped}</pre>'


@tmt.steps.provides_method('polarion')
class ReportPolarion(tmt.steps.report.ReportPlugin[ReportPolarionData]):
    """
    Write test results into an xUnit file and upload to Polarion.

    In order to get quickly started create a pylero config
    file ``~/.pylero`` in your home directory with the
    following content.

    **Token Authentication** (recommended):

    .. code-block:: ini

        [webservice]
        url=https://{your polarion web URL}/polarion
        svn_repo=https://{your polarion web URL}/repo
        default_project={your project name}
        token={your personal access token}

    **Password Authentication**:

    .. code-block:: ini

        [webservice]
        url=https://{your polarion web URL}/polarion
        svn_repo=https://{your polarion web URL}/repo
        default_project={your project name}
        user={your username}
        password={your password}

    See the ``Pylero Documentation`` for more details on how
    to configure the ``pylero`` module.

    https://github.com/RedHatQE/pylero

    .. note::

        Test run upload supports both token and password authentication.
        Results are uploaded using pylero's TestRun API. An XUnit file
        is also generated for reference.

    .. note::

        Your Polarion project might need a custom value format
        for the ``arch``, ``planned-in`` and other fields. The
        format of these fields might differ across Polarion
        projects, for example, ``x8664`` can be used instead
        of ``x86_64`` for the architecture.

    Examples:

    .. code-block:: yaml

        # Enable polarion report from the command line
        tmt run --all report --how polarion --project-id tmt
        tmt run --all report --how polarion --project-id tmt --no-upload --file test.xml

    .. code-block:: yaml

        # Use polarion as the default report for given plan
        report:
            how: polarion
            file: test.xml
            project-id: tmt
            title: tests_that_pass
            template: Empty  # Optional: default is 'Empty'
            planned-in: RHEL-9.1.0
            pool-team: sst_tmt
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

    def go(self, *, logger: Optional[tmt.log.Logger] = None) -> None:
        """
        Go through executed tests and report into Polarion
        """

        super().go(logger=logger)

        from tmt.export.polarion import find_polarion_case_ids, import_polarion

        import_polarion()
        from tmt.export.polarion import PolarionWorkItem

        # Get title from data, env, or generate from plan name
        title = self.data.title
        if not title:
            # If no title specified, generate from plan name and optionally include summary
            base_title = self.step.plan.name.rsplit('/', 1)[1]
            
            # Add plan summary to title if available (description field doesn't work)
            if self.step.plan.summary:
                # Keep title concise - limit to first 100 chars of summary
                summary_short = self.step.plan.summary[:100]
                if len(self.step.plan.summary) > 100:
                    summary_short += "..."
                title = f"{base_title}: {summary_short}"
            else:
                title = base_title + '_' + datetime.datetime.now(tz=datetime.timezone.utc).strftime("%Y%m%d%H%M%S")
            
            # Also check environment variable
            title = os.getenv('TMT_PLUGIN_REPORT_POLARION_TITLE', title)

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
                # Transform x86_64 to x8664 for Polarion compatibility
                if tr_field == 'arch' and param == 'x86_64':
                    param = 'x8664'
                testsuites_properties[f"polarion-custom-{tr_field.replace('_', '')}"] = param

        if use_facts:
            guests = self.step.plan.provision.ready_guests
            try:
                testsuites_properties['polarion-custom-hostname'] = guests[0].primary_address
                arch = guests[0].facts.arch
                if arch == 'x86_64':
                    arch = 'x8664'
                testsuites_properties['polarion-custom-arch'] = arch
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

        if upload:
            # Use pylero API to create test run directly (supports both token and password auth)
            from pylero.test_run import TestRun
            
            try:
                # Create test run
                template_to_use = template or DEFAULT_TEMPLATE
                test_run = TestRun.create(
                    project_id=project_id,
                    template=template_to_use,
                    title=title,
                )
                
                # Reload test run to ensure it's fully initialized before setting fields
                test_run = TestRun(project_id=project_id, test_run_id=test_run.test_run_id)
                
                # Set test run metadata
                # Set group_id (direct attribute)
                if testsuites_properties.get('polarion-custom-poolteam'):
                    test_run.group_id = testsuites_properties['polarion-custom-poolteam']
                
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
                        try:
                            test_run._set_custom_field(field_name, value)
                        except Exception as e:
                            self.warn(f"Could not set {field_name}={value}: {e}")
                
                # Check if ReportPortal was used and add the launch URL
                try:
                    if hasattr(self.step, 'workdir'):
                        for report in self.step.plan.report.phases():
                            if report.how == 'reportportal' and hasattr(report.data, 'launch_url'):
                                rp_url = report.data.launch_url
                                if rp_url:
                                    test_run._set_custom_field('rplaunchurl', rp_url)
                except Exception as e:
                    self.warn(f"Could not set ReportPortal URL: {e}")
                
                # Update test run with custom fields
                # Note: description field is not set - it causes "type cannot be null" error
                # Plan summary is included in the title instead
                test_run.update()
                
                # Add test records for each result
                for result in results_context:
                    if not result.ids or not any(result.ids.values()):
                        continue
                    
                    work_item_id, test_project_id = find_polarion_case_ids(result.ids)
                    if not work_item_id:
                        continue
                    
                    # Map tmt result to Polarion result
                    if hasattr(result.result, 'name'):
                        result_str = result.result.name.lower()
                    else:
                        result_str = str(result.result).split('.')[-1].lower()
                    
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
                    
                    # Convert duration to seconds
                    try:
                        duration_seconds = float(result.duration) if result.duration else 0.0
                    except (ValueError, TypeError):
                        duration_seconds = 0.0
                    
                    # Build test comment with output
                    comment_parts = []
                    if result.note:
                        comment_parts.append(result.note)
                    
                    # Add test output/log
                    if hasattr(result, 'log') and result.log:
                        log_content = None
                        
                        if isinstance(result.log, list):
                            for log_path in result.log:
                                if isinstance(log_path, (str, Path)):
                                    log_path = Path(log_path)
                                    if not log_path.is_absolute():
                                        log_path = self.step.plan.execute.workdir / log_path
                                    if log_path.name == 'output.txt' and log_path.exists():
                                        try:
                                            log_content = log_path.read_text()
                                            break
                                        except Exception as e:
                                            self.warn(f"Could not read log file {log_path}: {e}")
                        elif isinstance(result.log, Path):
                            try:
                                log_content = result.log.read_text()
                            except Exception as e:
                                self.warn(f"Could not read log file: {e}")
                        elif isinstance(result.log, str):
                            log_content = result.log
                        
                        if log_content:
                            if comment_parts:
                                comment_parts.append('\n---\nTest Output:\n')
                            comment_parts.append(format_as_html(log_content))
                    
                    test_comment = ''.join(comment_parts)
                    
                    # Add test record
                    test_run.add_test_record_by_fields(
                        test_case_id=work_item_id,
                        test_result=test_result,
                        test_comment=test_comment,
                        executed_by=PolarionWorkItem._session.user_id,
                        executed=datetime.datetime.now(tz=datetime.timezone.utc),
                        duration=duration_seconds,
                    )
                
                self.info(f'Test run created: {test_run.test_run_id}')
                server_url = str(PolarionWorkItem._session._server.url)
                test_run_url = (
                    f'{server_url}{"" if server_url.endswith("/") else "/"}'
                    f'#/project/{project_id}/testrun?id={test_run.test_run_id}'
                )
                self.info(f'URL: {test_run_url}')
                
            except Exception as error:
                raise tmt.utils.ReportError(
                    f"Failed to create test run in Polarion: {error}"
                ) from error
        
        self.info('xUnit file saved at', f_path, 'yellow')
