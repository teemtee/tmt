import shutil
import unittest.mock
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from tests import CliRunner, reset_common
from tmt.result import ResultOutcome
from tmt.steps.report.jira import (
    TRANSITION_FAIL,
    TRANSITION_PASS,
    ReportJira,
)
from tmt.utils import Command, CommandOutput, Path, RunError

DATA_DIR = Path(__file__).parent.parent / 'report' / 'jira' / 'data'


def _flatten_adf(adf: dict[str, Any]) -> list[str]:
    return [''.join(span['text'] for span in paragraph['content']) for paragraph in adf['content']]


class FakeGuestFacts:
    def __init__(self, os_release_content: dict[str, str], arch: str) -> None:
        self.os_release_content = os_release_content
        self.arch = arch


class FakeGuest:
    def __init__(self, os_release_content: dict[str, str], arch: str = 'x86_64') -> None:
        self.facts = FakeGuestFacts(os_release_content, arch)


@pytest.fixture(name='plugin')
def fixture_plugin() -> ReportJira:
    # Bare instance: _build_comment_adf, _distro_xy and _resolve don't touch
    # any step/plan machinery, only self.data for _resolve.
    return ReportJira.__new__(ReportJira)


class TestBuildCommentAdf:
    def test_minimal(self, plugin: ReportJira) -> None:
        adf = plugin._build_comment_adf(None, ResultOutcome.PASS, None, None, None, [])
        assert _flatten_adf(adf) == ['Outcome:  PASS']

    def test_full_with_failures(self, plugin: ReportJira) -> None:
        adf = plugin._build_comment_adf(
            'RHEL-10.3-20260817.0',
            ResultOutcome.FAIL,
            'x86_64',
            '00:00:05',
            'https://logs.example/1',
            ['boom: assertion failed', 'second failure'],
        )
        assert _flatten_adf(adf) == [
            'Compose:  RHEL-10.3-20260817.0',
            'Outcome:  FAIL',
            'Arch:     x86_64',
            'Duration: 00:00:05',
            'Logs:     https://logs.example/1',
            'Failures: boom: assertion failed',
            '          second failure',
        ]

    def test_outcome_color_mark(self, plugin: ReportJira) -> None:
        adf = plugin._build_comment_adf(None, ResultOutcome.FAIL, None, None, None, [])
        colored_span = adf['content'][0]['content'][1]
        assert colored_span['marks'][0]['attrs']['color'] == '#DE350B'


class TestDistroXY:
    def test_present(self, plugin: ReportJira) -> None:
        guest = FakeGuest({'ID': 'rhel', 'VERSION_ID': '10.3'})
        assert plugin._distro_xy(guest) == 'rhel-10.3'

    def test_missing_facts(self, plugin: ReportJira) -> None:
        guest = FakeGuest({'ID': 'rhel'})
        assert plugin._distro_xy(guest) is None


class FakePackageManager:
    def __init__(self, name: str) -> None:
        self.NAME = name


class FakeGuestWithPackageManager:
    def __init__(self, package_manager_name: str, stdout: Any = 'bash-5.2.21-2ubuntu4') -> None:
        self.package_manager = FakePackageManager(package_manager_name)
        self._stdout = stdout
        self.executed_command: Any = None

    def execute(self, command: Any, silent: bool = False) -> CommandOutput:
        self.executed_command = command
        if isinstance(self._stdout, Exception):
            raise self._stdout
        return CommandOutput(stdout=self._stdout, stderr=None)


class TestQueryNvr:
    def test_rpm_based(self, plugin: ReportJira) -> None:
        guest = FakeGuestWithPackageManager('dnf', stdout='bash-5.2.15-3.fc38')
        assert plugin._query_nvr(guest, 'bash') == 'bash-5.2.15-3.fc38'
        assert str(guest.executed_command).startswith('rpm ')

    def test_apt_based(self, plugin: ReportJira) -> None:
        guest = FakeGuestWithPackageManager('apt', stdout='bash-5.2.21-2ubuntu4')
        assert plugin._query_nvr(guest, 'bash') == 'bash-5.2.21-2ubuntu4'
        assert str(guest.executed_command).startswith('dpkg-query ')

    def test_unsupported_package_manager_warns_and_skips(self, plugin: ReportJira) -> None:
        plugin.warn = MagicMock()
        guest = FakeGuestWithPackageManager('apk')
        assert plugin._query_nvr(guest, 'bash') is None
        assert guest.executed_command is None
        plugin.warn.assert_called_once()

    def test_run_error_warns_and_returns_none(self, plugin: ReportJira) -> None:
        plugin.warn = MagicMock()
        error = RunError('failed', Command('rpm', '-q', 'bash'), 1)
        guest = FakeGuestWithPackageManager('dnf', stdout=error)
        assert plugin._query_nvr(guest, 'bash') is None
        plugin.warn.assert_called_once()


class TestResolve:
    def test_field_takes_priority_over_env(
        self, plugin: ReportJira, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        plugin.data = SimpleNamespace(url='https://cli.example')
        monkeypatch.setenv('TMT_PLUGIN_REPORT_JIRA_URL', 'https://env.example')
        assert plugin._resolve('url', 'TMT_PLUGIN_REPORT_JIRA_URL') == 'https://cli.example'

    def test_env_fallback(self, plugin: ReportJira, monkeypatch: pytest.MonkeyPatch) -> None:
        plugin.data = SimpleNamespace(url=None)
        monkeypatch.setenv('TMT_PLUGIN_REPORT_JIRA_URL', 'https://env.example')
        assert plugin._resolve('url', 'TMT_PLUGIN_REPORT_JIRA_URL') == 'https://env.example'

    def test_none_when_unset(self, plugin: ReportJira, monkeypatch: pytest.MonkeyPatch) -> None:
        plugin.data = SimpleNamespace(url=None)
        monkeypatch.delenv('TMT_PLUGIN_REPORT_JIRA_URL', raising=False)
        assert plugin._resolve('url', 'TMT_PLUGIN_REPORT_JIRA_URL') is None


class FakeJiraApi:
    """Records and answers calls normally made through ``_api_request``."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any]]] = []
        self.case_keys: dict[str, str] = {}
        self.skeleton_search_result: dict[str, Any] = {'issues': []}
        self.skeleton_create_result: dict[str, Any] = {'key': 'RHELTEST-500'}
        self.current_status = 'New'

    def __call__(self, session: MagicMock, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        payload = kwargs.get('json', {})
        self.calls.append((method, url, payload))

        if url.endswith('/search/jql'):
            jql = payload.get('jql', '')
            if 'issuetype="Test Case"' in jql:
                for uuid, key in self.case_keys.items():
                    if f'cf[10591]="{uuid}"' in jql:
                        return {'issues': [{'key': key}]}
                return {'issues': []}
            return self.skeleton_search_result
        if method == 'POST' and url.endswith('/issue'):
            return self.skeleton_create_result
        if url.split('?', maxsplit=1)[0].endswith('/status') or '?fields=status' in url:
            return {'fields': {'status': {'name': self.current_status}}}
        return {}

    def calls_matching(self, method: str, suffix: str) -> list[dict[str, Any]]:
        return [
            payload
            for m, url, payload in self.calls
            if m == method and url.split('?')[0].endswith(suffix)
        ]


@pytest.fixture(name='jira_api')
def fixture_jira_api() -> FakeJiraApi:
    return FakeJiraApi()


@pytest.fixture(autouse=True)
def _mock_network(jira_api: FakeJiraApi) -> Any:
    with (
        unittest.mock.patch('tmt.steps.report.jira._make_session', return_value=MagicMock()),
        unittest.mock.patch('tmt.steps.report.jira._api_request', side_effect=jira_api),
    ):
        yield
    # CliRunner options are cached on Common-derived classes; clean up so a
    # test module collected after this one (e.g. via `pytest tests/unit`)
    # doesn't inherit them.
    reset_common()


@pytest.fixture(name='plan_dir')
def fixture_plan_dir(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    reset_common()
    root = Path(tmp_path) / 'tree'
    shutil.copytree(DATA_DIR, root)
    monkeypatch.chdir(root)
    return root


CREDENTIALS = [
    '--url',
    'https://issues.redhat.com',
    '--user',
    'me@example.com',
    '--token',
    'dummy',
    '--project-id',
    'RHELTEST',
]


def run_report(test_filter: str, extra_args: list[str] = ()) -> Any:
    return CliRunner().invoke(
        '--feeling-safe',
        'run',
        'provision',
        '--how',
        'local',
        'discover',
        '--how',
        'fmf',
        '--test',
        test_filter,
        'execute',
        'report',
        '--how',
        'jira',
        *CREDENTIALS,
        *extra_args,
    )


class TestReportJiraGo:
    def test_missing_options_fails(self, plan_dir: Any) -> None:
        result = CliRunner().invoke(
            '--feeling-safe',
            'run',
            'provision',
            '--how',
            'local',
            'discover',
            '--how',
            'fmf',
            '--test',
            '/test/pass$',
            'execute',
            'report',
            '--how',
            'jira',
        )
        assert result.exit_code != 0
        # tmt.cli._root.main is invoked directly here, bypassing the
        # exception-formatting wrapper in tmt.__main__.run_cli(); the real
        # ReportError ends up chained as __cause__ of Run.go()'s
        # GeneralError('plan failed.').
        assert result.exception is not None
        assert 'Missing required Jira options' in str(result.exception.__cause__)

    def test_report_pass(self, plan_dir: Any, jira_api: FakeJiraApi) -> None:
        jira_api.case_keys = {'5fc3b1dc-5a60-40ea-b384-bc15d894ac70': 'RHELTEST-4746'}

        result = run_report('/test/pass$', ['--fix-version', 'rhel-10.3'])
        assert result.exit_code == 0, result.output

        created = jira_api.calls_matching('POST', '/issue')
        assert len(created) == 1
        assert created[0]['fields']['fixVersions'] == [{'name': 'rhel-10.3'}]
        assert created[0]['fields']['parent'] == {'key': 'RHELTEST-4746'}

        comments = jira_api.calls_matching('POST', 'RHELTEST-500/comment')
        assert len(comments) == 1
        assert 'Outcome:  PASS' in _flatten_adf(comments[0]['body'])

        transitions = jira_api.calls_matching('POST', 'RHELTEST-500/transitions')
        assert transitions == [{'transition': {'id': TRANSITION_PASS}}]

        assert 'Jira report: 1 PASS, 0 FAIL, 0 Blocked, 0 skipped.' in result.stderr

    def test_report_fail(self, plan_dir: Any, jira_api: FakeJiraApi) -> None:
        jira_api.case_keys = {'8ada9c66-b809-4aa4-bd06-8ebf1dd4e5bd': 'RHELTEST-4747'}

        result = run_report('/test/fail$', ['--fix-version', 'rhel-10.3'])
        assert result.exit_code != 0  # the test itself fails, report still runs

        comments = jira_api.calls_matching('POST', 'RHELTEST-500/comment')
        assert len(comments) == 1
        assert 'Outcome:  FAIL' in _flatten_adf(comments[0]['body'])

        transitions = jira_api.calls_matching('POST', 'RHELTEST-500/transitions')
        assert transitions == [{'transition': {'id': TRANSITION_FAIL}}]

        assert 'Jira report: 0 PASS, 1 FAIL, 0 Blocked, 0 skipped.' in result.stderr

    def test_no_jira_case_found_skips(self, plan_dir: Any, jira_api: FakeJiraApi) -> None:
        # No implements link and no matching UUID -- nothing to report against.
        result = run_report('/test/pass$', ['--fix-version', 'rhel-10.3'])
        assert result.exit_code == 0, result.output

        assert not jira_api.calls_matching('POST', '/issue')
        assert not [c for c in jira_api.calls if '/comment' in c[1]]
        assert 'Jira report: 0 PASS, 0 FAIL, 0 Blocked, 1 skipped.' in result.stderr

    def test_component_nvr_groups_skeleton(self, plan_dir: Any, jira_api: FakeJiraApi) -> None:
        jira_api.case_keys = {'5fc3b1dc-5a60-40ea-b384-bc15d894ac70': 'RHELTEST-4746'}

        result = run_report(
            '/test/pass$',
            ['--fix-version', 'rhel-10.3', '--component-nvr', 'bash-5.3.9-3.fc44'],
        )
        assert result.exit_code == 0, result.output

        skeleton_search = [
            payload
            for m, url, payload in jira_api.calls
            if m == 'POST'
            and url.endswith('/search/jql')
            and 'issuetype="Test Result"' in payload.get('jql', '')
        ]
        assert len(skeleton_search) == 1
        assert 'cf[10742]="bash-5.3.9-3.fc44"' in skeleton_search[0]['jql']

        created = jira_api.calls_matching('POST', '/issue')
        assert created[0]['fields']['customfield_10742'] == 'bash-5.3.9-3.fc44'
        assert created[0]['fields']['summary'] == 'rhel-10.3 / bash-5.3.9-3.fc44 (0)'
