"""
Export tmt test cases to Jira as TestCase work items.
"""

import email.utils
import os
import re
from typing import Any, Optional

import requests
from click import echo

import tmt.base.core
import tmt.convert
import tmt.export
import tmt.utils.git
from tmt.identifier import ID_KEY, add_uuid_if_not_defined
from tmt.utils import ConvertError
from tmt.utils.themes import style

# TestCase issue type ID in RHELTEST
ISSUE_TYPE_TEST_CASE = '10239'

# TestCase workflow transition IDs
TRANSITION_ACTIVE = '3'
TRANSITION_RETIRED = '4'

# Jira custom fields (RHELTEST)
FIELD_TMT_ID = 'customfield_10591'  # tmt UUID (ID field)
FIELD_EXTERNAL_ISSUE_URL = 'customfield_10766'  # Polarion test case link
FIELD_URL = 'customfield_10933'  # repo/script link

# Issue link type for test case → requirement relationship
LINK_TYPE_TESTS = 'pair'  # outward="tests", inward="is tested by"

RE_BUGZILLA_ID = re.compile(r'bugzilla\.redhat\.com/show_bug\.cgi\?id=(\d+)')


def _make_session(user: str, token: str) -> requests.Session:
    """Create an authenticated requests session."""
    session = requests.Session()
    session.auth = (user, token)
    session.headers.update(
        {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        }
    )
    return session


def _text_to_adf(text: str) -> dict[str, Any]:
    """Convert plain text to Atlassian Document Format (ADF)."""
    paragraphs = [
        {
            'type': 'paragraph',
            'content': [{'type': 'text', 'text': line}],
        }
        for line in text.splitlines()
        if line.strip()
    ]
    return {
        'type': 'doc',
        'version': 1,
        'content': paragraphs or [{'type': 'paragraph', 'content': []}],
    }


def _api_request(
    session: requests.Session,
    method: str,
    url: str,
    **kwargs: Any,
) -> dict[str, Any]:
    """Make a Jira REST API call, raise ConvertError on non-2xx response."""
    try:
        response = session.request(method, url, **kwargs)
    except requests.RequestException as err:
        raise ConvertError(f"Jira request failed: {err}") from err
    if not response.ok:
        raise ConvertError(
            f"Jira API error {response.status_code} on {method} {url}: {response.text[:300]}"
        )
    return response.json() if response.content else {}


def _resolve_account_id(
    session: requests.Session,
    api_base: str,
    email: str,
) -> Optional[str]:
    """
    Resolve a Jira Cloud ``accountId`` from an email address.

    Jira Cloud's REST API no longer accepts a ``name`` (login) when
    assigning issues; an ``accountId`` looked up via the user search
    endpoint is required instead.

    The ``user/search`` endpoint performs a loose match and, when
    nothing really matches, has been observed to fall back to
    returning arbitrary unrelated users rather than an empty list.
    A candidate is therefore only accepted when its ``emailAddress``
    matches ``email`` exactly (case-insensitively); this can also
    legitimately fail to find an existing account whose email is
    hidden by that user's Jira privacy settings.
    """
    try:
        users = _api_request(session, 'GET', f'{api_base}/user/search', params={'query': email})
    except ConvertError:
        return None
    if not isinstance(users, list):
        return None
    for candidate in users:
        if candidate.get('emailAddress', '').lower() == email.lower():
            return candidate.get('accountId')
    return None


def find_jira_case_key(
    test: tmt.base.core.Test,
    session: requests.Session,
    api_base: str,
    project_id: str,
    url: str,
) -> Optional[str]:
    """
    Find an existing Jira TestCase key for the given test.

    Lookup order:
    1. An 'implements' link in fmf pointing to this Jira instance.
    2. tmt UUID stored in customfield_10591 (the ``ID`` field).
    """
    # 1. implements link pointing to this Jira instance
    if test.link:
        for link in test.link.get('implements'):
            target = str(link.target)
            prefix = f'{url}/browse/'
            if target.startswith(prefix):
                key = target[len(prefix) :]
                echo(style(f"Found via implements link: '{key}'.", fg='blue'))
                return key

    # 2. UUID via cf[10591]
    uuid = test.node.get(ID_KEY)
    if uuid:
        result = _api_request(
            session,
            'POST',
            f'{api_base}/search/jql',
            json={
                'jql': (
                    f'project="{project_id}" AND issuetype="Test Case" AND cf[10591]="{uuid}"'
                ),
                'maxResults': 1,
                'fields': ['summary'],
            },
        )
        issues = result.get('issues', [])
        if issues:
            key = str(issues[0]['key'])
            echo(style(f"Found via UUID: '{key}'.", fg='blue'))
            return key

    return None


def _find_polarion_case_url(test: tmt.base.core.Test) -> Optional[str]:
    """
    Find the Polarion test case URL for this test.

    Checks 'implements' links in fmf first (written by a prior Polarion export),
    then falls back to a live Polarion API lookup when pylero is available.
    """
    if test.link:
        for link in test.link.get('implements'):
            if isinstance(link.target, tmt.base.core.FmfId):
                continue
            target = str(link.target)
            if 'polarion' in target.lower():
                return target

    # Live lookup — optional, requires pylero + ~/.pylero
    try:
        from tmt.export.polarion import (
            PolarionWorkItem,
            find_polarion_case_ids,
            import_polarion,
        )

        import_polarion()
        case_id, pol_project_id = find_polarion_case_ids(test.node)
        if case_id and pol_project_id:
            server_url = str(PolarionWorkItem._session._server.url).rstrip('/')
            return f'{server_url}/#/project/{pol_project_id}/workitem?id={case_id}'
    except Exception as error:
        test._logger.debug(f"Live Polarion lookup failed: {error}")

    return None


def _create_issue_links(
    test: tmt.base.core.Test,
    case_key: str,
    session: requests.Session,
    api_base: str,
    url: str,
) -> None:
    """
    Recreate fmf 'verifies' links as Jira issue links or remote links.

    - Links to issues on the same Jira instance become issue links of type 'pair'
      (RHELTEST tests RHEL-XXXX).
    - Links to Bugzilla become remote links on the TestCase.

    Existing links are checked first so repeated exports of the same
    test don't keep adding duplicates.
    """
    if not test.link:
        return

    browse_prefix = f'{url}/browse/'

    existing_issue = _api_request(session, 'GET', f'{api_base}/issue/{case_key}?fields=issuelinks')
    linked_keys = set()
    for issuelink in existing_issue.get('fields', {}).get('issuelinks', []):
        other = issuelink.get('inwardIssue') or issuelink.get('outwardIssue')
        if other:
            linked_keys.add(other['key'])

    existing_remote = _api_request(session, 'GET', f'{api_base}/issue/{case_key}/remotelink')
    linked_remote_urls: set[str] = (
        {remote_link['object']['url'] for remote_link in existing_remote}
        if isinstance(existing_remote, list)
        else set()
    )

    for link in test.link.get('verifies'):
        if isinstance(link.target, tmt.base.core.FmfId):
            continue
        target = str(link.target)

        # Same Jira instance — create a proper issue link
        if target.startswith(browse_prefix):
            req_key = target[len(browse_prefix) :]
            if req_key in linked_keys:
                echo(style('verifies: ', fg='green') + f'{req_key} (already linked)')
                continue
            try:
                _api_request(
                    session,
                    'POST',
                    f'{api_base}/issueLink',
                    json={
                        'type': {'name': LINK_TYPE_TESTS},
                        'outwardIssue': {'key': case_key},
                        'inwardIssue': {'key': req_key},
                    },
                )
                echo(style('verifies: ', fg='green') + req_key)
            except ConvertError as err:
                echo(style(f"Warning: could not link to '{req_key}': {err}", fg='yellow'))
            continue

        # Bugzilla — create a remote link
        bz_match = RE_BUGZILLA_ID.search(target)
        if bz_match:
            bz_id = bz_match.group(1)
            if target in linked_remote_urls:
                echo(style('verifies (BZ): ', fg='green') + f'{bz_id} (already linked)')
                continue
            try:
                _api_request(
                    session,
                    'POST',
                    f'{api_base}/issue/{case_key}/remotelink',
                    json={
                        'object': {
                            'url': target,
                            'title': f'BZ#{bz_id}',
                        },
                    },
                )
                echo(style('verifies (BZ): ', fg='green') + bz_id)
            except ConvertError as err:
                echo(style(f"Warning: could not add BZ remote link '{bz_id}': {err}", fg='yellow'))
            continue

        echo(style("Skipping unrecognised verifies link: ", fg='yellow') + target)


def _build_fields(
    project_id: str,
    summary: str,
    description: Optional[str],
    uuid: Optional[str],
    components: list[str],
    labels: list[str],
    contact_account_id: Optional[str],
    script_url: Optional[str],
    polarion_case_url: Optional[str],
    include_issuetype: bool = False,
) -> dict[str, Any]:
    """Assemble Jira field dict for create or update."""
    fields: dict[str, Any] = {'summary': summary}
    if include_issuetype:
        fields['project'] = {'key': project_id}
        fields['issuetype'] = {'id': ISSUE_TYPE_TEST_CASE}
    if description:
        fields['description'] = _text_to_adf(description)
    if uuid:
        fields[FIELD_TMT_ID] = uuid
    if components:
        fields['components'] = [{'name': c} for c in components]
    if labels:
        fields['labels'] = labels
    if contact_account_id:
        fields['assignee'] = {'accountId': contact_account_id}
    if script_url:
        fields[FIELD_URL] = script_url
    if polarion_case_url:
        fields[FIELD_EXTERNAL_ISSUE_URL] = polarion_case_url
    return fields


def _transition_case(
    session: requests.Session,
    api_base: str,
    key: str,
    enabled: bool,
) -> None:
    """Transition a TestCase to Active or Retired, skipping if already there."""
    target = 'Active' if enabled else 'Retired'
    current = _api_request(session, 'GET', f'{api_base}/issue/{key}?fields=status')
    current_status = current.get('fields', {}).get('status', {}).get('name')
    if current_status == target:
        return
    transition_id = TRANSITION_ACTIVE if enabled else TRANSITION_RETIRED
    _api_request(
        session,
        'POST',
        f'{api_base}/issue/{key}/transitions',
        json={'transition': {'id': transition_id}},
    )
    echo(style('status: ', fg='green') + target)


def export_to_jira(test: tmt.base.core.Test) -> None:
    """Export a single tmt test to a Jira TestCase."""
    url = (test.opt('jira_url') or os.environ.get('TMT_PLUGIN_EXPORT_JIRA_URL', '')).rstrip('/')
    token = test.opt('jira_token') or os.environ.get('TMT_PLUGIN_EXPORT_JIRA_TOKEN', '')
    user = test.opt('jira_user') or os.environ.get('TMT_PLUGIN_EXPORT_JIRA_USER', '')
    project_id = test.opt('project_id') or os.environ.get('TMT_PLUGIN_EXPORT_JIRA_PROJECT_ID', '')
    create = test.opt('create')
    duplicate = test.opt('duplicate')
    link_jira = test.opt('link_jira')
    ignore_git_validation = test.opt('ignore_git_validation')
    dry_mode = test.is_dry_run

    missing = [
        name
        for name, val in [
            ('--jira-url / TMT_PLUGIN_EXPORT_JIRA_URL', url),
            ('--jira-token / TMT_PLUGIN_EXPORT_JIRA_TOKEN', token),
            ('--jira-user / TMT_PLUGIN_EXPORT_JIRA_USER', user),
            ('--project-id / TMT_PLUGIN_EXPORT_JIRA_PROJECT_ID', project_id),
        ]
        if not val
    ]
    if missing:
        raise ConvertError(f"Missing required Jira options: {', '.join(missing)}.")

    valid, error_msg = tmt.utils.git.validate_git_status(test)
    if not valid:
        if ignore_git_validation:
            echo(style(f"Exporting regardless: '{error_msg}'.", fg='red'))
        else:
            raise ConvertError(
                f"Can't export due to '{error_msg}'.\n"
                "Use --ignore-git-validation to export regardless."
            )

    api_base = f'{url}/rest/api/3'
    session = _make_session(user, token)

    uuid = add_uuid_if_not_defined(test.node, dry_mode, test._logger)
    if not uuid:
        uuid = test.node.get(ID_KEY)

    summary = test.summary or test.name

    labels = list(test.tag)
    if test.tier is not None:
        labels.append(f'Tier{test.tier}')

    contact_account_id: Optional[str] = None
    if test.contact:
        addr = email.utils.parseaddr(test.contact[0])[1]
        if addr:
            contact_account_id = _resolve_account_id(session, api_base, addr)
            if not contact_account_id:
                echo(style(f"Warning: could not resolve Jira account for '{addr}'.", fg='yellow'))

    # Script URL: test-script link takes priority, then extra-task, then fmf repo URL
    script_url: Optional[str] = None
    if test.link:
        for link in test.link.get(relation='test-script'):
            if isinstance(link.target, str):
                script_url = link.target
                break
    if not script_url:
        if test.node.get('extra-task'):
            script_url = test.node.get('extra-task')
        elif not ignore_git_validation and test.fmf_id.url:
            script_url = test.fmf_id.url

    # Find or create TestCase
    case_key: Optional[str] = None
    if not duplicate:
        case_key = find_jira_case_key(test, session, api_base, project_id, url)

    # Polarion test case link — from implements links or live API lookup.
    # Only needed to build the fields for an actual create/update call, so
    # it's resolved lazily and not for a dry run.
    polarion_case_url: Optional[str] = None

    if case_key is None:
        if not create:
            raise ConvertError(
                f"Jira TestCase not found for '{test}'. Use --create to create a new test case."
            )
        if dry_mode:
            echo(style(f"Test case '{summary}' would be created.", fg='blue'))
        else:
            polarion_case_url = _find_polarion_case_url(test)
            fields = _build_fields(
                project_id,
                summary,
                test.description,
                uuid,
                test.component,
                labels,
                contact_account_id,
                script_url,
                polarion_case_url,
                include_issuetype=True,
            )
            response = _api_request(session, 'POST', f'{api_base}/issue', json={'fields': fields})
            case_key = response['key']
            echo(style(f"Test case '{case_key}' created.", fg='blue'))
    elif not dry_mode:
        polarion_case_url = _find_polarion_case_url(test)
        fields = _build_fields(
            project_id,
            summary,
            test.description,
            uuid,
            test.component,
            labels,
            contact_account_id,
            script_url,
            polarion_case_url,
        )
        _api_request(session, 'PUT', f'{api_base}/issue/{case_key}', json={'fields': fields})
        echo(style(f"Test case '{case_key}' updated.", fg='blue'))

    if polarion_case_url:
        echo(style('polarion: ', fg='green') + polarion_case_url)
    elif not dry_mode:
        echo(style('polarion: ', fg='yellow') + 'not found')

    echo(style('summary: ', fg='green') + summary)
    if uuid:
        echo(style('uuid: ', fg='green') + uuid)
    echo(style('labels: ', fg='green') + ' '.join(labels))
    echo(style('components: ', fg='green') + ' '.join(test.component))
    echo(style('enabled: ', fg='green') + str(test.enabled))

    if not dry_mode and case_key:
        _transition_case(session, api_base, case_key, test.enabled)
        _create_issue_links(test, case_key, session, api_base, url)

    if not dry_mode and link_jira and case_key:
        with test.node as data:
            tmt.convert.add_link(
                f'{url}/browse/{case_key}',
                data,
                system=tmt.convert.SYSTEM_OTHER,
                type_='implements',
            )
        echo(style('implements: ', fg='green') + f'{url}/browse/{case_key}')

    echo(style(f"Test case '{summary}' successfully exported to Jira.", fg='magenta'))


@tmt.base.core.Test.provides_export('jira')
class JiraExporter(tmt.export.ExportPlugin):
    """
    Export test metadata to Jira as ``Test Case`` work items.

    The ``--jira-url``, ``--jira-user``, ``--jira-token`` and
    ``--project-id`` options are required. They can also be provided
    via the corresponding ``TMT_PLUGIN_EXPORT_JIRA_*`` environment
    variables.

    Existing ``Test Case`` issues are located first by an ``implements``
    link in the fmf metadata pointing to the configured Jira instance,
    then by the tmt UUID stored in the ``ID`` custom field. Use
    ``--create`` to create a new ``Test Case`` when none is found, and
    ``--link-jira`` to write the Jira issue URL back into the fmf
    metadata as an ``implements`` link for future lookups.

    Polarion test case links present in ``implements`` fmf links or
    found via a live Polarion API lookup are preserved in the
    ``External issue URL`` custom field. ``verifies`` fmf links are
    recreated as Jira issue links (``tests`` type for issues on the
    same instance, remote links for Bugzilla URLs).

    .. code-block:: shell

        tmt tests export --how jira --create --link-jira \\
            --jira-url https://issues.redhat.com \\
            --jira-user me@example.com --jira-token TOKEN \\
            --project-id RHELTEST
    """

    @classmethod
    def export_test_collection(
        cls,
        tests: list[tmt.base.core.Test],
        keys: Optional[list[str]] = None,
        **kwargs: Any,
    ) -> str:
        """Export a collection of tests to Jira."""
        for test in tests:
            export_to_jira(test)
        return ''
