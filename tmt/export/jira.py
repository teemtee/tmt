"""
Export tmt test cases to Jira as TestCase work items.
"""

import email.utils
import re
from typing import Any, Optional

from click import echo

import tmt.base.core
import tmt.convert
import tmt.export
import tmt.utils.git
from tmt.identifier import ID_KEY, add_uuid_if_not_defined
from tmt.utils import ConvertError
from tmt.utils.jira import JiraInstance
from tmt.utils.themes import style

# Issue link type for test case → requirement relationship
LINK_TYPE_TESTS = 'pair'  # outward="tests", inward="is tested by"

RE_BUGZILLA_ID = re.compile(r'show_bug\.cgi\?(?:.*&)?id=(\d+)')


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


def find_jira_case_key(
    test: tmt.base.core.Test,
    jira_instance: JiraInstance,
    project_id: str,
    url: str,
    field_tmt_id: str,
) -> Optional[str]:
    """
    Find an existing Jira TestCase key for the given test.

    Lookup order:
    1. An 'implements' link in fmf pointing to this Jira instance.
    2. tmt UUID stored in ``field_tmt_id`` (the ``ID`` field).
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

    # 2. UUID via the ID custom field
    uuid = test.node.get(ID_KEY)
    if uuid:
        field_jql = JiraInstance.field_jql_id(field_tmt_id)
        issues = jira_instance.search_issues(
            f'project="{project_id}" AND issuetype="Test Case" AND cf[{field_jql}]="{uuid}"',
            max_results=1,
            fields=[],
        )
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
    jira_instance: JiraInstance,
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

    verifies_targets = [
        str(link.target)
        for link in test.link.get('verifies')
        if not isinstance(link.target, tmt.base.core.FmfId)
    ]
    if not verifies_targets:
        return

    import jira as jira_module

    browse_prefix = f'{url}/browse/'
    linked_keys = jira_instance.get_linked_issue_keys(case_key)
    linked_remote_urls = jira_instance.get_linked_remote_urls(case_key)

    for target in verifies_targets:
        # Same Jira instance — create a proper issue link
        if target.startswith(browse_prefix):
            req_key = target[len(browse_prefix) :]
            if req_key in linked_keys:
                echo(style('verifies: ', fg='green') + f'{req_key} (already linked)')
                continue
            try:
                jira_instance.jira.create_issue_link(
                    type=LINK_TYPE_TESTS, inwardIssue=req_key, outwardIssue=case_key
                )
                echo(style('verifies: ', fg='green') + req_key)
            except jira_module.JIRAError as err:
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
                jira_instance.jira.add_remote_link(
                    case_key, destination={'url': target, 'title': f'BZ#{bz_id}'}
                )
                echo(style('verifies (BZ): ', fg='green') + bz_id)
            except jira_module.JIRAError as err:
                echo(style(f"Warning: could not add BZ remote link '{bz_id}': {err}", fg='yellow'))
            continue

        echo(style("Skipping unrecognised verifies link: ", fg='yellow') + target)


def _build_fields(
    project_id: str,
    summary: str,
    description: Optional[str],
    uuid: str,
    components: list[str],
    labels: list[str],
    contact_account_id: Optional[str],
    script_url: Optional[str],
    polarion_case_url: Optional[str],
    field_ids: dict[str, str],
    issue_type_id: Optional[str] = None,
) -> dict[str, Any]:
    """
    Assemble Jira field dict for create or update.

    :param field_ids: resolved custom field IDs, keyed by ``'tmt_id'``,
        ``'url'`` and ``'external_issue_url'`` (see
        :py:meth:`JiraInstance.resolve_field_id`).
    :param issue_type_id: resolved ``Test Case`` issue type ID, only needed
        when creating a new issue.
    """
    fields: dict[str, Any] = {
        'summary': summary,
        field_ids['tmt_id']: uuid,
    }
    if issue_type_id:
        fields['project'] = {'key': project_id}
        fields['issuetype'] = {'id': issue_type_id}
    if description:
        fields['description'] = _text_to_adf(description)
    if components:
        fields['components'] = [{'name': c} for c in components]
    if labels:
        fields['labels'] = labels
    if contact_account_id:
        fields['assignee'] = {'accountId': contact_account_id}
    if script_url:
        fields[field_ids['url']] = script_url
    if polarion_case_url:
        fields[field_ids['external_issue_url']] = polarion_case_url
    return fields


def _transition_case(jira_instance: JiraInstance, key: str, enabled: bool) -> None:
    """Transition a TestCase to Active or Retired, skipping if already there."""
    target = 'Active' if enabled else 'Retired'
    current_status = jira_instance.jira.issue(key, fields='status').fields.status.name
    if current_status == target:
        return
    jira_instance.transition_issue(key, target)
    echo(style('status: ', fg='green') + target)


def export_to_jira(
    test: tmt.base.core.Test, jira_instance: Optional[JiraInstance] = None
) -> JiraInstance:
    """
    Export a single tmt test to a Jira TestCase.

    :param jira_instance: connection to reuse, e.g. across a batch of
        tests exported in one run; a new one is created and returned if
        not given.
    """
    create = test.opt('create')
    duplicate = test.opt('duplicate')
    link_jira = test.opt('link_jira')
    ignore_git_validation = test.opt('ignore_git_validation')
    dry_mode = test.is_dry_run

    required = ['jira_url', 'jira_token', 'jira_user', 'project_id']
    missing = [f"--{opt.replace('_', '-')}" for opt in required if not test.opt(opt)]
    if missing:
        raise ConvertError(f"Missing required Jira options: {', '.join(missing)}.")

    jira_url = test.opt('jira_url')
    token = test.opt('jira_token')
    user = test.opt('jira_user')
    project_id = test.opt('project_id')
    url = jira_url.rstrip('/')

    valid, error_msg = tmt.utils.git.validate_git_status(test)
    if not valid:
        if ignore_git_validation:
            echo(style(f"Exporting regardless: '{error_msg}'.", fg='red'))
        else:
            raise ConvertError(
                f"Can't export due to '{error_msg}'.\n"
                "Use --ignore-git-validation to export regardless."
            )

    if jira_instance is None:
        jira_instance = JiraInstance(url=url, email=user, token=token, logger=test._logger)

    field_tmt_id = jira_instance.resolve_field_id('ID')

    summary = test.summary or test.name

    labels = list(test.tag)
    if test.tier is not None:
        labels.append(f'Tier{test.tier}')

    contact_account_id: Optional[str] = None
    if test.contact:
        addr = email.utils.parseaddr(test.contact[0])[1]
        if addr:
            contact_account_id = jira_instance.resolve_account_id(addr)
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
        case_key = find_jira_case_key(test, jira_instance, project_id, url, field_tmt_id)

    # UUID always needs to exist in fmf data and Jira:
    # 1. From fmf if already defined.
    # 2. From existing Jira issue if available.
    # 3. Otherwise generate a new one and save into fmf data.
    uuid: Optional[str] = test.node.get(ID_KEY)

    # Polarion test case link — from implements links or live API lookup.
    # Only needed to build the fields for an actual create/update call, so
    # it's resolved lazily and not for a dry run.
    polarion_case_url: Optional[str] = None

    if case_key is None:
        if not create:
            raise ConvertError(
                f"Jira TestCase not found for '{test}'. Use --create to create a new test case."
            )
        if not uuid:
            uuid = add_uuid_if_not_defined(test.node, dry_mode, test._logger)
    elif not uuid:
        jira_issue = jira_instance.jira.issue(case_key)
        jira_uuid = getattr(jira_issue.fields, field_tmt_id, None)
        if not jira_uuid and hasattr(jira_issue, 'raw'):
            jira_uuid = jira_issue.raw.get('fields', {}).get(field_tmt_id)
        if jira_uuid:
            uuid = str(jira_uuid)
            if not dry_mode:
                with test.node as data:
                    data[ID_KEY] = uuid
        else:
            uuid = add_uuid_if_not_defined(test.node, dry_mode, test._logger)
    assert uuid is not None

    if not dry_mode:
        polarion_case_url = _find_polarion_case_url(test)
        field_ids = {
            'tmt_id': field_tmt_id,
            'url': jira_instance.resolve_field_id('URL'),
            'external_issue_url': jira_instance.resolve_field_id('External issue URL'),
        }
        issue_type_id = (
            jira_instance.resolve_issue_type_id(project_id, 'Test Case')
            if case_key is None
            else None
        )
        fields = _build_fields(
            project_id=project_id,
            summary=summary,
            description=test.description,
            uuid=uuid,
            components=test.component,
            labels=labels,
            contact_account_id=contact_account_id,
            script_url=script_url,
            polarion_case_url=polarion_case_url,
            field_ids=field_ids,
            issue_type_id=issue_type_id,
        )

    if case_key is None:
        if dry_mode:
            echo(style(f"Test case '{summary}' would be created.", fg='blue'))
        else:
            case_key = str(jira_instance.jira.create_issue(fields=fields).key)
            echo(style(f"Test case '{case_key}' created.", fg='blue'))
    elif dry_mode:
        echo(style(f"Test case '{case_key}' would be updated.", fg='blue'))
    else:
        jira_instance.jira.issue(case_key).update(fields=fields)
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
        _transition_case(jira_instance, case_key, test.enabled)
        _create_issue_links(test, case_key, jira_instance, url)

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

    return jira_instance


@tmt.base.core.Test.provides_export('jira')
class JiraExporter(tmt.export.ExportPlugin):
    """
    Export test metadata to Jira as ``Test Case`` work items.

    The ``--jira-url``, ``--jira-user``, ``--jira-token`` and
    ``--project-id`` options are required. Credentials can also be
    provided via the corresponding ``TMT_PLUGIN_EXPORT_JIRA_*``
    environment variables.

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
        jira_instance: Optional[JiraInstance] = None
        for test in tests:
            jira_instance = export_to_jira(test, jira_instance)
        return ''
