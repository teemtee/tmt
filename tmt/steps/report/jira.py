"""
Report tmt test results to Jira as TestResult subtask comments.
"""

import os
from typing import Any, Optional

import requests

import tmt.log
import tmt.steps
import tmt.steps.report
import tmt.utils
from tmt.container import container, field
from tmt.export.jira import (
    _api_request,
    _make_session,
    _resolve_account_id,
)
from tmt.result import Result, ResultOutcome
from tmt.utils import Command, ConvertError, ReportError

# TestResult issue type ID in RHELTEST
ISSUE_TYPE_TEST_RESULT = '10300'

# TestResult workflow transition IDs
TRANSITION_PASS = '2'
TRANSITION_FAIL = '3'
TRANSITION_BLOCKED = '4'

# Maximum comments per TestResult subtask before opening a new one
COMMENT_LIMIT = 4900

# Maximum failure strings and per-string length included in a comment
MAX_FAILURES = 20
MAX_FAILURE_LINE_LEN = 200

# Jira custom fields (RHELTEST)
FIELD_COMPONENT_NVR = 'customfield_10742'  # Component Fix Version(s)

# Issue link type for test case → requirement
LINK_TYPE_TESTS = 'pair'

# Outcome → transition mapping
_OUTCOME_TRANSITION = {
    ResultOutcome.PASS: TRANSITION_PASS,
    ResultOutcome.FAIL: TRANSITION_FAIL,
    ResultOutcome.ERROR: TRANSITION_FAIL,
    ResultOutcome.WARN: TRANSITION_BLOCKED,
    ResultOutcome.SKIP: TRANSITION_BLOCKED,
    ResultOutcome.PENDING: TRANSITION_BLOCKED,
}

# Outcome → ADF text color
_OUTCOME_COLOR = {
    ResultOutcome.PASS: '#00875A',
    ResultOutcome.FAIL: '#DE350B',
    ResultOutcome.ERROR: '#DE350B',
    ResultOutcome.WARN: '#FF991F',
    ResultOutcome.SKIP: '#6B778C',
    ResultOutcome.PENDING: '#6B778C',
}


@container
class ReportJiraData(tmt.steps.report.ReportStepData):
    url: Optional[str] = field(
        default=None,
        option='--url',
        metavar='URL',
        help="""
             Jira instance base URL, e.g. ``https://issues.redhat.com``.
             Also uses ``TMT_PLUGIN_REPORT_JIRA_URL``.
             """,
    )

    token: Optional[str] = field(
        default=None,
        option='--token',
        metavar='TOKEN',
        help="""
             Jira API token for HTTP Basic authentication.
             Also uses ``TMT_PLUGIN_REPORT_JIRA_TOKEN``.
             """,
    )

    user: Optional[str] = field(
        default=None,
        option='--user',
        metavar='EMAIL',
        help="""
             Jira user email address for HTTP Basic authentication.
             Also uses ``TMT_PLUGIN_REPORT_JIRA_USER``.
             """,
    )

    project_id: Optional[str] = field(
        default=None,
        option='--project-id',
        metavar='ID',
        help="""
             Jira project key, e.g. ``RHELTEST``.
             Also uses ``TMT_PLUGIN_REPORT_JIRA_PROJECT_ID``.
             """,
    )

    compose_id: Optional[str] = field(
        default=None,
        option='--compose-id',
        metavar='ID',
        help="""
             Compose ID of the image used for this run,
             e.g. ``RHEL-10.3-20260817.0``. Written into each result
             comment and used to derive the distro version when
             ``--fix-version`` is not set.
             Also uses ``TMT_PLUGIN_REPORT_JIRA_COMPOSE_ID`` or
             ``TMT_COMPOSE_ID``.
             """,
    )

    component_nvr: Optional[str] = field(
        default=None,
        option='--component-nvr',
        metavar='NVR',
        help="""
             Override the package NVR instead of querying the guest's
             package manager for it. When neither this option nor the
             fmf ``component`` key is set, the NVR is omitted and
             results are grouped by distro version only.
             """,
    )

    fix_version: Optional[str] = field(
        default=None,
        option='--fix-version',
        metavar='VERSION',
        help="""
             Override the distro x.y version used for ``Test Result``
             grouping, e.g. ``rhel-10.3``. When not set the version is
             read from guest ``os-release`` facts.
             Also uses ``TMT_PLUGIN_REPORT_JIRA_FIX_VERSION``.
             """,
    )

    logs: Optional[str] = field(
        default=None,
        option='--logs',
        metavar='URL',
        help="""
             URL of the logs for this run. Written into each result comment.
             Also uses ``TMT_PLUGIN_REPORT_JIRA_LOGS`` or
             ``TMT_REPORT_ARTIFACTS_URL``.
             """,
    )

    assignee: Optional[str] = field(
        default=None,
        option='--assignee',
        metavar='EMAIL',
        help="""
             Assignee for newly created ``Test Result`` subtasks.
             Also uses ``TMT_PLUGIN_REPORT_JIRA_ASSIGNEE``.
             """,
    )


@tmt.steps.provides_method('jira')
class ReportJira(tmt.steps.report.ReportPlugin[ReportJiraData]):
    """
    Report test results to Jira as ``Test Result`` subtask comments.

    For each test case that has a corresponding ``Test Case`` issue in
    Jira (located via an ``implements`` link or the ``ID`` custom field),
    a numbered ``Test Result`` subtask is created or reused per unique
    combination of distro version and package NVR. Individual test run
    results are appended as comments on that subtask. The distro version
    is read from guest ``os-release`` facts. The package NVR is queried
    from the guest's package manager (``rpm`` or ``apt``) using the
    ``component`` key of the fmf test metadata; when no component is
    defined the NVR is omitted and results are grouped by distro
    version only.

    The ``url``, ``user``, ``token`` and ``project-id`` keys are all
    required. Credentials can also be provided via the corresponding
    ``TMT_PLUGIN_REPORT_JIRA_*`` environment variables.

    .. note::

        Run ``tmt tests export --how jira --link-jira`` first to
        create the ``Test Case`` issues and write the ``implements``
        links back into the fmf metadata. Without those links the
        report plugin falls back to UUID-based lookup.

    .. code-block:: yaml

        report:
            how: jira
            url: https://issues.redhat.com
            user: me@example.com
            token: <api-token>
            project-id: RHELTEST
            compose-id: RHEL-10.3-20260817.0

    .. code-block:: shell

        tmt run report --how jira \\
            --url https://issues.redhat.com \\
            --user me@example.com --token TOKEN \\
            --project-id RHELTEST --compose-id RHEL-10.3-20260817.0
    """

    _data_class = ReportJiraData

    def _resolve(self, field_name: str, *env_vars: str) -> Optional[str]:
        """Return the first non-empty value from data field or env vars."""
        value = getattr(self.data, field_name)
        if value:
            return str(value)
        for var in env_vars:
            value = os.environ.get(var)
            if value:
                return value
        return None

    def _distro_xy(self, guest: Any) -> Optional[str]:
        """
        Extract distro x.y string from guest os-release facts.

        Returns e.g. 'rhel-10.2', 'fedora-42', 'ubuntu-24.04'.
        Falls back to None when facts are unavailable.
        """
        distro_id = guest.facts.os_release_content.get('ID')
        version_id = guest.facts.os_release_content.get('VERSION_ID')
        if distro_id and version_id:
            return f'{distro_id}-{version_id}'
        return None

    def _query_nvr(self, guest: Any, component: str) -> Optional[str]:
        """
        Query the installed package version from the guest.

        tmt's package manager abstraction has no method for this (it
        only covers install/presence/repository queries), so the
        command is picked directly based on the guest's package
        manager: not every distribution has ``rpm`` available (e.g.
        Debian/Ubuntu use ``apt``/``dpkg``).
        """
        package_manager = guest.package_manager.NAME

        if package_manager in ('dnf', 'dnf5', 'yum', 'rpm-ostree'):
            command = Command('rpm', '-q', component, '--queryformat', '%{NVR}')
        elif package_manager == 'apt':
            command = Command('dpkg-query', '-W', '-f=${Package}-${Version}', component)
        else:
            self.warn(
                f"Don't know how to query an installed package version "
                f"for the '{package_manager}' package manager."
            )
            return None

        try:
            output = guest.execute(command, silent=True)
            return output.stdout.strip() if output.stdout else None
        except tmt.utils.RunError:
            self.warn(f"Could not query version of '{component}' on guest.")
            return None

    def _read_failures(self, result: Result) -> list[str]:
        """
        Extract short failure strings from result.failure_logs YAML files.

        Mirrors the 'failures' Jinja filter used by the JUnit report plugin.
        """
        failures: list[str] = []
        for path in result.failure_logs:
            try:
                content = self.step.plan.execute.read(path)
                failures += tmt.utils.yaml_to_list(content)
            except tmt.utils.FileError:
                self.warn(f"Could not read failure log: '{path}'")
        truncated = 0
        if len(failures) > MAX_FAILURES:
            truncated = len(failures) - MAX_FAILURES
            failures = failures[:MAX_FAILURES]
        failures = [str(f)[:MAX_FAILURE_LINE_LEN] for f in failures]
        if truncated:
            failures.append(f'... and {truncated} more (see logs)')
        return failures

    def _build_comment_adf(
        self,
        compose: Optional[str],
        outcome: ResultOutcome,
        arch: Optional[str],
        duration: Optional[str],
        logs_url: Optional[str],
        failures: list[str],
    ) -> dict[str, Any]:
        """Build the ADF comment body for a result."""

        def _para(text: str) -> dict[str, Any]:
            return {
                'type': 'paragraph',
                'content': [{'type': 'text', 'text': text}],
            }

        content: list[dict[str, Any]] = []

        if compose:
            content.append(_para(f'Compose:  {compose}'))

        color = _OUTCOME_COLOR.get(outcome, '#6B778C')
        content.append(
            {
                'type': 'paragraph',
                'content': [
                    {'type': 'text', 'text': 'Outcome:  '},
                    {
                        'type': 'text',
                        'text': outcome.value.upper(),
                        'marks': [{'type': 'textColor', 'attrs': {'color': color}}],
                    },
                ],
            }
        )

        if arch:
            content.append(_para(f'Arch:     {arch}'))
        if duration:
            content.append(_para(f'Duration: {duration}'))
        if logs_url:
            content.append(_para(f'Logs:     {logs_url}'))
        if failures:
            content.append(_para(f'Failures: {failures[0]}'))
            content.extend(_para(f'          {f}') for f in failures[1:])

        return {'type': 'doc', 'version': 1, 'content': content}

    def _find_or_create_skeleton(
        self,
        session: requests.Session,
        api_base: str,
        testcase_key: str,
        distro_xy: str,
        nvr: Optional[str],
    ) -> str:
        """
        Return the key of a TestResult subtask for (testcase, distro_xy[, nvr]).

        When ``nvr`` is ``None`` the subtask is identified by distro only.
        Fetches all matching subtasks ordered newest first. Picks the first
        one with room for more comments. Creates a new numbered skeleton if
        all are full or none exist.
        """
        nvr_clause = f' AND cf[10742]="{nvr}"' if nvr else ' AND cf[10742] is EMPTY'
        response = _api_request(
            session,
            'POST',
            f'{api_base}/search/jql',
            json={
                'jql': (
                    f'project="{self.data.project_id}" AND issuetype="Test Result"'
                    f' AND parent="{testcase_key}"'
                    f' AND fixVersion="{distro_xy}"'
                    f'{nvr_clause}'
                    ' ORDER BY created DESC'
                ),
                'maxResults': 100,
                'fields': ['summary', 'status', 'comment'],
            },
        )
        all_subtasks = response.get('issues', [])

        # Find the first subtask that still has room for comments
        for subtask in all_subtasks:
            comment_count = subtask['fields']['comment']['total']
            if comment_count < COMMENT_LIMIT:
                return str(subtask['key'])

        # All full or none exist — create a new numbered skeleton
        next_index = len(all_subtasks)
        summary = f'{distro_xy} / {nvr} ({next_index})' if nvr else f'{distro_xy} ({next_index})'
        fields: dict[str, Any] = {
            'project': {'key': self.data.project_id},
            'parent': {'key': testcase_key},
            'issuetype': {'id': ISSUE_TYPE_TEST_RESULT},
            'summary': summary,
            'fixVersions': [{'name': distro_xy}],
            'labels': ['Automated'],
        }
        if nvr:
            fields[FIELD_COMPONENT_NVR] = nvr
        if self.data.assignee:
            account_id = _resolve_account_id(session, api_base, self.data.assignee)
            if account_id:
                fields['assignee'] = {'accountId': account_id}
            else:
                self.warn(f"Could not resolve Jira account for '{self.data.assignee}'.")
        resp = _api_request(session, 'POST', f'{api_base}/issue', json={'fields': fields})
        key = str(resp['key'])
        self.info(f"Created TestResult skeleton '{key}': {summary}")
        return key

    def _add_comment(
        self,
        session: requests.Session,
        api_base: str,
        testresult_key: str,
        body_adf: dict[str, Any],
    ) -> None:
        """Add a result comment to a TestResult subtask, truncating failures on 400."""
        try:
            _api_request(
                session,
                'POST',
                f'{api_base}/issue/{testresult_key}/comment',
                json={'body': body_adf},
            )
        except ConvertError as err:
            if '400' not in str(err):
                raise
            # Comment too large — retry without the Failures section
            self.warn(f"Comment too large for '{testresult_key}', retrying without failures.")
            content = body_adf.get('content', [])
            trimmed_content = [
                p
                for p in content
                if not any('Failures:' in t.get('text', '') for t in p.get('content', []))
            ]
            trimmed_content.append(
                {
                    'type': 'paragraph',
                    'content': [{'type': 'text', 'text': 'Failures: omitted — see logs'}],
                }
            )
            body_adf['content'] = trimmed_content
            _api_request(
                session,
                'POST',
                f'{api_base}/issue/{testresult_key}/comment',
                json={'body': body_adf},
            )

    def _transition(
        self,
        session: requests.Session,
        api_base: str,
        key: str,
        outcome: ResultOutcome,
        current_status: str,
    ) -> None:
        """Transition a TestResult subtask to reflect the latest outcome."""
        transition_id = _OUTCOME_TRANSITION.get(outcome, TRANSITION_BLOCKED)
        target = {TRANSITION_PASS: 'PASS', TRANSITION_FAIL: 'FAIL', TRANSITION_BLOCKED: 'Blocked'}[
            transition_id
        ]
        if current_status == target:
            return
        _api_request(
            session,
            'POST',
            f'{api_base}/issue/{key}/transitions',
            json={'transition': {'id': transition_id}},
        )

    def _find_jira_case_key(
        self,
        result_ids: dict[str, Optional[str]],
        session: requests.Session,
        api_base: str,
    ) -> Optional[str]:
        """Look up a Jira TestCase key by UUID (customfield_10591)."""
        uuid = result_ids.get('id')
        if not uuid:
            return None
        response = _api_request(
            session,
            'POST',
            f'{api_base}/search/jql',
            json={
                'jql': (
                    f'project="{self.data.project_id}" AND issuetype="Test Case"'
                    f' AND cf[10591]="{uuid}"'
                ),
                'maxResults': 1,
                'fields': ['summary'],
            },
        )
        issues = response.get('issues', [])
        return issues[0]['key'] if issues else None

    def go(self, *, logger: Optional[tmt.log.Logger] = None) -> None:
        """Process results and report them to Jira."""
        super().go(logger=logger)

        if self.is_dry_run:
            return

        # Resolve required config
        url = (self._resolve('url', 'TMT_PLUGIN_REPORT_JIRA_URL') or '').rstrip('/')
        token = self._resolve('token', 'TMT_PLUGIN_REPORT_JIRA_TOKEN') or ''
        user = self._resolve('user', 'TMT_PLUGIN_REPORT_JIRA_USER') or ''
        project_id = self._resolve('project_id', 'TMT_PLUGIN_REPORT_JIRA_PROJECT_ID') or ''

        missing = [
            name
            for name, val in [
                ('--url / TMT_PLUGIN_REPORT_JIRA_URL', url),
                ('--token / TMT_PLUGIN_REPORT_JIRA_TOKEN', token),
                ('--user / TMT_PLUGIN_REPORT_JIRA_USER', user),
                ('--project-id / TMT_PLUGIN_REPORT_JIRA_PROJECT_ID', project_id),
            ]
            if not val
        ]
        if missing:
            raise ReportError(f"Missing required Jira options: {', '.join(missing)}.")

        # Bind project_id into data so _find_or_create_skeleton can use it
        self.data.project_id = project_id

        compose_id = self._resolve(
            'compose_id', 'TMT_PLUGIN_REPORT_JIRA_COMPOSE_ID', 'TMT_COMPOSE_ID'
        )
        logs_url = self._resolve('logs', 'TMT_PLUGIN_REPORT_JIRA_LOGS', 'TMT_REPORT_ARTIFACTS_URL')

        api_base = f'{url}/rest/api/3'
        session = _make_session(user, token)

        browse_prefix = f'{url}/browse/'

        # --- Pre-processing pass ---
        # Build maps: test name → Jira TestCase key, test name → component
        test_to_jira: dict[str, str] = {}
        test_to_component: dict[str, Optional[str]] = {}

        for origin in self.step.plan.discover.tests():
            test = origin.test
            test_to_component[test.name] = test.component[0] if test.component else None
            if test.link:
                for link in test.link.get('implements'):
                    target = str(link.target)
                    if target.startswith(browse_prefix):
                        test_to_jira[test.name] = target[len(browse_prefix) :]
                        break

        # Index ready guests by name
        guests = {g.name: g for g in self.step.plan.provision.ready_guests}

        results = self.step.plan.execute.results()

        # Resolve Jira key, NVR, and distro per result
        for result in results:
            # Jira TestCase key
            if result.name in test_to_jira:
                result.ids['jira'] = test_to_jira[result.name]
            else:
                key = self._find_jira_case_key(result.ids, session, api_base)
                if key:
                    result.ids['jira'] = key
                else:
                    self.warn(f"No Jira TestCase found for '{result.name}', skipping.")
                    continue

            # Guest for this result
            guest = guests.get(result.guest.name) if result.guest else None
            if guest is None and guests:
                guest = next(iter(guests.values()))

            # NVR
            resolved_nvr = self.data.component_nvr
            if not resolved_nvr and guest:
                component = test_to_component.get(result.name)
                if component:
                    resolved_nvr = self._query_nvr(guest, component)
            result.ids['nvr'] = resolved_nvr or ''

            # Distro x.y
            distro_xy = self._resolve('fix_version', 'TMT_PLUGIN_REPORT_JIRA_FIX_VERSION')
            if not distro_xy and guest:
                distro_xy = self._distro_xy(guest)
            result.ids['distro_xy'] = distro_xy or ''

        # --- Main reporting loop ---
        counts: dict[str, int] = {'pass': 0, 'fail': 0, 'blocked': 0, 'skipped': 0}

        for result in results:
            if 'jira' not in result.ids:
                counts['skipped'] += 1
                continue

            testcase_key = str(result.ids['jira'])
            nvr: Optional[str] = result.ids.get('nvr') or None
            distro_xy = result.ids.get('distro_xy', '')

            if not distro_xy:
                self.warn(f"Missing distro x.y for '{result.name}', skipping.")
                counts['skipped'] += 1
                continue

            # Find or create skeleton
            testresult_key = self._find_or_create_skeleton(
                session, api_base, testcase_key, distro_xy, nvr
            )

            # Arch from guest facts
            arch: Optional[str] = None
            guest = guests.get(result.guest.name) if result.guest else None
            if guest is None and guests:
                guest = next(iter(guests.values()))
            if guest:
                arch = guest.facts.arch

            # Failure strings
            failures = self._read_failures(result)

            # Build and post comment
            body_adf = self._build_comment_adf(
                compose_id,
                result.result,
                arch,
                result.duration,
                logs_url,
                failures,
            )
            self._add_comment(session, api_base, testresult_key, body_adf)

            # Get current status of the subtask for transition check
            subtask_info = _api_request(
                session,
                'GET',
                f'{api_base}/issue/{testresult_key}?fields=status',
            )
            current_status = subtask_info['fields']['status']['name']
            self._transition(session, api_base, testresult_key, result.result, current_status)

            # Track counts
            outcome = result.result
            if outcome == ResultOutcome.PASS:
                counts['pass'] += 1
            elif outcome in (ResultOutcome.FAIL, ResultOutcome.ERROR):
                counts['fail'] += 1
            else:
                counts['blocked'] += 1

            self.info(f"[{result.result.value.upper()}] {result.name} → {testresult_key}")

        self.info(
            f"Jira report: {counts['pass']} PASS, {counts['fail']} FAIL, "
            f"{counts['blocked']} Blocked, {counts['skipped']} skipped."
        )
