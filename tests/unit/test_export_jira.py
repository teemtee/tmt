import logging
import unittest.mock
from typing import Any
from unittest.mock import MagicMock

import fmf
import pytest

import tmt.base.core
import tmt.log
from tests import CliRunner, reset_common
from tmt.export.jira import _build_fields, _text_to_adf
from tmt.identifier import ID_KEY
from tmt.utils import Path


class FakeJiraApi:
    """Records and answers calls normally made through ``_api_request``."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any]]] = []
        self.search_result: dict[str, Any] = {'issues': []}
        self.create_result: dict[str, Any] = {'key': 'RHELTEST-100'}

    def __call__(self, session: MagicMock, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        self.calls.append((method, url, kwargs.get('json', {})))
        if url.endswith('/search/jql'):
            return self.search_result
        if url.endswith('/issue'):
            return self.create_result
        return {}

    def calls_matching(self, method: str, suffix: str) -> list[dict[str, Any]]:
        return [payload for m, url, payload in self.calls if m == method and url.endswith(suffix)]


@pytest.fixture(name='jira_api')
def fixture_jira_api() -> FakeJiraApi:
    return FakeJiraApi()


@pytest.fixture(autouse=True)
def _mock_network(jira_api: FakeJiraApi) -> Any:
    with (
        unittest.mock.patch('tmt.export.jira._make_session', return_value=MagicMock()),
        unittest.mock.patch('tmt.export.jira._api_request', side_effect=jira_api),
        unittest.mock.patch('tmt.utils.git.validate_git_status', return_value=(True, '')),
        # Avoid a live lookup against a real Polarion instance when ~/.pylero
        # happens to be configured on the machine running the tests.
        unittest.mock.patch('tmt.export.jira._find_polarion_case_url', return_value=None),
    ):
        yield
    # CliRunner options are cached on Common-derived classes; clean up so a
    # test module collected after this one (e.g. via `pytest tests/unit`)
    # doesn't inherit them.
    reset_common()


CREDENTIALS = [
    '--jira-url',
    'https://issues.redhat.com',
    '--jira-user',
    'me@example.com',
    '--jira-token',
    'dummy-token',
    '--project-id',
    'RHELTEST',
]


@pytest.fixture(name='fmf_root')
def fixture_fmf_root(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    # A prior CliRunner invocation (e.g. --dry) leaves its options cached on
    # Common-derived classes; reset before creating the fixture's Test node.
    reset_common()
    root = Path(tmp_path) / 'tree'
    fmf.Tree.init(path=root)
    logger = tmt.log.Logger(actual_logger=logging.getLogger('tmt'))
    tmt.base.core.Test.create(names=['test'], template='shell', path=root, logger=logger)

    # Match the nitrate/polarion export test pattern: run from inside the
    # test's own fmf directory and select it via '.', since the positional
    # export argument is a name filter, not a filesystem path.
    monkeypatch.chdir(root / 'test')
    return root


def find_test_node(root: Any) -> fmf.Tree:
    return fmf.Tree(root).find('/test')


class TestBuildFields:
    def test_minimal(self) -> None:
        fields = _build_fields(
            project_id='RHELTEST',
            summary='Check something',
            description=None,
            uuid=None,
            components=[],
            labels=[],
            contact_account_id=None,
            script_url=None,
            polarion_case_url=None,
        )
        assert fields == {'summary': 'Check something'}

    def test_full(self) -> None:
        fields = _build_fields(
            project_id='RHELTEST',
            summary='Check something',
            description='Longer text',
            uuid='abc-123',
            components=['kernel'],
            labels=['Tier1'],
            contact_account_id='712020:abc-123',
            script_url='https://example.com/test.sh',
            polarion_case_url='https://polarion.example.com/case/1',
            include_issuetype=True,
        )
        assert fields['project'] == {'key': 'RHELTEST'}
        assert fields['issuetype'] == {'id': '10239'}
        assert fields['description'] == _text_to_adf('Longer text')
        assert fields['customfield_10591'] == 'abc-123'
        assert fields['components'] == [{'name': 'kernel'}]
        assert fields['labels'] == ['Tier1']
        assert fields['assignee'] == {'accountId': '712020:abc-123'}
        assert fields['customfield_10933'] == 'https://example.com/test.sh'
        assert fields['customfield_10766'] == 'https://polarion.example.com/case/1'


class TestTextToAdf:
    def test_empty(self) -> None:
        assert _text_to_adf('') == {
            'type': 'doc',
            'version': 1,
            'content': [{'type': 'paragraph', 'content': []}],
        }

    def test_multiline(self) -> None:
        adf = _text_to_adf('first\n\nsecond')
        assert [p['content'][0]['text'] for p in adf['content']] == ['first', 'second']


class TestExportToJira:
    def test_missing_required_options(self, fmf_root: Any) -> None:
        output = CliRunner().invoke('tests', 'export', '--how', 'jira', '.')
        assert output.exit_code != 0
        assert 'Missing required Jira options' in str(output.exception)

    def test_create_dry_run(self, fmf_root: Any, jira_api: FakeJiraApi) -> None:
        node_before = find_test_node(fmf_root)
        assert ID_KEY not in node_before.data

        output = CliRunner().invoke(
            'tests',
            'export',
            '--how',
            'jira',
            '--create',
            '--dry',
            *CREDENTIALS,
            '.',
        )
        assert output.exit_code == 0, output.output
        assert 'would be created' in output.output
        # Dry run must not create the issue nor touch fmf metadata.
        assert not jira_api.calls_matching('POST', '/issue')
        assert ID_KEY not in find_test_node(fmf_root).data

    def test_create(self, fmf_root: Any, jira_api: FakeJiraApi) -> None:
        expected_summary = find_test_node(fmf_root).data['summary']

        output = CliRunner().invoke(
            'tests',
            'export',
            '--how',
            'jira',
            '--create',
            *CREDENTIALS,
            '.',
        )
        assert output.exit_code == 0, output.output
        assert "Test case 'RHELTEST-100' created." in output.output

        created = jira_api.calls_matching('POST', '/issue')
        assert len(created) == 1
        assert created[0]['fields']['summary'] == expected_summary

        # A freshly created, enabled test case must be transitioned to Active.
        transitions = jira_api.calls_matching('POST', 'issue/RHELTEST-100/transitions')
        assert transitions == [{'transition': {'id': '3'}}]

        # The UUID generated for the export must be written back to fmf.
        assert ID_KEY in find_test_node(fmf_root).data

    def test_create_required_without_flag_fails(self, fmf_root: Any) -> None:
        output = CliRunner().invoke(
            'tests',
            'export',
            '--how',
            'jira',
            *CREDENTIALS,
            '.',
        )
        assert output.exit_code != 0
        assert 'Use --create to create a new test case' in str(output.exception)

    def test_link_jira_writes_implements_link(self, fmf_root: Any, jira_api: FakeJiraApi) -> None:
        output = CliRunner().invoke(
            'tests',
            'export',
            '--how',
            'jira',
            '--create',
            '--link-jira',
            *CREDENTIALS,
            '.',
        )
        assert output.exit_code == 0, output.output

        node = find_test_node(fmf_root)
        implements = [
            link['implements'] for link in node.data.get('link', []) if 'implements' in link
        ]
        assert implements == ['https://issues.redhat.com/browse/RHELTEST-100']

    def test_existing_case_is_updated(self, fmf_root: Any, jira_api: FakeJiraApi) -> None:
        # Simulate a test that was already exported once: it already carries
        # a tmt UUID, which is how find_jira_case_key() locates it in Jira.
        with find_test_node(fmf_root) as data:
            data[ID_KEY] = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'

        jira_api.search_result = {'issues': [{'key': 'RHELTEST-42'}]}

        output = CliRunner().invoke(
            'tests',
            'export',
            '--how',
            'jira',
            *CREDENTIALS,
            '.',
        )
        assert output.exit_code == 0, output.output
        assert "Test case 'RHELTEST-42' updated." in output.output
        assert not jira_api.calls_matching('POST', '/issue')

        updated = jira_api.calls_matching('PUT', 'issue/RHELTEST-42')
        assert len(updated) == 1
