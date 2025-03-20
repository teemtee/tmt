import datetime
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

    See the ``Pylero Documentation`` for more details on how
    to configure the ``pylero`` module.

    https://github.com/RedHatQE/pylero

    .. note::

        For Polarion report to export correctly you need to
        use password authentication, since exporting the
        report happens through Polarion XUnit importer which
        does not support using tokens. You can still
        authenticate with token to only generate the report
        using ``--no-upload`` argument.

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

        title = self.data.title
        if not title:
            title = os.getenv(
                'TMT_PLUGIN_REPORT_POLARION_TITLE',
                self.step.plan.name.rsplit('/', 1)[1]
                + '_'
                +
                # Polarion server running with UTC timezone
                datetime.datetime.now(tz=datetime.timezone.utc).strftime("%Y%m%d%H%M%S"),
            )

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
                testsuites_properties[f"polarion-custom-{tr_field.replace('_', '')}"] = param

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

        assert self.workdir is not None

        testsuites_properties.update(
            {
                'polarion-project-id': project_id,
                'polarion-user-id': PolarionWorkItem._session.user_id,
                'polarion-testrun-title': title,
                'polarion-project-span-ids': ','.join([project_id, *project_span_ids]),
            }
        )

        # Add deployment mode if provided as a context variable
        deployment_mode = self.step.plan._fmf_context.get('deployment-mode', [])
        if deployment_mode:
            testsuites_properties.update({'polarion-custom-deploymentMode': deployment_mode[0]})

        # ignore[assignment]: mypy does not support different types for property getter
        # and setter. The assignment is correct, but mypy cannot tell.
        # See https://github.com/python/mypy/issues/3004 for getter/setter discussions
        results_context.properties = testsuites_properties  # type: ignore[assignment]

        xml_data = make_junit_xml(
            phase=self,
            flavor='polarion',
            prettify=self.data.prettify,
            include_output_log=self.data.include_output_log,
            results_context=results_context,
        )

        f_path = self.data.file or self.workdir / DEFAULT_FILENAME

        try:
            f_path.write_text(xml_data)
        except Exception as error:
            raise tmt.utils.ReportError(f"Failed to write the output '{f_path}'.") from error

        if upload:
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
