import logging
import subprocess
import unittest.mock
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any, Optional

import fmf
import pytest

import tmt.base.core
import tmt.log
from tests import CliRunner, reset_common
from tmt.export.jira import JiraExportContext, JiraExporter
from tmt.identifier import ID_KEY
from tmt.utils import ExportError, Path
from tmt.utils.jira import JiraInstance


class FakeIssueType:
    def __init__(self, type_id: str, name: str) -> None:
        self.id = type_id
        self.name = name
        self.statuses = [SimpleNamespace(name=name) for name in ('New', 'Active', 'Retired')]


class FakeUser:
    def __init__(
        self,
        account_id: str,
        email_address: str,
        display_name: str = '',
        name: str = '',
    ) -> None:
        self.accountId = account_id
        self.emailAddress = email_address
        self.displayName = display_name or email_address
        self.name = name or email_address


class FakeIssueRef:
    def __init__(self, key: str) -> None:
        self.key = key


class FakeIssueLink:
    def __init__(
        self, inward: Optional[str] = None, outward: Optional[str] = None, type_name: str = 'Tests'
    ) -> None:
        self.type = SimpleNamespace(name=type_name)
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
        issue_type_name: str = 'Test Case',
    ) -> None:
        self.status = FakeStatus(status_name)
        self.issuelinks = issuelinks
        self.issuetype = FakeIssueType(
            '10239' if issue_type_name == 'Test Case' else '10300', issue_type_name
        )
        self.project = SimpleNamespace(key='RHELTEST')
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
        issue_type_name: str = 'Test Case',
    ) -> None:
        self.key = key
        self.fields = FakeIssueFields(
            status_name, issuelinks or [], custom_fields, issue_type_name
        )
        self.updated_fields: Optional[dict[str, Any]] = None

    def update(self, fields: dict[str, Any]) -> None:
        self.updated_fields = fields


class FakeRemoteLinkObject:
    def __init__(self, url: str) -> None:
        self.url = url


class FakeRemoteLink:
    def __init__(self, link_id: int, url: str, global_id: Optional[str] = None) -> None:
        self.globalId = global_id
        self.id = link_id
        self.object = FakeRemoteLinkObject(url)


class FakeJiraClient:
    """Fakes the parts of the ``jira.JIRA`` SDK client used by ``JiraInstance``."""

    def __init__(self) -> None:
        self.deploymentType = 'Server'
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
        self.account_queries: list[Optional[str]] = []
        self.remote_links_map: dict[str, list[FakeRemoteLink]] = {}
        self.nonexistent_issues: set[str] = set()
        self.created_issues: list[dict[str, Any]] = []
        self.created_issue_links: list[tuple[str, str, str]] = []
        self.created_remote_links: list[tuple[str, dict[str, Any]]] = []
        self.remote_global_ids: list[Optional[str]] = []
        self.deleted_remote_links: list[tuple[str, str]] = []
        self.searches: list[tuple[str, int]] = []
        self.transitioned: list[tuple[str, str]] = []
        self.link_types_response: list[Any] = [
            SimpleNamespace(name='Tests'),
            SimpleNamespace(name='Blocks'),
        ]
        self.field_metadata_override: Optional[dict[str, Any]] = None
        self.field_metadata_calls: list[tuple[str, str]] = []

    def fields(self) -> list[dict[str, str]]:
        return self.fields_response

    def issue_link_types(self, force: bool = False) -> list[Any]:
        return self.link_types_response

    def _get_json(self, path: str, params: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        assert params is not None
        if path == 'search/jql':
            return {
                **self.search_issues(
                    params['jql'],
                    maxResults=params['maxResults'],
                    json_result=True,
                    fields=params['fields'],
                ),
                'isLast': True,
            }
        assert path.startswith('issue/createmeta/')
        parts = path.split('/')
        self.field_metadata_calls.append((parts[2], parts[4]))
        fields = [
            {'fieldId': field_id, **data} for field_id, data in self._field_metadata().items()
        ]
        start = params['startAt']
        return {'fields': fields[start : start + params['maxResults']], 'total': len(fields)}

    def _field_metadata(self) -> dict[str, Any]:
        if self.field_metadata_override is not None:
            return self.field_metadata_override
        fields = {
            name: {'required': name == 'summary'}
            for name in ('summary', 'description', 'components', 'labels', 'assignee')
        }
        for field in self.fields_response:
            fields[field['id']] = {
                'schema': {'type': 'option' if field['name'] == 'Tier' else 'string'},
                'required': False,
            }
            if field['name'] == 'Tier':
                fields[field['id']]['allowedValues'] = [
                    {'value': value} for value in ('1', '2', 'First', 'Second')
                ]
        return fields

    def project_issue_fields(
        self,
        project: str,
        issue_type: str,
        startAt: int = 0,  # noqa: N803
        maxResults: int = 50,  # noqa: N803
    ) -> list[Any]:
        self.field_metadata_calls.append((project, issue_type))
        return [
            SimpleNamespace(raw={'fieldId': field_id, **data})
            for field_id, data in self._field_metadata().items()
        ]

    def editmeta(self, issue: str) -> dict[str, Any]:
        return {'fields': self._field_metadata()}

    def issue_types_for_project(self, project_id: str) -> list[FakeIssueType]:
        return self.issue_types_response

    def search_issues(
        self,
        jql_str: str,
        maxResults: int = 50,  # noqa: N803
        json_result: bool = False,
        fields: Any = None,
    ) -> dict[str, Any]:
        self.searches.append((jql_str, maxResults))
        return self.search_result

    def search_users(self, query: Optional[str] = None, **kwargs: Any) -> list[FakeUser]:
        self.account_queries.append(query)
        return self.users

    def create_issue(self, fields: dict[str, Any]) -> FakeIssue:
        self.created_issues.append(fields)
        return FakeIssue(self.create_result_key)

    def issue(self, key: str, fields: Any = None, **kwargs: Any) -> FakeIssue:
        if key in self.nonexistent_issues:
            import jira

            raise jira.JIRAError(status_code=404, text=f"Issue {key} does not exist")
        return self.issues.setdefault(key, FakeIssue(key))

    def transitions(self, issue: str) -> list[dict[str, Any]]:
        return self.transitions_response

    def transition_issue(self, issue: str, transition: str) -> None:
        self.transitioned.append((issue, transition))

    def create_issue_link(
        self,
        type: str,  # noqa: A002
        inwardIssue: str,  # noqa: N803
        outwardIssue: str,  # noqa: N803
        comment: Optional[dict[str, Any]] = None,
    ) -> None:
        self.created_issue_links.append((type, inwardIssue, outwardIssue))
        self.issue(inwardIssue).fields.issuelinks.append(
            FakeIssueLink(outward=outwardIssue, type_name=type)
        )
        self.issue(outwardIssue).fields.issuelinks.append(
            FakeIssueLink(inward=inwardIssue, type_name=type)
        )

    def add_remote_link(
        self,
        issue: str,
        destination: dict[str, Any],
        globalId: Optional[str] = None,  # noqa: N803
        application: Optional[dict[str, Any]] = None,
        relationship: Optional[str] = None,
    ) -> None:
        self.created_remote_links.append((issue, destination))
        self.remote_global_ids.append(globalId)
        existing = self.remote_links_map.setdefault(issue, [])
        existing[:] = [link for link in existing if not globalId or link.globalId != globalId]
        existing.append(FakeRemoteLink(len(existing), destination['url'], globalId))

    def delete_remote_link(
        self, issue: str, *, internal_id: Optional[str] = None, global_id: Optional[str] = None
    ) -> None:
        assert global_id
        self.deleted_remote_links.append((issue, global_id))
        self.remote_links_map[issue] = [
            link for link in self.remote_links_map.get(issue, []) if link.globalId != global_id
        ]

    def remote_links(self, issue: str) -> list[FakeRemoteLink]:
        return self.remote_links_map.get(issue, [])


@pytest.fixture(name='fake_jira')
def fixture_fake_jira() -> FakeJiraClient:
    return FakeJiraClient()


@pytest.fixture(autouse=True)
def _mock_network(fake_jira: FakeJiraClient, monkeypatch: pytest.MonkeyPatch) -> Any:
    for variable in ('TMT_JIRA_URL', 'TMT_JIRA_USER', 'TMT_JIRA_TOKEN'):
        monkeypatch.delenv(variable, raising=False)
    with (
        unittest.mock.patch('jira.JIRA', return_value=fake_jira),
        unittest.mock.patch(
            'requests.sessions.Session.request', side_effect=AssertionError('Network disabled')
        ),
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
    '--jira-issue-type',
    'Test Case',
    '--jira-uuid-field',
    'ID',
    '--jira-automation-url',
    'URL',
    '--ignore-git-validation',
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
    init_git(root)

    # Match the nitrate/polarion export test pattern: run from inside the
    # test's own fmf directory and select it via '.', since the positional
    # export argument is a name filter, not a filesystem path.
    monkeypatch.chdir(root / 'test')
    return root


def find_test_node(root: Any) -> fmf.Tree:
    return fmf.Tree(root).find('/test')


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ['git', *args], cwd=root, check=True, capture_output=True, text=True
    ).stdout


def init_git(root: Path) -> None:
    """Create a tracked, published fixture without any network access."""
    git(root, 'init', '-b', 'main')
    git(root, 'config', 'user.name', 'Jira export tests')
    git(root, 'config', 'user.email', 'tests@example.com')
    git(root, 'add', '.')
    git(root, '-c', 'core.hooksPath=/dev/null', 'commit', '-m', 'Fixture')
    git(root, 'update-ref', 'refs/remotes/origin/main', 'HEAD')
    git(root, 'config', 'remote.origin.url', 'https://github.com/example/tests.git')
    git(root, 'config', 'remote.origin.fetch', '+refs/heads/*:refs/remotes/origin/*')
    git(root, 'config', 'branch.main.remote', 'origin')
    git(root, 'config', 'branch.main.merge', 'refs/heads/main')


@pytest.fixture(name='profile', autouse=True)
def fixture_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Callable[[dict[str, Any]], None]:
    import tmt.utils

    config_root = Path(tmp_path) / 'config'
    fmf.Tree.init(path=config_root)
    monkeypatch.setenv('TMT_CONFIG_DIR', str(config_root))

    def write(data: dict[str, Any]) -> None:
        (config_root / 'export').mkdir(exist_ok=True)
        (config_root / 'export' / 'jira.fmf').write_text(tmt.utils.to_yaml(data))

    write({})
    return write


FIELD_IDS = {
    'tmt_id': 'customfield_10591',
    'url': 'customfield_10933',
    'external_issue_url': 'customfield_10766',
}


class TestTextToAdf:
    def test_empty(self) -> None:
        assert JiraExporter._text_to_adf('') == {
            'type': 'doc',
            'version': 1,
            'content': [{'type': 'paragraph', 'content': []}],
        }

    def test_multiline(self) -> None:
        adf = JiraExporter._text_to_adf('first\n\nsecond')
        assert [p['content'][0]['text'] for p in adf['content']] == ['first', 'second']


class TestFieldJqlId:
    def test_extracts_numeric_suffix(self) -> None:
        assert JiraInstance.field_jql_id('customfield_10591') == '10591'


class TestResolveIssueTypeId:
    def test_by_id_and_project_cache(
        self, jira_instance: JiraInstance, fake_jira: FakeJiraClient
    ) -> None:
        assert jira_instance.resolve_issue_type_id('FIRST', '10239') == '10239'
        fake_jira.issue_types_response = [FakeIssueType('20000', 'Test Case')]
        assert jira_instance.resolve_issue_type_id('SECOND', 'Test Case') == '20000'
        assert jira_instance.resolve_issue_type_id('FIRST', 'Test Case') == '10239'

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
        with pytest.raises(ExportError, match="No 'Bug' issue type found"):
            jira_instance.resolve_issue_type_id('RHELTEST', 'Bug')

    def test_result_is_cached(
        self, jira_instance: JiraInstance, fake_jira: FakeJiraClient
    ) -> None:
        fake_jira.issue_types_response = [FakeIssueType('10239', 'Test Case')]
        assert jira_instance.resolve_issue_type_id('RHELTEST', 'Test Case') == '10239'
        fake_jira.issue_types_response = []  # would now fail if not cached
        assert jira_instance.resolve_issue_type_id('RHELTEST', 'Test Case') == '10239'


class TestResolveFieldId:
    def test_id_disambiguates_name(
        self, jira_instance: JiraInstance, fake_jira: FakeJiraClient
    ) -> None:
        fake_jira.fields_response.append({'id': 'customfield_99999', 'name': 'ID'})
        assert jira_instance.resolve_field_id('customfield_99999') == 'customfield_99999'
        with pytest.raises(ExportError, match='Configure a field ID'):
            jira_instance.resolve_field_id('ID')

    def test_found(self, jira_instance: JiraInstance) -> None:
        assert jira_instance.resolve_field_id('ID') == 'customfield_10591'

    def test_not_found_raises(
        self, jira_instance: JiraInstance, fake_jira: FakeJiraClient
    ) -> None:
        fake_jira.fields_response = []
        with pytest.raises(ExportError, match="No 'ID' custom field found"):
            jira_instance.resolve_field_id('ID')

    def test_ambiguous_raises(
        self, jira_instance: JiraInstance, fake_jira: FakeJiraClient
    ) -> None:
        fake_jira.fields_response = [
            {'id': 'customfield_10591', 'name': 'ID'},
            {'id': 'customfield_99999', 'name': 'ID'},
        ]
        with pytest.raises(ExportError, match="Multiple fields named 'ID'"):
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
        with pytest.raises(ExportError, match="No transition to status 'Retired'"):
            jira_instance.resolve_transition_id('RHELTEST-1', 'Retired')


class TestResolveAccountId:
    def test_exact_email_match(
        self, jira_instance: JiraInstance, fake_jira: FakeJiraClient
    ) -> None:
        fake_jira.users = [FakeUser('712020:abc', 'me@example.com')]
        assert jira_instance.resolve_account_id('me@example.com') == '712020:abc'

    def test_display_name_match(
        self, jira_instance: JiraInstance, fake_jira: FakeJiraClient
    ) -> None:
        fake_jira.users = [
            FakeUser('712020:abc', 'hidden@example.com', display_name='Petr Matyas')
        ]
        assert jira_instance.resolve_account_id('Petr Matyas') == '712020:abc'

    def test_username_match(self, jira_instance: JiraInstance, fake_jira: FakeJiraClient) -> None:
        fake_jira.users = [FakeUser('712020:abc', 'hidden@example.com', name='pmatyas')]
        assert jira_instance.resolve_account_id('pmatyas') == '712020:abc'

    def test_no_exact_match_returns_none(
        self, jira_instance: JiraInstance, fake_jira: FakeJiraClient
    ) -> None:
        # A non-matching query can fall back to returning unrelated users.
        fake_jira.users = [FakeUser('712020:abc', 'someone-else@example.com')]
        assert jira_instance.resolve_account_id('me@example.com') is None


@pytest.mark.parametrize('cloud', [False, True])
def test_client_deployment_options(cloud: bool) -> None:
    with unittest.mock.patch('jira.JIRA') as constructor:
        instance = JiraInstance(
            url='https://jira.example.com',
            email='me@example.com',
            token='test-token',  # noqa: S106
            logger=tmt.log.Logger.get_bootstrap_logger(),
            cloud=cloud,
        )
    kwargs = constructor.call_args.kwargs
    assert kwargs['server'] == 'https://jira.example.com'
    if cloud:
        assert kwargs['options'] == {'rest_api_version': '3'}
        assert kwargs['get_server_info'] is False
        assert instance.jira.deploymentType == 'Cloud'
    else:
        assert set(kwargs) == {'server', 'basic_auth'}
        assert instance.jira.deploymentType != 'Cloud'


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

        # No workflow transition is requested by default.
        assert not fake_jira.transitioned

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

    def test_implements_link_nonexistent_warns_and_falls_back_to_uuid(
        self, fmf_root: Any, fake_jira: FakeJiraClient
    ) -> None:
        node = find_test_node(fmf_root)
        with node as data:
            data['link'] = [{'implements': 'https://issues.redhat.com/browse/RHELTEST-999'}]
            data[ID_KEY] = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'

        fake_jira.nonexistent_issues.add('RHELTEST-999')
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
        assert "Jira issue 'RHELTEST-999' from implements link not found in Jira." in output.output
        assert "Found Jira issue: 'RHELTEST-42'." in output.output
        assert "Test case 'RHELTEST-42' updated." in output.output

    def test_implements_link_wrong_type_warns_and_falls_back_to_uuid(
        self, fmf_root: Any, fake_jira: FakeJiraClient
    ) -> None:
        node = find_test_node(fmf_root)
        with node as data:
            data['link'] = [{'implements': 'https://issues.redhat.com/browse/RHELTEST-999'}]
            data[ID_KEY] = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'

        fake_jira.issues['RHELTEST-999'] = FakeIssue('RHELTEST-999', issue_type_name='Bug')
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
        assert (
            "Ignoring Jira backlink 'RHELTEST-999' outside configured project/type."
            in output.output
        )
        assert "Found Jira issue: 'RHELTEST-42'." in output.output
        assert "Test case 'RHELTEST-42' updated." in output.output

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
        self, fmf_root: Any, fake_jira: FakeJiraClient, profile: Any
    ) -> None:
        profile({'links': {'verifies': {'issue-type': 'Tests', 'remote': True}}})
        node = find_test_node(fmf_root)
        with node as data:
            data[ID_KEY] = 'known-uuid'
            data['link'] = [
                {'verifies': 'https://issues.redhat.com/browse/RHELTEST-1'},
                {'verifies': 'https://bugzilla.redhat.com/show_bug.cgi?id=123'},
                {'verifies': 'https://bugzilla.mozilla.org/show_bug.cgi?id=456'},
            ]

        # RHELTEST-1 is already linked; the Bugzilla remote links are not.
        fake_jira.issues['RHELTEST-100'] = FakeIssue(
            'RHELTEST-100', issuelinks=[FakeIssueLink(outward='RHELTEST-1')]
        )
        fake_jira.search_result = {'issues': [{'key': 'RHELTEST-100'}]}

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
        # Configured remote links are created from local URLs.
        assert fake_jira.created_remote_links == [
            (
                'RHELTEST-100',
                {
                    'url': 'https://bugzilla.redhat.com/show_bug.cgi?id=123',
                    'title': 'verifies',
                },
            ),
            (
                'RHELTEST-100',
                {
                    'url': 'https://bugzilla.mozilla.org/show_bug.cgi?id=456',
                    'title': 'verifies',
                },
            ),
        ]

    def test_verifies_links_bugzilla_ignored_without_flag(
        self, fmf_root: Any, fake_jira: FakeJiraClient
    ) -> None:
        node = find_test_node(fmf_root)
        with node as data:
            data['link'] = [
                {'verifies': 'https://bugzilla.redhat.com/show_bug.cgi?id=123'},
            ]

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
        assert not fake_jira.created_remote_links


@pytest.mark.parametrize(
    'contact', ['John Smith', 'john@example.com', 'John Smith <john@example.com>']
)
def test_contact_is_not_truncated(
    contact: str, jira_instance: JiraInstance, fake_jira: FakeJiraClient
) -> None:
    fake_jira.users = [FakeUser('account-1', 'john@example.com', display_name='John Smith')]
    test = tmt.base.core.Test(
        node=fmf.Tree(data={'test': 'true', 'contact': contact}),
        logger=tmt.log.Logger.get_bootstrap_logger(),
    )
    with unittest.mock.patch.object(
        jira_instance, 'resolve_account_id', wraps=jira_instance.resolve_account_id
    ) as lookup:
        assert JiraExporter._resolve_contact(test, jira_instance) == 'account-1'
    assert lookup.call_args.args[0] == ('John Smith' if '@' not in contact else 'john@example.com')


def shared_tree(tmp_path: Path, ids: bool) -> Path:
    """Two virtual tests share one tracked main.fmf and a local remote ref."""
    root = Path(tmp_path) / 'shared'
    fmf.Tree.init(path=root)
    (root / 'main.fmf').write_text(
        'test: /bin/true\n/first:\n  summary: First\n'
        + ('  id: first-uuid\n' if ids else '')
        + '/second:\n  summary: Second\n'
        + ('  id: second-uuid\n' if ids else '')
    )
    init_git(root)
    return root


def export_shared(root: Path, *options: str) -> Any:
    credentials = [option for option in CREDENTIALS if option != '--ignore-git-validation']
    return CliRunner().invoke(
        '--root',
        str(root),
        'tests',
        'export',
        '--how',
        'jira',
        '--create',
        *credentials,
        *options,
        '^/(first|second)$',
    )


@pytest.mark.parametrize(
    ('ids', 'backlinks'), [(False, False), (False, True), (True, True), (True, False)]
)
def test_shared_file_writes_do_not_invalidate_collection(
    tmp_path: Path, fake_jira: FakeJiraClient, ids: bool, backlinks: bool
) -> None:
    root = shared_tree(tmp_path, ids)
    assert not git(root, 'status', '--porcelain')
    output = export_shared(root, *(['--link-jira'] if backlinks else []))
    assert output.exit_code == 0, output.exception
    assert len(fake_jira.created_issues) == 2
    nodes = fmf.Tree(root)
    uuids = [nodes.find(name).get(ID_KEY) for name in ('/first', '/second')]
    assert len(set(uuids)) == 2
    assert all(uuids)
    if ids:
        assert uuids == ['first-uuid', 'second-uuid']
    if backlinks:
        assert all(nodes.find(name).get('link') for name in ('/first', '/second'))
    assert bool(git(root, 'status', '--porcelain')) == (not ids or backlinks)


@pytest.mark.parametrize('unpublished', [False, True])
def test_preflight_rejects_user_changes_before_first_jira_write(
    tmp_path: Path, fake_jira: FakeJiraClient, unpublished: bool
) -> None:
    root = shared_tree(tmp_path, True)
    (root / 'second.fmf').write_text('summary: Changed second test\n')
    if unpublished:
        git(root, 'add', 'second.fmf')
        git(root, '-c', 'core.hooksPath=/dev/null', 'commit', '-m', 'Unpublished user change')
    before = (root / 'main.fmf').read_bytes()
    output = export_shared(root)
    assert output.exit_code != 0
    assert ('Not pushed changes' if unpublished else 'Uncommitted changes') in str(
        output.exception
    )
    assert not fake_jira.created_issues
    assert (root / 'main.fmf').read_bytes() == before


@pytest.mark.parametrize('ignore', [False, True])
def test_automation_url_independent_of_validation_policy(
    tmp_path: Path, fake_jira: FakeJiraClient, ignore: bool
) -> None:
    root = shared_tree(tmp_path, True)
    with unittest.mock.patch.object(
        tmt.base.core.Test, 'web_link', wraps=None, return_value='https://example.com/main.fmf'
    ) as web_link:
        output = export_shared(root, *(['--ignore-git-validation'] if ignore else []))
    assert output.exit_code == 0, output.exception
    assert web_link.call_count == 2
    assert all(
        fields['customfield_10933'] == 'https://example.com/main.fmf'
        for fields in fake_jira.created_issues
    )


@pytest.mark.parametrize('direction', ['outward', 'inward'])
def test_fresh_requirement_link_sdk_direction_and_deduplication(
    fmf_root: Path, fake_jira: FakeJiraClient, profile: Any, direction: str
) -> None:
    profile({'links': {'verifies': {'issue-type': 'Tests', 'direction': direction}}})
    with find_test_node(fmf_root) as data:
        data[ID_KEY] = 'known-uuid'
        data['link'] = [{'verifies': 'https://issues.redhat.com/browse/REQ-1'}]
    fake_jira.search_result = {'issues': [{'key': 'RHELTEST-100'}]}
    # Another relationship to this requirement must not suppress the new one.
    fake_jira.issues['RHELTEST-100'] = FakeIssue(
        'RHELTEST-100', issuelinks=[FakeIssueLink(outward='REQ-1', type_name='Blocks')]
    )
    for _ in range(2):
        output = CliRunner().invoke('tests', 'export', '--how', 'jira', *CREDENTIALS, '.')
        assert output.exit_code == 0, output.exception
    expected = ('RHELTEST-100', 'REQ-1') if direction == 'outward' else ('REQ-1', 'RHELTEST-100')
    assert fake_jira.created_issue_links == [('Tests', *expected)]
    import inspect

    import jira

    inspect.signature(jira.JIRA.create_issue_link).bind(
        fake_jira, type='Tests', inwardIssue=expected[0], outwardIssue=expected[1]
    )


def test_uuid_lookup_is_component_independent_and_rejects_ambiguity(
    fmf_root: Path, fake_jira: FakeJiraClient
) -> None:
    with find_test_node(fmf_root) as data:
        data[ID_KEY] = 'stable-uuid'
        data['component'] = ['new-component']
    fake_jira.search_result = {'issues': [{'key': 'RHELTEST-1'}, {'key': 'RHELTEST-2'}]}
    before = (fmf_root / 'test' / 'main.fmf').read_bytes()
    output = CliRunner().invoke('tests', 'export', '--how', 'jira', '--create', *CREDENTIALS, '.')
    assert output.exit_code != 0
    assert 'Multiple Jira issues match UUID' in str(output.exception)
    assert 'component' not in fake_jira.searches[0][0]
    assert fake_jira.searches[0][1] == 2
    assert not fake_jira.created_issues
    assert (fmf_root / 'test' / 'main.fmf').read_bytes() == before


def test_backlink_cannot_replace_a_different_uuid(
    fmf_root: Path, fake_jira: FakeJiraClient
) -> None:
    with find_test_node(fmf_root) as data:
        data[ID_KEY] = 'local-uuid'
        data['link'] = [{'implements': 'https://issues.redhat.com/browse/RHELTEST-42'}]
    fake_jira.issues['RHELTEST-42'] = FakeIssue(
        'RHELTEST-42', custom_fields={'customfield_10591': 'other-uuid'}
    )
    output = CliRunner().invoke('tests', 'export', '--how', 'jira', *CREDENTIALS, '.')
    assert output.exit_code != 0
    assert 'different UUID' in str(output.exception)
    assert fake_jira.issues['RHELTEST-42'].updated_fields is None
    assert find_test_node(fmf_root).get(ID_KEY) == 'local-uuid'


@pytest.mark.parametrize('existing', [False, True])
@pytest.mark.parametrize(
    ('summary', 'description'),
    [
        ('Concise title', 'Detailed explanation'),
        ('Concise title', None),
        ('Concise title', ''),
        (None, 'Detailed explanation'),
        ('', 'Detailed explanation'),
    ],
)
def test_default_summary_and_description_mapping(
    fmf_root: Path,
    fake_jira: FakeJiraClient,
    existing: bool,
    summary: Optional[str],
    description: Optional[str],
) -> None:
    with find_test_node(fmf_root) as data:
        data.update(id='known-uuid', summary=summary, description=description)
    if existing:
        fake_jira.search_result = {'issues': [{'key': 'RHELTEST-42'}]}

    output = CliRunner().invoke('tests', 'export', '--how', 'jira', '--create', *CREDENTIALS, '.')
    assert output.exit_code == 0, output.exception
    fields = (
        fake_jira.issues['RHELTEST-42'].updated_fields if existing else fake_jira.created_issues[0]
    )
    assert fields is not None
    assert fields['summary'] == (summary or '/test')
    assert fields['description'] == (
        {
            'type': 'doc',
            'version': 1,
            'content': [
                {
                    'type': 'paragraph',
                    'content': [{'type': 'text', 'text': 'Detailed explanation'}],
                }
            ],
        }
        if description
        else None
    )


@pytest.mark.parametrize('remaining_description', [None, ''])
@pytest.mark.parametrize('remaining_summary', [None, 'Still descriptive'])
def test_generic_profile_and_empty_owned_fields(
    fmf_root: Path,
    fake_jira: FakeJiraClient,
    profile: Any,
    remaining_summary: Optional[str],
    remaining_description: Optional[str],
) -> None:
    profile(
        {
            'project': 'QA',
            'issue-type': 'Scenario',
            'uuid-field': 'Case UUID',
            'automation-url': 'Automation',
            'title': '{name}',
            'fields': {'Tier': {'source': 'tier', 'type': 'single-select'}},
        }
    )
    fake_jira.fields_response = [
        {'id': 'customfield_1', 'name': 'Case UUID'},
        {'id': 'customfield_2', 'name': 'Automation'},
        {'id': 'customfield_3', 'name': 'Tier'},
    ]
    fake_jira.issue_types_response = [FakeIssueType('7', 'Scenario')]
    with find_test_node(fmf_root) as data:
        data.update(
            id='known-uuid',
            summary='Descriptive summary',
            description='More detail',
            tier='2',
            component=['storage', 'kernel'],
            tag=['smoke'],
        )
    credentials = [*CREDENTIALS[:6], '--ignore-git-validation']
    output = CliRunner().invoke('tests', 'export', '--how', 'jira', '--create', *credentials, '.')
    assert output.exit_code == 0, output.exception
    fields = fake_jira.created_issues[0]
    assert fields['summary'] == '/test'
    assert fields['description'] == JiraExporter._text_to_adf('More detail')
    assert fields['customfield_1'] == 'known-uuid'
    assert fields['customfield_3'] == {'value': '2'}
    assert fields['components'] == [{'name': 'storage'}, {'name': 'kernel'}]
    assert fields['labels'] == ['smoke']
    assert not fake_jira.transitioned
    assert not find_test_node(fmf_root).get('link')

    with find_test_node(fmf_root) as data:
        data.update(
            summary=remaining_summary,
            description=remaining_description,
            tier=None,
            component=[],
            tag=[],
            contact=[],
        )
    fake_jira.search_result = {'issues': [{'key': 'QA-1'}]}
    with unittest.mock.patch.object(tmt.base.core.Test, 'web_link', return_value=None):
        output = CliRunner().invoke('tests', 'export', '--how', 'jira', *credentials, '.')
    assert output.exit_code == 0, output.exception
    updated = fake_jira.issues['QA-1'].updated_fields
    assert updated is not None
    assert updated['description'] is None
    assert updated['customfield_2'] is None
    assert updated['customfield_3'] is None
    assert updated['assignee'] is None
    assert updated['components'] == []
    assert updated['labels'] == []


def test_status_transition_is_optional(fmf_root: Path, fake_jira: FakeJiraClient) -> None:
    output = CliRunner().invoke(
        'tests',
        'export',
        '--how',
        'jira',
        '--create',
        '--jira-status',
        'Active',
        *CREDENTIALS,
        '.',
    )
    assert output.exit_code == 0, output.exception
    assert fake_jira.transitioned == [('RHELTEST-100', '3')]


def test_local_external_url_mapping_has_no_polarion_lookup(
    fmf_root: Path, fake_jira: FakeJiraClient, profile: Any
) -> None:
    profile({'links': {'implements': {'remote': True}}})
    target = 'https://polarion.example.com/project/workitem?id=123'
    with find_test_node(fmf_root) as data:
        data['link'] = [{'implements': target}]
    output = CliRunner().invoke('tests', 'export', '--how', 'jira', '--create', *CREDENTIALS, '.')
    assert output.exit_code == 0, output.exception
    assert fake_jira.created_remote_links == [
        ('RHELTEST-100', {'url': target, 'title': 'implements'})
    ]


def test_managed_remote_automation_link_is_updated_and_cleared(
    fmf_root: Path, fake_jira: FakeJiraClient
) -> None:
    with find_test_node(fmf_root) as data:
        data[ID_KEY] = 'known-uuid'
    fake_jira.search_result = {'issues': [{'key': 'RHELTEST-42'}]}
    fake_jira.remote_links_map['RHELTEST-42'] = [FakeRemoteLink(1, 'https://unrelated.com')]
    for url in ('https://automation.example.com/old', 'https://automation.example.com/new', None):
        with unittest.mock.patch.object(tmt.base.core.Test, 'web_link', return_value=url):
            output = CliRunner().invoke(
                'tests',
                'export',
                '--how',
                'jira',
                *CREDENTIALS,
                '--jira-automation-url',
                'remote-link',
                '.',
            )
        assert output.exit_code == 0, output.exception
    assert fake_jira.remote_global_ids == ['tmt:uuid:known-uuid', 'tmt:uuid:known-uuid']
    assert fake_jira.deleted_remote_links == [('RHELTEST-42', 'tmt:uuid:known-uuid')]
    assert [link.object.url for link in fake_jira.remote_links_map['RHELTEST-42']] == [
        'https://unrelated.com'
    ]


@pytest.mark.parametrize(
    'config',
    [
        {'fields': {'Tier': {'source': 'nonexistent', 'type': 'single-select'}}},
        {'fields': {'Tier': {'source': 'tier', 'type': 'arbitrary'}}},
        {'unexpected': 'value'},
        {'links': {'unknown': {'remote': True}}},
        {'fields': {'ID': {'source': 'tier'}}},
    ],
)
def test_invalid_profiles_fail_before_jira_writes(
    fmf_root: Path, fake_jira: FakeJiraClient, profile: Any, config: dict[str, Any]
) -> None:
    profile(config)
    output = CliRunner().invoke('tests', 'export', '--how', 'jira', '--create', *CREDENTIALS, '.')
    assert output.exit_code != 0
    assert not fake_jira.created_issues
    assert find_test_node(fmf_root).get(ID_KEY) is None


@pytest.mark.parametrize('dry', [False, True])
@pytest.mark.parametrize('existing', [False, True])
def test_external_extension_reuses_exporter(
    fmf_root: Path, fake_jira: FakeJiraClient, profile: Any, dry: bool, existing: bool
) -> None:
    import runpy

    example = Path(__file__).resolve().parents[2] / 'examples' / 'plugins' / 'jira_export.py'
    exporter = runpy.run_path(str(example))['SiteJiraExporter']
    with find_test_node(fmf_root) as data:
        data.update(id='known-uuid', tag=['smoke'])
    if existing:
        fake_jira.search_result = {'issues': [{'key': 'RHELTEST-42'}]}
    reset_common()
    tmt.base.core.Test.store_cli_invocation(
        None,
        options={
            'jira_url': 'https://issues.redhat.com',
            'jira_user': 'me@example.com',
            'jira_token': 'dummy-token',
            'project_id': 'RHELTEST',
            'create': True,
            'dry': dry,
            'ignore_git_validation': True,
        },
    )
    profile({'uuid-field': 'ID', 'issue-type': 'Test Case', 'automation-url': None})
    logger = tmt.log.Logger.get_bootstrap_logger()
    test = tmt.base.core.Test(node=find_test_node(fmf_root), logger=logger)
    before = (fmf_root / 'test' / 'main.fmf').read_bytes()
    observed: list[tuple[Optional[str], bool, str, dict[str, Any]]] = []

    def post(resolved: tmt.base.core.Test, context: JiraExportContext) -> None:
        observed.append((context.issue_key, context.dry_run, resolved.name, context.fields))

    with (
        unittest.mock.patch.object(exporter, 'post_export', side_effect=post),
        unittest.mock.patch.object(
            exporter, 'enrich_payload', wraps=exporter.enrich_payload
        ) as enrich,
    ):
        exporter.export_test_collection([test])
    assert enrich.call_count == 1
    assert enrich.call_args.args[2]['labels'] == ['smoke', 'site-smoke']
    assert observed == [
        (
            ('RHELTEST-42' if existing else None if dry else 'RHELTEST-100'),
            dry,
            '/test',
            {'ID': 'customfield_10591'},
        )
    ]
    if dry:
        assert not fake_jira.created_issues
        assert all(issue.updated_fields is None for issue in fake_jira.issues.values())
        assert not fake_jira.created_remote_links
        assert not fake_jira.created_issue_links
        assert not fake_jira.transitioned
    else:
        fields = (
            fake_jira.issues['RHELTEST-42'].updated_fields
            if existing
            else fake_jira.created_issues[0]
        )
        assert fields is not None
        assert fields['labels'] == ['smoke', 'site-smoke']
        assert fields['customfield_10591'] == 'known-uuid'
    assert (fmf_root / 'test' / 'main.fmf').read_bytes() == before


def test_payload_hook_cannot_change_identity(fmf_root: Path, fake_jira: FakeJiraClient) -> None:
    def enrich(
        test: tmt.base.core.Test, context: JiraExportContext, fields: dict[str, Any]
    ) -> None:
        fields['customfield_10591'] = 'replacement-uuid'

    with unittest.mock.patch.object(JiraExporter, 'enrich_payload', side_effect=enrich):
        output = CliRunner().invoke(
            'tests', 'export', '--how', 'jira', '--create', *CREDENTIALS, '.'
        )
    assert output.exit_code != 0
    assert 'must preserve identity' in str(output.exception)
    assert not fake_jira.created_issues


def test_selected_uuid_collision_fails_before_writes(
    tmp_path: Path, fake_jira: FakeJiraClient
) -> None:
    root = shared_tree(tmp_path, True)
    (root / 'main.fmf').write_text(
        (root / 'main.fmf').read_text().replace('second-uuid', 'first-uuid')
    )
    output = export_shared(root, '--ignore-git-validation')
    assert output.exit_code != 0
    assert 'Multiple selected tests share UUID' in str(output.exception)
    assert not fake_jira.created_issues


@pytest.mark.parametrize('values', [{'1': 'First'}, {'2': 'Second'}])
def test_select_mapping_translates_only_configured_values(
    fmf_root: Path, fake_jira: FakeJiraClient, profile: Any, values: dict[str, str]
) -> None:
    profile({'fields': {'Tier': {'source': 'tier', 'type': 'single-select', 'values': values}}})
    fake_jira.fields_response.append({'id': 'customfield_3', 'name': 'Tier'})
    with find_test_node(fmf_root) as data:
        data['tier'] = '1'
    output = CliRunner().invoke('tests', 'export', '--how', 'jira', '--create', *CREDENTIALS, '.')
    if '1' in values:
        assert output.exit_code == 0, output.exception
        assert fake_jira.created_issues[0]['customfield_3'] == {'value': 'First'}
    else:
        assert output.exit_code != 0
        assert 'No configured value' in str(output.exception)
        assert not fake_jira.created_issues


def test_cli_schema_overrides_profile(
    fmf_root: Path, fake_jira: FakeJiraClient, profile: Any
) -> None:
    profile(
        {
            'project': 'OTHER',
            'issue-type': 'Unknown',
            'uuid-field': 'Absent',
            'automation-url': 'Absent',
            'title': '{summary}',
            'status': 'Unavailable',
        }
    )
    output = CliRunner().invoke(
        'tests',
        'export',
        '--how',
        'jira',
        '--create',
        *CREDENTIALS,
        '--jira-title',
        'case {name}',
        '--jira-status',
        'none',
        '--jira-automation-url',
        'none',
        '.',
    )
    assert output.exit_code == 0, output.exception
    assert fake_jira.created_issues[0]['summary'] == 'case /test'
    assert fake_jira.created_issues[0]['project'] == {'key': 'RHELTEST'}
    assert not fake_jira.transitioned
    assert 'customfield_10933' not in fake_jira.created_issues[0]
    assert not fake_jira.created_remote_links


def test_duplicate_issue_type_and_transition_are_explicit(
    fake_jira: FakeJiraClient, jira_instance: JiraInstance
) -> None:
    fake_jira.issue_types_response.append(FakeIssueType('10300', 'Test Case'))
    with pytest.raises(ExportError, match='Multiple issue types'):
        jira_instance.resolve_issue_type_id('RHELTEST', 'Test Case')
    assert jira_instance.resolve_issue_type_id('RHELTEST', '10300') == '10300'
    fake_jira.transitions_response.append({'id': '5', 'to': {'name': 'Active'}})
    with pytest.raises(ExportError, match='Multiple transitions'):
        jira_instance.resolve_transition_id('RHELTEST-1', 'Active')


@pytest.mark.parametrize('reverse', [False, True])
def test_ambiguous_contacts_are_preserved_and_cached(
    jira_instance: JiraInstance, fake_jira: FakeJiraClient, reverse: bool
) -> None:
    fake_jira.users = [
        FakeUser('one', 'one@example.com', display_name='John Smith'),
        FakeUser('two', 'two@example.com', display_name='John Smith'),
    ]
    if reverse:
        fake_jira.users.reverse()
    with unittest.mock.patch.object(jira_instance.logger, 'warning') as warning:
        assert jira_instance.resolve_account_id('John Smith') is None
        assert jira_instance.resolve_account_id('john smith') is None
    assert 'Ambiguous Jira contact' in warning.call_args.args[0]
    assert fake_jira.account_queries == ['John Smith']


def test_account_resolution_prefers_email_and_caches_misses(
    jira_instance: JiraInstance, fake_jira: FakeJiraClient
) -> None:
    fake_jira.users = [
        FakeUser('named', 'other@example.com', display_name='john@example.com'),
        FakeUser('email', 'john@example.com', display_name='John Smith'),
    ]
    assert jira_instance.resolve_account_id('john@example.com') == 'email'
    assert jira_instance.resolve_account_id('john@example.com') == 'email'
    assert jira_instance.resolve_account_id('Missing Person') is None
    assert jira_instance.resolve_account_id('Missing Person') is None
    assert fake_jira.account_queries == ['john@example.com', 'Missing Person']


@pytest.mark.parametrize(
    'matches', [[], [{'key': 'RHELTEST-1'}], [{'key': 'RHELTEST-1'}, {'key': 'RHELTEST-2'}]]
)
def test_shared_uuid_lookup(
    jira_instance: JiraInstance, fake_jira: FakeJiraClient, matches: list[dict[str, str]]
) -> None:
    fake_jira.search_result = {'issues': matches}
    kwargs = {'project_id': 'RHELTEST', 'issue_type': 'Test Case', 'uuid_field': 'ID'}
    if len(matches) > 1:
        with pytest.raises(ExportError, match='Multiple Jira issues match UUID'):
            jira_instance.find_issue_by_uuid('known-uuid', **kwargs)
    else:
        assert jira_instance.find_issue_by_uuid('known-uuid', **kwargs) == (
            matches[0]['key'] if matches else None
        )
    assert fake_jira.searches == [
        ('project="RHELTEST" AND issuetype="10239" AND cf[10591]="known-uuid"', 2)
    ]


@pytest.mark.parametrize(
    'scenario',
    [
        'same-restored-uuid',
        'same-key-local-ids',
        'same-key-generated-ids',
        'distinct-keys-same-uuid',
        'distinct',
    ],
)
def test_prepared_collection_identity_uniqueness(
    tmp_path: Path, fake_jira: FakeJiraClient, scenario: str
) -> None:
    import tmt.utils

    root = Path(tmp_path) / 'identity'
    fmf.Tree.init(path=root)
    same_key = scenario.startswith('same-')
    keys = ['RHELTEST-1', 'RHELTEST-1' if same_key else 'RHELTEST-2']
    metadata: dict[str, Any] = {'test': '/bin/true'}
    for index, name in enumerate(['/first', '/second']):
        metadata[name] = {
            'summary': name,
            'link': [{'implements': f'https://issues.redhat.com/browse/{keys[index]}'}],
        }
        if scenario == 'same-key-local-ids':
            metadata[name]['id'] = f'local-uuid-{index}'
        jira_uuid = (
            None
            if scenario.startswith('same-key')
            else 'restored-uuid'
            if scenario != 'distinct'
            else f'uuid-{index}'
        )
        fake_jira.issues[keys[index]] = FakeIssue(
            keys[index], custom_fields={'customfield_10591': jira_uuid}
        )
    source = root / 'main.fmf'
    source.write_text(tmt.utils.to_yaml(metadata))
    init_git(root)
    before = source.read_bytes()
    output = export_shared(root)
    if scenario == 'distinct':
        assert output.exit_code == 0, output.exception
        assert [fmf.Tree(root).find(name).get(ID_KEY) for name in ('/first', '/second')] == [
            'uuid-0',
            'uuid-1',
        ]
        assert all(issue.updated_fields is not None for issue in fake_jira.issues.values())
    else:
        assert output.exit_code != 0
        expected = 'target Jira issue' if scenario.startswith('same-key') else 'share UUID'
        assert expected in str(output.exception)
        assert source.read_bytes() == before
        assert not git(root, 'status', '--porcelain')
        assert all(issue.updated_fields is None for issue in fake_jira.issues.values())
    assert not fake_jira.created_issues


def test_invalid_title_does_not_persist_generated_uuids(
    tmp_path: Path, fake_jira: FakeJiraClient
) -> None:
    root = shared_tree(tmp_path, False)
    before = (root / 'main.fmf').read_bytes()
    output = export_shared(root, '--jira-title', '{unsupported}')
    assert output.exit_code != 0
    assert 'Invalid Jira title' in str(output.exception)
    assert (root / 'main.fmf').read_bytes() == before
    assert not fake_jira.created_issues


def test_late_value_mapping_failure_prevents_all_writes(
    tmp_path: Path, fake_jira: FakeJiraClient, profile: Any
) -> None:
    root = shared_tree(tmp_path, False)
    source = root / 'main.fmf'
    source.write_text(
        source.read_text()
        .replace('summary: First', 'summary: First\n  tier: 1')
        .replace('summary: Second', 'summary: Second\n  tier: 2')
    )
    git(root, 'add', 'main.fmf')
    git(root, '-c', 'core.hooksPath=/dev/null', 'commit', '-m', 'Tiers')
    git(root, 'update-ref', 'refs/remotes/origin/main', 'HEAD')
    fake_jira.fields_response.append({'id': 'customfield_3', 'name': 'Tier'})
    profile(
        {'fields': {'Tier': {'source': 'tier', 'type': 'single-select', 'values': {'1': 'First'}}}}
    )
    before = source.read_bytes()
    output = export_shared(root)
    assert output.exit_code != 0
    assert 'No configured value' in str(output.exception)
    assert source.read_bytes() == before
    assert not fake_jira.created_issues


@pytest.mark.parametrize('dry', [False, True])
def test_invalid_relationship_fails_during_preparation(
    fmf_root: Path, fake_jira: FakeJiraClient, profile: Any, dry: bool
) -> None:
    profile({'links': {'verifies': {'issue-type': 'Missing relationship'}}})
    before = (fmf_root / 'test' / 'main.fmf').read_bytes()
    output = CliRunner().invoke(
        'tests',
        'export',
        '--how',
        'jira',
        '--create',
        *CREDENTIALS,
        *(['--dry'] if dry else []),
        '.',
    )
    assert output.exit_code != 0
    assert 'Expected one Jira relationship type' in str(output.exception)
    assert (fmf_root / 'test' / 'main.fmf').read_bytes() == before
    assert not fake_jira.created_issues


@pytest.mark.parametrize('failure', ['missing-field', 'bad-option', 'bad-type', 'required-clear'])
def test_field_metadata_is_validated_before_writes(
    fmf_root: Path, fake_jira: FakeJiraClient, profile: Any, failure: str
) -> None:
    fake_jira.fields_response.append({'id': 'customfield_3', 'name': 'Tier'})
    profile({'fields': {'Tier': {'source': 'tier', 'type': 'single-select'}}})
    with find_test_node(fmf_root) as data:
        data['tier'] = None if failure == 'required-clear' else '2'
    metadata = fake_jira._field_metadata()
    if failure == 'missing-field':
        del metadata['customfield_3']
    elif failure == 'bad-option':
        metadata['customfield_3']['allowedValues'] = [{'value': '1'}]
    elif failure == 'bad-type':
        metadata['customfield_3']['schema']['type'] = 'string'
    else:
        metadata['customfield_3']['required'] = True
    fake_jira.field_metadata_override = metadata
    before = (fmf_root / 'test' / 'main.fmf').read_bytes()
    output = CliRunner().invoke('tests', 'export', '--how', 'jira', '--create', *CREDENTIALS, '.')
    assert output.exit_code != 0
    assert (fmf_root / 'test' / 'main.fmf').read_bytes() == before
    assert not fake_jira.created_issues


@pytest.mark.parametrize('dry', [False, True])
def test_required_reporter_with_jira_default_can_be_omitted(
    fmf_root: Path, fake_jira: FakeJiraClient, dry: bool
) -> None:
    # RHELTEST's Cloud create metadata reports this implicit user default.
    metadata = fake_jira._field_metadata()
    metadata['reporter'] = {
        'key': 'reporter',
        'required': True,
        'hasDefaultValue': True,
        'schema': {'type': 'user', 'system': 'reporter'},
        'operations': ['set'],
    }
    fake_jira.field_metadata_override = metadata
    before = (fmf_root / 'test' / 'main.fmf').read_bytes()
    output = CliRunner().invoke(
        'tests',
        'export',
        '--how',
        'jira',
        '--create',
        *CREDENTIALS,
        *(['--dry'] if dry else []),
        '.',
    )
    assert output.exit_code == 0, output.exception
    if dry:
        assert not fake_jira.created_issues
        assert (fmf_root / 'test' / 'main.fmf').read_bytes() == before
    else:
        assert len(fake_jira.created_issues) == 1
        assert 'reporter' not in fake_jira.created_issues[0]


@pytest.mark.parametrize('dry', [False, True])
def test_missing_required_field_without_default_prevents_writes(
    fmf_root: Path, fake_jira: FakeJiraClient, dry: bool
) -> None:
    metadata = fake_jira._field_metadata()
    metadata['customfield_12345'] = {
        'required': True,
        'hasDefaultValue': False,
        'schema': {'type': 'string', 'customId': 12345},
    }
    fake_jira.field_metadata_override = metadata
    before = (fmf_root / 'test' / 'main.fmf').read_bytes()
    output = CliRunner().invoke(
        'tests',
        'export',
        '--how',
        'jira',
        '--create',
        *CREDENTIALS,
        *(['--dry'] if dry else []),
        '.',
    )
    assert output.exit_code != 0
    assert "Missing required Jira field 'customfield_12345'" in str(output.exception)
    assert not fake_jira.created_issues
    assert (fmf_root / 'test' / 'main.fmf').read_bytes() == before


def test_dry_run_displays_fields_clears_links_and_transitions(
    fmf_root: Path, fake_jira: FakeJiraClient, profile: Any
) -> None:
    profile(
        {
            'status': 'Active',
            'fields': {'Tier': {'source': 'tier', 'type': 'single-select'}},
            'links': {'verifies': {'issue-type': 'Tests', 'remote': True}},
        }
    )
    fake_jira.fields_response.append({'id': 'customfield_3', 'name': 'Tier'})
    with find_test_node(fmf_root) as data:
        data.update(
            id='known-uuid',
            tier=1,
            summary=None,
            description=None,
            tag=[],
            component=[],
            contact=[],
        )
        data['link'] = [
            {'verifies': 'https://issues.redhat.com/browse/REQ-1'},
            {'verifies': 'https://external.example.com/requirement'},
        ]
    fake_jira.search_result = {'issues': [{'key': 'RHELTEST-42'}]}
    before = (fmf_root / 'test' / 'main.fmf').read_bytes()
    with unittest.mock.patch.object(
        tmt.base.core.Test, 'web_link', return_value='https://automation.example.com/test'
    ):
        output = CliRunner().invoke('tests', 'export', '--how', 'jira', '--dry', *CREDENTIALS, '.')
    assert output.exit_code == 0, output.exception
    for text in (
        'customfield_3:',
        "value: '1'",
        'https://automation.example.com/test',
        'description: null',
        'labels: []',
        'components: []',
        'type: Tests',
        'target: REQ-1',
        'direction: outward',
        'https://external.example.com/requirement',
        'status: Active',
        "id: '3'",
    ):
        assert text in output.output
    assert (fmf_root / 'test' / 'main.fmf').read_bytes() == before
    assert not fake_jira.created_issues
    assert not fake_jira.created_remote_links
    assert not fake_jira.created_issue_links
    assert not fake_jira.transitioned
    assert all(issue.updated_fields is None for issue in fake_jira.issues.values())


def test_ambiguous_assignee_is_omitted_from_update(
    fmf_root: Path, fake_jira: FakeJiraClient, caplog: pytest.LogCaptureFixture
) -> None:
    with find_test_node(fmf_root) as data:
        data.update(id='known-uuid', contact=['John Smith'])
    fake_jira.users = [
        FakeUser('one', 'one@example.com', 'John Smith'),
        FakeUser('two', 'two@example.com', 'John Smith'),
    ]
    fake_jira.search_result = {'issues': [{'key': 'RHELTEST-42'}]}
    output = CliRunner().invoke('tests', 'export', '--how', 'jira', *CREDENTIALS, '.')
    assert output.exit_code == 0, output.exception
    assert 'Ambiguous Jira contact' in caplog.text
    assert 'Could not resolve Jira account' in output.output
    assert 'assignee' not in fake_jira.issues['RHELTEST-42'].updated_fields


def test_portable_profiles_layer_over_defaults_and_accept_cli_overrides(
    tmp_path: Path,
    fmf_root: Path,
    fake_jira: FakeJiraClient,
    profile: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import os

    config_root = os.environ['TMT_CONFIG_DIR']
    profile({'project': 'USER', 'uuid-field': 'ID', 'title': '{summary}'})
    base = Path(tmp_path) / 'team.yaml'
    base.write_text(
        "project: RHELTEST\nissue-type: Test Case\nuuid-field: ID\n"
        "fields:\n  Tier:\n    source: tier\n    type: single-select\n"
        "    values: {'1': 'First', '2': 'Second'}\n"
    )
    overrides = Path(tmp_path) / 'repo.yaml'
    overrides.write_text(
        "title: '{name}'\nmanaged-fields: [summary, description, components]\n"
        "fields:\n  Tier:\n    values: {'1': '1'}\n"
    )
    fake_jira.fields_response.append({'id': 'customfield_3', 'name': 'Tier'})
    with find_test_node(fmf_root) as data:
        data.update(id='known-uuid', tier=1, tag=['Jira-owned'], contact=['John Smith'])
    output = CliRunner().invoke(
        'tests',
        'export',
        '--how',
        'jira',
        '--create',
        *CREDENTIALS[:6],
        '--ignore-git-validation',
        '--jira-profile',
        str(base),
        '--jira-profile',
        str(overrides),
        '--jira-title',
        'CLI {name}',
        '.',
    )
    assert output.exit_code == 0, output.exception
    fields = fake_jira.created_issues[0]
    assert fields['summary'] == 'CLI /test'
    assert fields['project'] == {'key': 'RHELTEST'}
    assert fields['customfield_3'] == {'value': '1'}
    assert 'labels' not in fields
    assert 'assignee' not in fields
    assert not fake_jira.account_queries
    assert os.environ['TMT_CONFIG_DIR'] == config_root


def test_profile_can_clear_inherited_relationships(
    tmp_path: Path, fmf_root: Path, fake_jira: FakeJiraClient
) -> None:
    base = Path(tmp_path) / 'base.yaml'
    base.write_text('links:\n  verifies:\n    issue-type: Missing type\n')
    override = Path(tmp_path) / 'override.yaml'
    override.write_text('links: {}\n')
    output = CliRunner().invoke(
        'tests',
        'export',
        '--how',
        'jira',
        '--create',
        *CREDENTIALS,
        '--jira-profile',
        str(base),
        '--jira-profile',
        str(override),
        '.',
    )
    assert output.exit_code == 0, output.exception
    assert fake_jira.created_issues


@pytest.mark.parametrize('override', [False, True])
def test_credentials_from_environment_and_cli_precedence(
    fmf_root: Path, fake_jira: FakeJiraClient, monkeypatch: pytest.MonkeyPatch, override: bool
) -> None:
    monkeypatch.setenv('TMT_JIRA_URL', 'https://issues.redhat.com')
    monkeypatch.setenv('TMT_JIRA_USER', 'env@example.com')
    monkeypatch.setenv('TMT_JIRA_TOKEN', 'environment-test-token')
    with unittest.mock.patch('jira.JIRA', return_value=fake_jira) as constructor:
        output = CliRunner().invoke(
            'tests',
            'export',
            '--how',
            'jira',
            '--create',
            '--dry',
            *CREDENTIALS[6:],
            *(['--jira-user', 'cli@example.com'] if override else []),
            '.',
        )
    assert output.exit_code == 0, output.exception
    assert constructor.call_args.kwargs['basic_auth'] == (
        'cli@example.com' if override else 'env@example.com',
        'environment-test-token',
    )
    assert 'environment-test-token' not in output.output


def test_credentials_reuse_personal_link_settings(
    fmf_root: Path, fake_jira: FakeJiraClient
) -> None:
    import os

    (Path(os.environ['TMT_CONFIG_DIR']) / 'link.fmf').write_text(
        'issue-tracker:\n  - type: jira\n    url: https://issues.redhat.com\n'
        '    tmt-web-url: https://tmt.example.com\n    email: settings@example.com\n'
        '    token: personal-test-token\n'
    )
    with unittest.mock.patch('jira.JIRA', return_value=fake_jira) as constructor:
        output = CliRunner().invoke(
            'tests', 'export', '--how', 'jira', '--create', *CREDENTIALS[6:], '.'
        )
    assert output.exit_code == 0, output.exception
    assert constructor.call_args.kwargs['basic_auth'] == (
        'settings@example.com',
        'personal-test-token',
    )


def test_unmanaged_fields_are_preserved_and_managed_components_clear(
    fmf_root: Path, fake_jira: FakeJiraClient, profile: Any
) -> None:
    profile({'managed-fields': ['components']})
    with find_test_node(fmf_root) as data:
        data.update(
            id='known-uuid',
            summary='Local title',
            description='Local details',
            tag=['local-label'],
            contact=['John Smith'],
            component=[],
        )
    fake_jira.search_result = {'issues': [{'key': 'RHELTEST-42'}]}
    output = CliRunner().invoke('tests', 'export', '--how', 'jira', *CREDENTIALS, '.')
    assert output.exit_code == 0, output.exception
    payload = fake_jira.issues['RHELTEST-42'].updated_fields
    assert payload['components'] == []
    assert all(field not in payload for field in ('summary', 'description', 'labels', 'assignee'))
    assert not fake_jira.account_queries


@pytest.mark.parametrize('ownership', [[], ['invented-field']])
def test_empty_or_invalid_ownership_on_creation(
    fmf_root: Path, fake_jira: FakeJiraClient, profile: Any, ownership: list[str]
) -> None:
    profile({'managed-fields': ownership})
    output = CliRunner().invoke('tests', 'export', '--how', 'jira', '--create', *CREDENTIALS, '.')
    if ownership:
        assert output.exit_code != 0
        assert not fake_jira.created_issues
    else:
        assert output.exit_code == 0, output.exception
        assert 'summary' in fake_jira.created_issues[0]
        assert 'labels' not in fake_jira.created_issues[0]


@pytest.mark.parametrize('existing', [False, True])
def test_workflow_failures_prevent_writes(
    fmf_root: Path, fake_jira: FakeJiraClient, existing: bool
) -> None:
    if existing:
        with find_test_node(fmf_root) as data:
            data[ID_KEY] = 'known-uuid'
        fake_jira.search_result = {'issues': [{'key': 'RHELTEST-42'}]}
        fake_jira.transitions_response = []
    before = (fmf_root / 'test' / 'main.fmf').read_bytes()
    output = CliRunner().invoke(
        'tests',
        'export',
        '--how',
        'jira',
        '--create',
        *CREDENTIALS,
        '--jira-status',
        'Active' if existing else 'Missing status',
        '.',
    )
    assert output.exit_code != 0
    assert (fmf_root / 'test' / 'main.fmf').read_bytes() == before
    assert not fake_jira.created_issues
    assert all(issue.updated_fields is None for issue in fake_jira.issues.values())


def test_missing_requirement_is_checked_before_creation(
    fmf_root: Path, fake_jira: FakeJiraClient, profile: Any
) -> None:
    profile({'links': {'verifies': {'issue-type': 'Tests'}}})
    with find_test_node(fmf_root) as data:
        data['link'] = [{'verifies': 'https://issues.redhat.com/browse/REQ-1'}]
    fake_jira.nonexistent_issues.add('REQ-1')
    before = (fmf_root / 'test' / 'main.fmf').read_bytes()
    output = CliRunner().invoke('tests', 'export', '--how', 'jira', '--create', *CREDENTIALS, '.')
    assert output.exit_code != 0
    assert (fmf_root / 'test' / 'main.fmf').read_bytes() == before
    assert not fake_jira.created_issues


def test_apply_failure_reports_completed_work_and_retains_identity(
    tmp_path: Path, fake_jira: FakeJiraClient
) -> None:
    import jira

    root = shared_tree(tmp_path, False)
    with unittest.mock.patch.object(
        fake_jira,
        'create_issue',
        side_effect=[
            FakeIssue('RHELTEST-1'),
            jira.JIRAError(status_code=503, text='Temporary failure'),
        ],
    ):
        output = export_shared(root)
    assert output.exit_code != 0
    assert "Completed tests: ['/first']" in str(output.exception)
    assert 'Current test may have partial writes' in str(output.exception)
    assert all(fmf.Tree(root).find(name).get(ID_KEY) for name in ('/first', '/second'))


def test_cloud_create_field_metadata_uses_real_sdk_transport_and_pagination(
    jira_instance: JiraInstance,
) -> None:
    import json

    import requests
    from jira.client import JIRA

    # Use real SDK URL construction and JSON decoding, without opening a session.
    client = JIRA.__new__(JIRA)
    client.deploymentType = 'Cloud'
    client._version = (0, 0, 0)
    client._options = {
        'server': 'https://example.invalid',
        'rest_path': 'api',
        'rest_api_version': '3',
    }
    client._session = unittest.mock.Mock()
    responses = []
    for field_id in ('summary', 'customfield_1'):
        response = requests.Response()
        response.status_code = 200
        response._content = json.dumps(
            {'fields': [{'fieldId': field_id, 'required': True}], 'total': 2}
        ).encode()
        responses.append(response)
    client._session.get.side_effect = responses
    jira_instance.jira = client
    metadata = jira_instance.field_metadata('QA', '7')
    assert set(metadata) == {'summary', 'customfield_1'}
    assert jira_instance.field_metadata('QA', '7') == metadata
    assert client._session.get.call_count == 2
    assert [call.kwargs['params']['startAt'] for call in client._session.get.call_args_list] == [
        0,
        1,
    ]
    assert (
        client._session.get.call_args.args[0]
        == 'https://example.invalid/rest/api/3/issue/createmeta/QA/issuetypes/7'
    )


@pytest.mark.parametrize('cloud', [False, True])
def test_workflow_status_validation_uses_real_sdk_project_statuses(
    jira_instance: JiraInstance, cloud: bool
) -> None:
    import json

    import requests
    from jira.client import JIRA

    client = JIRA.__new__(JIRA)
    client.deploymentType = 'Cloud' if cloud else 'Server'
    client._options = {
        'server': 'https://example.invalid',
        'rest_path': 'api',
        'rest_api_version': '3' if cloud else '2',
    }
    client._session = unittest.mock.Mock()
    responses = []
    for status_name in ('Active', 'Retired'):
        response = requests.Response()
        response.status_code = 200
        response._content = json.dumps(
            [
                {
                    'id': '7',
                    'name': 'Scenario',
                    'subtask': False,
                    'statuses': [{'id': '3', 'name': status_name}],
                },
                {
                    'id': '8',
                    'name': 'Task',
                    'subtask': False,
                    'statuses': [{'id': '4', 'name': 'Done'}],
                },
            ]
        ).encode()
        responses.append(response)
    client._session.get.side_effect = responses
    jira_instance.jira = client

    # Exercise the real SDK method and resource decoding, not FakeIssueType.
    jira_instance.validate_status('QA', 'Scenario', 'Active')
    jira_instance.validate_status('QA', '7', 'Active')
    jira_instance.validate_status('QA', 'Task', 'Done')
    with pytest.raises(ExportError, match="Status 'Done' is not available"):
        jira_instance.validate_status('QA', '7', 'Done')
    with pytest.raises(ExportError, match="Status 'Active' is not available"):
        jira_instance.validate_status('OTHER', '7', 'Active')
    jira_instance.validate_status('OTHER', 'Scenario', 'Retired')

    api_version = '3' if cloud else '2'
    assert [call.args[0] for call in client._session.get.call_args_list] == [
        f'https://example.invalid/rest/api/{api_version}/project/{project}/statuses'
        for project in ('QA', 'OTHER')
    ]


@pytest.mark.parametrize('cloud', [False, True])
def test_search_uses_real_sdk_transport_and_preserves_server_routing(
    jira_instance: JiraInstance, cloud: bool
) -> None:
    import json

    import requests
    from jira.client import JIRA

    client = JIRA.__new__(JIRA)
    client.deploymentType = 'Cloud' if cloud else 'Server'
    client._options = {
        'server': 'https://example.invalid',
        'rest_path': 'api',
        'rest_api_version': '3' if cloud else '2',
        'default_batch_size': 50,
        'async': False,
    }
    client._fields_cache_value = {'key': 'key'}
    client._session = unittest.mock.Mock()
    response = requests.Response()
    response.status_code = 200
    response._content = json.dumps({'issues': [{'key': 'QA-1'}], 'isLast': True}).encode()
    client._session.get.return_value = response
    jira_instance.jira = client
    assert jira_instance.search_issues('project="QA"', max_results=2, fields=['key']) == [
        {'key': 'QA-1'}
    ]
    expected = (
        'https://example.invalid/rest/api/3/search/jql'
        if cloud
        else 'https://example.invalid/rest/api/2/search'
    )
    assert client._session.get.call_args.args[0] == expected
    assert client._session.get.call_args.kwargs['params']['maxResults'] == 2
    assert client._session.get.call_args.kwargs['params']['fields'] == ['key']


def test_cloud_uuid_lookup_detects_matches_on_later_pages(
    jira_instance: JiraInstance, fake_jira: FakeJiraClient
) -> None:
    fake_jira.deploymentType = 'Cloud'
    pages = [
        {'issues': [{'key': 'RHELTEST-1'}], 'nextPageToken': 'page-two', 'isLast': False},
        {'issues': [{'key': 'RHELTEST-2'}], 'isLast': True},
    ]
    with (
        unittest.mock.patch.object(fake_jira, '_get_json', side_effect=pages) as transport,
        pytest.raises(ExportError, match='Multiple Jira issues match UUID'),
    ):
        jira_instance.find_issue_by_uuid(
            'known-uuid', project_id='RHELTEST', issue_type='Test Case', uuid_field='ID'
        )
    assert [call.args[0] for call in transport.call_args_list] == ['search/jql', 'search/jql']
    assert [call.kwargs['params']['maxResults'] for call in transport.call_args_list] == [2, 1]
    assert 'nextPageToken' not in transport.call_args_list[0].kwargs['params']
    assert transport.call_args.kwargs['params']['nextPageToken'] == 'page-two'
    assert transport.call_args.kwargs['params']['maxResults'] == 1


@pytest.mark.parametrize('token', [None, 'repeated'])
def test_cloud_search_fails_on_stalled_pagination(
    jira_instance: JiraInstance, fake_jira: FakeJiraClient, token: Optional[str]
) -> None:
    fake_jira.deploymentType = 'Cloud'
    page = {'issues': [], 'isLast': False, 'nextPageToken': token}
    with (
        unittest.mock.patch.object(fake_jira, '_get_json', return_value=page),
        pytest.raises(ExportError, match='pagination did not advance'),
    ):
        jira_instance.search_issues('project="QA"')


@pytest.mark.parametrize(
    ('options', 'tier'),
    [
        (['1'], '1'),
        ([1], '1'),
        ([0], '0'),
        ([{'value': 0}], '0'),
        ([{'value': '1'}], '1'),
        ([{'name': '1'}], '1'),
        ([{'id': '10', 'value': '1'}], '1'),
    ],
)
def test_scalar_and_object_choices_prepare_successfully(
    tmp_path: Path, fake_jira: FakeJiraClient, profile: Any, options: list[Any], tier: str
) -> None:
    root = shared_tree(tmp_path, True)
    source = root / 'main.fmf'
    source.write_text(f'tier: "{tier}"\n' + source.read_text())
    git(root, 'add', 'main.fmf')
    git(root, '-c', 'core.hooksPath=/dev/null', 'commit', '-m', 'Tier fixture')
    git(root, 'update-ref', 'refs/remotes/origin/main', 'HEAD')
    fake_jira.fields_response.append({'id': 'customfield_3', 'name': 'Tier'})
    profile({'fields': {'Tier': {'source': 'tier', 'type': 'single-select'}}})
    metadata = fake_jira._field_metadata()
    metadata['customfield_3']['allowedValues'] = options
    fake_jira.field_metadata_override = metadata
    output = export_shared(root, '--dry')
    assert output.exit_code == 0, output.exception
    assert f"value: '{tier}'" in output.output
    assert not fake_jira.created_issues
    assert not git(root, 'status', '--porcelain')


@pytest.mark.parametrize(
    ('choice', 'valid'),
    [
        ({'id': '10'}, True),
        ({'id': 'missing'}, False),
        ({'id': '10', 'value': '2'}, False),
        ({'value': '2'}, True),
    ],
)
def test_id_based_choices_are_validated_consistently(
    fmf_root: Path, fake_jira: FakeJiraClient, profile: Any, choice: dict[str, str], valid: bool
) -> None:
    fake_jira.fields_response.append({'id': 'customfield_3', 'name': 'Tier'})
    profile({'fields': {'Tier': {'source': 'tier', 'type': 'single-select'}}})
    metadata = fake_jira._field_metadata()
    metadata['customfield_3']['allowedValues'] = [
        {'id': '10', 'value': '1'},
        {'id': '20', 'value': '2'},
    ]
    fake_jira.field_metadata_override = metadata
    with find_test_node(fmf_root) as data:
        data['tier'] = '1'
    before = (fmf_root / 'test' / 'main.fmf').read_bytes()

    def enrich(
        test: tmt.base.core.Test, context: JiraExportContext, fields: dict[str, Any]
    ) -> None:
        fields['customfield_3'] = choice

    with unittest.mock.patch.object(JiraExporter, 'enrich_payload', side_effect=enrich):
        output = CliRunner().invoke(
            'tests', 'export', '--how', 'jira', '--create', *CREDENTIALS, '--dry', '.'
        )
    assert (output.exit_code == 0) == valid, output.exception
    assert (fmf_root / 'test' / 'main.fmf').read_bytes() == before
    assert not fake_jira.created_issues


@pytest.mark.parametrize(
    'options', [None, {'value': '1'}, [None], [['1']], [{'unexpected': '1'}], [{'value': ['1']}]]
)
def test_unsupported_choices_raise_export_error_without_writes(
    fmf_root: Path, fake_jira: FakeJiraClient, profile: Any, options: Any
) -> None:
    fake_jira.fields_response.append({'id': 'customfield_3', 'name': 'Tier'})
    profile({'fields': {'Tier': {'source': 'tier', 'type': 'single-select'}}})
    with find_test_node(fmf_root) as data:
        data['tier'] = '1'
    metadata = fake_jira._field_metadata()
    metadata['customfield_3']['allowedValues'] = options
    fake_jira.field_metadata_override = metadata
    before = (fmf_root / 'test' / 'main.fmf').read_bytes()
    output = CliRunner().invoke('tests', 'export', '--how', 'jira', '--create', *CREDENTIALS, '.')
    assert output.exit_code != 0
    assert isinstance(output.exception, ExportError)
    assert 'Unsupported' in str(output.exception)
    assert (fmf_root / 'test' / 'main.fmf').read_bytes() == before
    assert not fake_jira.created_issues


@pytest.mark.parametrize('label', ['red', 'green'])
def test_scalar_payload_choices_are_checked(
    fmf_root: Path, fake_jira: FakeJiraClient, label: str
) -> None:
    with find_test_node(fmf_root) as data:
        data.update(id='known-uuid', tag=[label])
    metadata = fake_jira._field_metadata()
    metadata['labels']['allowedValues'] = ['red', 'blue']
    fake_jira.field_metadata_override = metadata
    before = (fmf_root / 'test' / 'main.fmf').read_bytes()
    output = CliRunner().invoke(
        'tests', 'export', '--how', 'jira', '--dry', '--create', *CREDENTIALS, '.'
    )
    assert (output.exit_code == 0) == (label == 'red'), output.exception
    assert (fmf_root / 'test' / 'main.fmf').read_bytes() == before
    assert not fake_jira.created_issues
