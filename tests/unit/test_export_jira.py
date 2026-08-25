import logging
import unittest.mock
from typing import Any, Optional

import fmf
import pytest

import tmt.base.core
import tmt.log
from tests import CliRunner, reset_common
from tmt.export.jira import _build_fields, _text_to_adf
from tmt.identifier import ID_KEY
from tmt.utils import ConvertError, Path
from tmt.utils.jira import JiraInstance


class FakeIssueType:
    def __init__(self, type_id: str, name: str) -> None:
        self.id = type_id
        self.name = name


class FakeUser:
    def __init__(self, account_id: str, email_address: str) -> None:
        self.accountId = account_id
        self.emailAddress = email_address


class FakeIssueRef:
    def __init__(self, key: str) -> None:
        self.key = key


class FakeIssueLink:
    def __init__(self, inward: Optional[str] = None, outward: Optional[str] = None) -> None:
        if inward:
            self.inwardIssue = FakeIssueRef(inward)
        if outward:
            self.outwardIssue = FakeIssueRef(outward)


class FakeStatus:
    def __init__(self, name: str) -> None:
        self.name = name


class FakeIssueFields:
    def __init__(
        self,
        status_name: str,
        issuelinks: list[FakeIssueLink],
        custom_fields: Optional[dict[str, Any]] = None,
    ) -> None:
        self.status = FakeStatus(status_name)
        self.issuelinks = issuelinks
        if custom_fields:
            for k, v in custom_fields.items():
                setattr(self, k, v)


class FakeIssue:
    def __init__(
        self,
        key: str,
        status_name: str = 'New',
        issuelinks: Optional[list[FakeIssueLink]] = None,
        custom_fields: Optional[dict[str, Any]] = None,
    ) -> None:
        self.key = key
        self.fields = FakeIssueFields(status_name, issuelinks or [], custom_fields)
        self.updated_fields: Optional[dict[str, Any]] = None

    def update(self, fields: dict[str, Any]) -> None:
        self.updated_fields = fields


class FakeRemoteLinkObject:
    def __init__(self, url: str) -> None:
        self.url = url


class FakeRemoteLink:
    def __init__(self, link_id: int, url: str) -> None:
        self.id = link_id
        self.object = FakeRemoteLinkObject(url)


class FakeJiraClient:
    """Fakes the parts of the ``jira.JIRA`` SDK client used by ``JiraInstance``."""

    def __init__(self) -> None:
        self.fields_response: list[dict[str, str]] = [
            {'id': 'customfield_10591', 'name': 'ID'},
            {'id': 'customfield_10933', 'name': 'URL'},
            {'id': 'customfield_10766', 'name': 'External issue URL'},
        ]
        self.issue_types_response: list[FakeIssueType] = [FakeIssueType('10239', 'Test Case')]
        self.search_result: dict[str, Any] = {'issues': []}
        self.create_result_key = 'RHELTEST-100'
        self.issues: dict[str, FakeIssue] = {}
        self.transitions_response: list[dict[str, Any]] = [
            {'id': '3', 'to': {'name': 'Active'}},
            {'id': '4', 'to': {'name': 'Retired'}},
        ]
        self.users: list[FakeUser] = []
        self.remote_links_map: dict[str, list[FakeRemoteLink]] = {}
        self.created_issues: list[dict[str, Any]] = []
        self.created_issue_links: list[tuple[str, str, str]] = []
        self.created_remote_links: list[tuple[str, dict[str, Any]]] = []
        self.transitioned: list[tuple[str, str]] = []

    def fields(self) -> list[dict[str, str]]:
        return self.fields_response

    def issue_types_for_project(self, project_id: str) -> list[FakeIssueType]:
        return self.issue_types_response

    def search_issues(
        self,
        jql_str: str,
        maxResults: int = 50,  # noqa: N803
        json_result: bool = False,
        fields: Any = None,
    ) -> dict[str, Any]:
        return self.search_result

    def search_users(self, query: Optional[str] = None, **kwargs: Any) -> list[FakeUser]:
        return self.users

    def create_issue(self, fields: dict[str, Any]) -> FakeIssue:
        self.created_issues.append(fields)
        return FakeIssue(self.create_result_key)

    def issue(self, key: str, fields: Any = None, **kwargs: Any) -> FakeIssue:
        return self.issues.setdefault(key, FakeIssue(key))

    def transitions(self, issue: str) -> list[dict[str, Any]]:
        return self.transitions_response

    def transition_issue(self, issue: str, transition: str) -> None:
        self.transitioned.append((issue, transition))

    def create_issue_link(self, type_: str, inwardIssue: str, outwardIssue: str) -> None:  # noqa: N803
        self.created_issue_links.append((type_, inwardIssue, outwardIssue))

    def add_remote_link(self, issue: str, destination: dict[str, Any]) -> None:
        self.created_remote_links.append((issue, destination))

    def remote_links(self, issue: str) -> list[FakeRemoteLink]:
        return self.remote_links_map.get(issue, [])


@pytest.fixture(name='fake_jira')
def fixture_fake_jira() -> FakeJiraClient:
    return FakeJiraClient()


@pytest.fixture(autouse=True)
def _mock_network(fake_jira: FakeJiraClient) -> Any:
    with (
        unittest.mock.patch('jira.JIRA', return_value=fake_jira),
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


@pytest.fixture(name='jira_instance')
def fixture_jira_instance(fake_jira: FakeJiraClient, _mock_network: Any) -> JiraInstance:
    logger = tmt.log.Logger(actual_logger=logging.getLogger('tmt'))
    return JiraInstance(url='https://x', email='u', token='fake-token', logger=logger)  # noqa: S106


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


FIELD_IDS = {
    'tmt_id': 'customfield_10591',
    'url': 'customfield_10933',
    'external_issue_url': 'customfield_10766',
}


class TestBuildFields:
    def test_minimal(self) -> None:
        fields = _build_fields(
            project_id='RHELTEST',
            summary='Check something',
            description=None,
            uuid='abc-123',
            components=[],
            labels=[],
            contact_account_id=None,
            script_url=None,
            polarion_case_url=None,
            field_ids=FIELD_IDS,
        )
        assert fields == {'summary': 'Check something', 'customfield_10591': 'abc-123'}

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
            field_ids=FIELD_IDS,
            issue_type_id='10239',
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


class TestFieldJqlId:
    def test_extracts_numeric_suffix(self) -> None:
        assert JiraInstance.field_jql_id('customfield_10591') == '10591'


class TestResolveIssueTypeId:
    def test_found(self, jira_instance: JiraInstance, fake_jira: FakeJiraClient) -> None:
        fake_jira.issue_types_response = [
            FakeIssueType('10239', 'Test Case'),
            FakeIssueType('10300', 'Test Result'),
        ]
        assert jira_instance.resolve_issue_type_id('RHELTEST', 'Test Case') == '10239'

    def test_not_found_raises(
        self, jira_instance: JiraInstance, fake_jira: FakeJiraClient
    ) -> None:
        fake_jira.issue_types_response = [FakeIssueType('10239', 'Test Case')]
        with pytest.raises(ConvertError, match="No 'Bug' issue type found"):
            jira_instance.resolve_issue_type_id('RHELTEST', 'Bug')

    def test_result_is_cached(
        self, jira_instance: JiraInstance, fake_jira: FakeJiraClient
    ) -> None:
        fake_jira.issue_types_response = [FakeIssueType('10239', 'Test Case')]
        assert jira_instance.resolve_issue_type_id('RHELTEST', 'Test Case') == '10239'
        fake_jira.issue_types_response = []  # would now fail if not cached
        assert jira_instance.resolve_issue_type_id('RHELTEST', 'Test Case') == '10239'


class TestResolveFieldId:
    def test_found(self, jira_instance: JiraInstance) -> None:
        assert jira_instance.resolve_field_id('ID') == 'customfield_10591'

    def test_not_found_raises(
        self, jira_instance: JiraInstance, fake_jira: FakeJiraClient
    ) -> None:
        fake_jira.fields_response = []
        with pytest.raises(ConvertError, match="No 'ID' custom field found"):
            jira_instance.resolve_field_id('ID')

    def test_ambiguous_raises(
        self, jira_instance: JiraInstance, fake_jira: FakeJiraClient
    ) -> None:
        fake_jira.fields_response = [
            {'id': 'customfield_10591', 'name': 'ID'},
            {'id': 'customfield_99999', 'name': 'ID'},
        ]
        with pytest.raises(ConvertError, match="Multiple fields named 'ID'"):
            jira_instance.resolve_field_id('ID')

    def test_result_is_cached(
        self, jira_instance: JiraInstance, fake_jira: FakeJiraClient
    ) -> None:
        assert jira_instance.resolve_field_id('ID') == 'customfield_10591'
        fake_jira.fields_response = []  # would now fail if not cached
        assert jira_instance.resolve_field_id('ID') == 'customfield_10591'
        assert jira_instance.resolve_field_id('URL') == 'customfield_10933'


class TestResolveTransitionId:
    def test_found(self, jira_instance: JiraInstance) -> None:
        assert jira_instance.resolve_transition_id('RHELTEST-1', 'Active') == '3'

    def test_not_found_raises(
        self, jira_instance: JiraInstance, fake_jira: FakeJiraClient
    ) -> None:
        fake_jira.transitions_response = [{'id': '3', 'to': {'name': 'Active'}}]
        with pytest.raises(ConvertError, match="No transition to status 'Retired'"):
            jira_instance.resolve_transition_id('RHELTEST-1', 'Retired')


class TestResolveAccountId:
    def test_exact_match(self, jira_instance: JiraInstance, fake_jira: FakeJiraClient) -> None:
        fake_jira.users = [FakeUser('712020:abc', 'me@example.com')]
        assert jira_instance.resolve_account_id('me@example.com') == '712020:abc'

    def test_no_exact_match_returns_none(
        self, jira_instance: JiraInstance, fake_jira: FakeJiraClient
    ) -> None:
        # A non-matching query can fall back to returning unrelated users.
        fake_jira.users = [FakeUser('712020:abc', 'someone-else@example.com')]
        assert jira_instance.resolve_account_id('me@example.com') is None


class TestExportToJira:
    def test_missing_required_options(self, fmf_root: Any) -> None:
        output = CliRunner().invoke('tests', 'export', '--how', 'jira', '.')
        assert output.exit_code != 0
        assert 'Missing required Jira options' in str(output.exception)

    def test_create_dry_run(self, fmf_root: Any, fake_jira: FakeJiraClient) -> None:
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
        assert not fake_jira.created_issues
        assert ID_KEY not in find_test_node(fmf_root).data

    def test_create(self, fmf_root: Any, fake_jira: FakeJiraClient) -> None:
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

        assert len(fake_jira.created_issues) == 1
        assert fake_jira.created_issues[0]['summary'] == expected_summary

        # A freshly created, enabled test case must be transitioned to Active.
        assert fake_jira.transitioned == [('RHELTEST-100', '3')]

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
        assert ID_KEY not in find_test_node(fmf_root).data

    def test_existing_case_copies_uuid_from_jira_if_missing_in_fmf(
        self, fmf_root: Any, fake_jira: FakeJiraClient
    ) -> None:
        node = find_test_node(fmf_root)
        with node as data:
            data['link'] = [{'implements': 'https://issues.redhat.com/browse/RHELTEST-42'}]

        fake_jira.issues['RHELTEST-42'] = FakeIssue(
            'RHELTEST-42',
            custom_fields={'customfield_10591': 'from-jira-uuid-1234'},
        )

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
        assert find_test_node(fmf_root).data[ID_KEY] == 'from-jira-uuid-1234'
        assert fake_jira.issues['RHELTEST-42'].updated_fields is not None
        assert (
            fake_jira.issues['RHELTEST-42'].updated_fields['customfield_10591']
            == 'from-jira-uuid-1234'
        )

    def test_existing_case_generates_uuid_if_missing_in_both(
        self, fmf_root: Any, fake_jira: FakeJiraClient
    ) -> None:
        node = find_test_node(fmf_root)
        with node as data:
            data['link'] = [{'implements': 'https://issues.redhat.com/browse/RHELTEST-42'}]

        fake_jira.issues['RHELTEST-42'] = FakeIssue('RHELTEST-42')

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
        saved_uuid = find_test_node(fmf_root).data.get(ID_KEY)
        assert saved_uuid is not None
        assert fake_jira.issues['RHELTEST-42'].updated_fields is not None
        assert fake_jira.issues['RHELTEST-42'].updated_fields['customfield_10591'] == saved_uuid

    def test_link_jira_writes_implements_link(
        self, fmf_root: Any, fake_jira: FakeJiraClient
    ) -> None:
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

    def test_existing_case_update_dry_run(self, fmf_root: Any, fake_jira: FakeJiraClient) -> None:
        with find_test_node(fmf_root) as data:
            data[ID_KEY] = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'

        fake_jira.search_result = {'issues': [{'key': 'RHELTEST-42'}]}

        output = CliRunner().invoke(
            'tests',
            'export',
            '--how',
            'jira',
            '--dry',
            *CREDENTIALS,
            '.',
        )
        assert output.exit_code == 0, output.output
        assert "Test case 'RHELTEST-42' would be updated." in output.output
        assert not fake_jira.created_issues
        assert 'RHELTEST-42' not in fake_jira.issues

    def test_existing_case_is_updated(self, fmf_root: Any, fake_jira: FakeJiraClient) -> None:
        # Simulate a test that was already exported once: it already carries
        # a tmt UUID, which is how find_jira_case_key() locates it in Jira.
        with find_test_node(fmf_root) as data:
            data[ID_KEY] = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'

        fake_jira.search_result = {'issues': [{'key': 'RHELTEST-42'}]}

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
        assert not fake_jira.created_issues
        assert fake_jira.issues['RHELTEST-42'].updated_fields is not None

    def test_verifies_links_recreated_and_deduplicated(
        self, fmf_root: Any, fake_jira: FakeJiraClient
    ) -> None:
        node = find_test_node(fmf_root)
        with node as data:
            data['link'] = [
                {'verifies': 'https://issues.redhat.com/browse/RHELTEST-1'},
                {'verifies': 'https://bugzilla.redhat.com/show_bug.cgi?id=123'},
                {'verifies': 'https://bugzilla.mozilla.org/show_bug.cgi?id=456'},
            ]

        # RHELTEST-1 is already linked; the Bugzilla remote links are not.
        fake_jira.issues['RHELTEST-100'] = FakeIssue(
            'RHELTEST-100', issuelinks=[FakeIssueLink(inward='RHELTEST-1')]
        )

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
        # Already linked -- must not be recreated.
        assert not fake_jira.created_issue_links
        # Not yet linked -- must be created exactly once.
        assert fake_jira.created_remote_links == [
            (
                'RHELTEST-100',
                {
                    'url': 'https://bugzilla.redhat.com/show_bug.cgi?id=123',
                    'title': 'BZ#123',
                },
            ),
            (
                'RHELTEST-100',
                {
                    'url': 'https://bugzilla.mozilla.org/show_bug.cgi?id=456',
                    'title': 'BZ#456',
                },
            ),
        ]
