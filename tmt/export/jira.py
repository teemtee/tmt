"""
Export tmt test cases to Jira as TestCase work items.
"""

import email.utils
import re
from typing import Any, Optional

import tmt.base.core
import tmt.convert
import tmt.export
import tmt.log
import tmt.utils.git
from tmt.identifier import ID_KEY, add_uuid_if_not_defined
from tmt.utils import ExportError
from tmt.utils.jira import JiraInstance

# Issue link type for test case → requirement relationship
LINK_TYPE_TESTS = 'pair'  # outward="tests", inward="is tested by"

RE_BUGZILLA_ID = re.compile(r'show_bug\.cgi\?(?:.*&)?id=(\d+)')


@tmt.base.core.Test.provides_export('jira')
class JiraExporter(tmt.export.ExportPlugin):
    """
    Export test metadata to Jira as ``Test Case`` work items.

    The ``--jira-url``, ``--jira-user``, ``--jira-token`` and
    ``--project-id`` options are required.

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

    _logger: tmt.log.Logger = tmt.log.Logger.get_bootstrap_logger()

    @staticmethod
    def _text_to_adf(text: str) -> dict[str, Any]:
        """
        Convert plain text into Atlassian Document Format (ADF).

        Jira Cloud REST API v3 requires rich-text fields (such as
        ``description`` and comments) to be structured as an Atlassian
        Document Format (ADF) document tree rather than plain strings or
        legacy wiki markup. Passing a plain string causes the API to reject
        the request with a 400 Bad Request error.

        See: https://developer.atlassian.com/cloud/jira/platform/apis/document/structure/
        """
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

    @classmethod
    def _build_fields(
        cls,
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
            fields['description'] = cls._text_to_adf(description)
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

    @staticmethod
    def _find_case_key(
        test: tmt.base.core.Test,
        jira_instance: JiraInstance,
        project_id: str,
        url: str,
        field_tmt_id: str,
    ) -> Optional[str]:
        """
        Find an existing Jira TestCase key for the given test.

        Lookup order:

        1. An 'implements' link in fmf pointing to this Jira instance (verified for
           existence and Test Case type).
        2. tmt UUID stored in ``field_tmt_id`` (the ``ID`` field).
        """
        import jira as jira_module

        if test.link:
            for link in test.link.get('implements'):
                if isinstance(link.target, tmt.base.core.FmfId):
                    continue
                target = str(link.target)
                prefix = f'{url}/browse/'
                if target.startswith(prefix):
                    key = target[len(prefix) :].strip()
                    try:
                        issue = jira_instance.jira.issue(key, fields='issuetype')
                    except jira_module.JIRAError:
                        test._logger.warning(
                            f"Jira issue '{key}' from implements link not found in Jira."
                        )
                        continue
                    issue_type_obj = getattr(getattr(issue, 'fields', None), 'issuetype', None)
                    type_name = getattr(issue_type_obj, 'name', '')
                    if type_name != 'Test Case':
                        test._logger.warning(
                            f"Jira issue '{key}' from implements link is not a "
                            f"'Test Case' (type: '{type_name}')."
                        )
                        continue
                    test._logger.print(f"Found via implements link: '{key}'.", color='blue')
                    return key

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
                test._logger.print(f"Found via UUID: '{key}'.", color='blue')
                return key

        return None

    @staticmethod
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

    @staticmethod
    def _find_script_url(test: tmt.base.core.Test) -> Optional[str]:
        """Find the test script URL from test-script links, extra-task, or git repo URL."""
        if test.link:
            for link in test.link.get(relation='test-script'):
                if isinstance(link.target, str):
                    return link.target
        if test.node.get('extra-task'):
            return str(test.node.get('extra-task'))
        if not test.opt('ignore_git_validation') and test.fmf_id.url:
            return test.fmf_id.url
        return None

    @staticmethod
    def _resolve_contact(test: tmt.base.core.Test, jira_instance: JiraInstance) -> Optional[str]:
        """Resolve contact from fmf metadata to Jira accountId."""
        if not test.contact:
            return None
        contact_str = test.contact[0]
        contact_id = email.utils.parseaddr(contact_str)[1] or contact_str.strip()
        if not contact_id:
            return None
        account_id = jira_instance.resolve_account_id(contact_id)
        if not account_id:
            test._logger.warning(f"Could not resolve Jira account for '{contact_id}'.")
        return account_id

    @staticmethod
    def _resolve_uuid(
        test: tmt.base.core.Test,
        jira_instance: JiraInstance,
        case_key: Optional[str],
        field_tmt_id: str,
    ) -> str:
        """Ensure UUID exists in fmf data and Jira, syncing or generating as needed."""
        uuid: Optional[str] = test.node.get(ID_KEY)
        if uuid:
            return uuid

        if case_key is not None:
            jira_issue = jira_instance.jira.issue(case_key)
            jira_uuid = getattr(jira_issue.fields, field_tmt_id, None)
            if not jira_uuid and hasattr(jira_issue, 'raw'):
                jira_uuid = jira_issue.raw.get('fields', {}).get(field_tmt_id)
            if jira_uuid:
                uuid = str(jira_uuid)
                if not test.is_dry_run:
                    with test.node as data:
                        data[ID_KEY] = uuid
                return uuid

        uuid = add_uuid_if_not_defined(test.node, test.is_dry_run, test._logger)
        assert uuid is not None
        return uuid

    @staticmethod
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
                    test._logger.info('verifies', f'{req_key} (already linked)', 'green')
                    continue
                try:
                    jira_instance.jira.create_issue_link(
                        type=LINK_TYPE_TESTS, inwardIssue=req_key, outwardIssue=case_key
                    )
                    test._logger.info('verifies', req_key, 'green')
                except jira_module.JIRAError as err:
                    test._logger.warning(f"Could not link to '{req_key}': {err}")
                continue

            # Bugzilla — create a remote link
            bz_match = RE_BUGZILLA_ID.search(target)
            if bz_match:
                bz_id = bz_match.group(1)
                if target in linked_remote_urls:
                    test._logger.info('verifies (BZ)', f'{bz_id} (already linked)', 'green')
                    continue
                try:
                    jira_instance.jira.add_remote_link(
                        case_key, destination={'url': target, 'title': f'BZ#{bz_id}'}
                    )
                    test._logger.info('verifies (BZ)', bz_id, 'green')
                except jira_module.JIRAError as err:
                    test._logger.warning(f"Could not add BZ remote link '{bz_id}': {err}")
                continue

            test._logger.warning(f"Skipping unrecognised verifies link: {target}")

    @staticmethod
    def _transition_case(
        test: tmt.base.core.Test, jira_instance: JiraInstance, key: str, enabled: bool
    ) -> None:
        """Transition a TestCase to Active or Retired, skipping if already there."""
        target = 'Active' if enabled else 'Retired'
        current_status = jira_instance.jira.issue(key, fields='status').fields.status.name
        if current_status == target:
            return
        jira_instance.transition_issue(key, target)
        test._logger.info('status', target, 'green')

    @staticmethod
    def _link_jira_to_fmf(test: tmt.base.core.Test, url: str, case_key: str) -> None:
        """Write Jira implements link back to fmf metadata."""
        with test.node as data:
            tmt.convert.add_link(
                f'{url}/browse/{case_key}',
                data,
                system=tmt.convert.SYSTEM_OTHER,
                type_='implements',
            )
        test._logger.info('implements', f'{url}/browse/{case_key}', 'green')

    @staticmethod
    def _log_metadata(
        test: tmt.base.core.Test,
        summary: str,
        uuid: str,
        labels: list[str],
        polarion_case_url: Optional[str],
    ) -> None:
        """Log exported test case metadata."""
        if polarion_case_url:
            test._logger.info('polarion', polarion_case_url, 'green')
        elif not test.is_dry_run:
            test._logger.info('polarion', 'not found', 'yellow')

        test._logger.info('summary', summary, 'green')
        test._logger.info('uuid', uuid, 'green')
        test._logger.info('labels', ' '.join(labels), 'green')
        test._logger.info('components', ' '.join(test.component), 'green')
        test._logger.info('enabled', str(test.enabled), 'green')

    @classmethod
    def _create_jira_instance(cls) -> JiraInstance:
        """Validate options and initialize JiraInstance."""
        required = ['jira_url', 'jira_token', 'jira_user', 'project_id']
        missing = [
            f"--{opt.replace('_', '-')}" for opt in required if not tmt.base.core.Test._opt(opt)
        ]
        if missing:
            raise ExportError(f"Missing required Jira options: {', '.join(missing)}.")

        return JiraInstance(
            url=str(tmt.base.core.Test._opt('jira_url')).rstrip('/'),
            email=tmt.base.core.Test._opt('jira_user'),
            token=tmt.base.core.Test._opt('jira_token'),
            logger=cls._logger,
        )

    @classmethod
    def _export_test_dry(
        cls,
        test: tmt.base.core.Test,
        summary: str,
        uuid: str,
        labels: list[str],
        case_key: Optional[str],
    ) -> None:
        """Handle dry-run reporting without modifying Jira or fmf data."""
        if case_key is None:
            test._logger.print(f"Test case '{summary}' would be created.", color='blue')
        else:
            test._logger.print(f"Test case '{case_key}' would be updated.", color='blue')

        cls._log_metadata(test, summary, uuid, labels, polarion_case_url=None)
        test._logger.print(
            f"Test case '{summary}' successfully exported to Jira.", color='magenta'
        )

    @classmethod
    def _export_test_live(
        cls,
        test: tmt.base.core.Test,
        jira_instance: JiraInstance,
        project_id: str,
        url: str,
        field_tmt_id: str,
        summary: str,
        uuid: str,
        labels: list[str],
        case_key: Optional[str],
    ) -> None:
        """Perform live Jira issue creation or update and update fmf metadata."""
        contact_account_id = cls._resolve_contact(test, jira_instance)
        script_url = cls._find_script_url(test)
        polarion_case_url = cls._find_polarion_case_url(test)

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
        fields = cls._build_fields(
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
            case_key = str(jira_instance.jira.create_issue(fields=fields).key)
            test._logger.print(f"Test case '{case_key}' created.", color='blue')
        else:
            jira_instance.jira.issue(case_key).update(fields=fields)
            test._logger.print(f"Test case '{case_key}' updated.", color='blue')

        cls._log_metadata(test, summary, uuid, labels, polarion_case_url)

        cls._transition_case(test, jira_instance, case_key, test.enabled)
        cls._create_issue_links(test, case_key, jira_instance, url)
        if test.opt('link_jira'):
            cls._link_jira_to_fmf(test, url, case_key)

        test._logger.print(
            f"Test case '{summary}' successfully exported to Jira.", color='magenta'
        )

    @classmethod
    def export_test(cls, test: tmt.base.core.Test, jira_instance: JiraInstance) -> None:
        """
        Export a single tmt test to a Jira TestCase.

        :param jira_instance: connection to reuse across tests.
        """
        url = jira_instance.url
        project_id = str(test.opt('project_id'))

        valid, error_msg = tmt.utils.git.validate_git_status(test)
        if not valid:
            if test.opt('ignore_git_validation'):
                test._logger.print(f"Exporting regardless: '{error_msg}'.", color='red')
            else:
                raise ExportError(
                    f"Can't export due to '{error_msg}'.\n"
                    "Use --ignore-git-validation to export regardless."
                )

        field_tmt_id = jira_instance.resolve_field_id('ID')
        summary = test.summary or test.name
        labels = list(test.tag)
        if test.tier is not None:
            labels.append(f'Tier{test.tier}')

        case_key = (
            None
            if test.opt('duplicate')
            else cls._find_case_key(test, jira_instance, project_id, url, field_tmt_id)
        )

        if case_key is None and not test.opt('create'):
            raise ExportError(
                f"Jira TestCase not found for '{test}'. Use --create to create a new test case."
            )

        uuid = cls._resolve_uuid(test, jira_instance, case_key, field_tmt_id)

        if test.is_dry_run:
            cls._export_test_dry(test, summary, uuid, labels, case_key)
            return

        cls._export_test_live(
            test=test,
            jira_instance=jira_instance,
            project_id=project_id,
            url=url,
            field_tmt_id=field_tmt_id,
            summary=summary,
            uuid=uuid,
            labels=labels,
            case_key=case_key,
        )

    @classmethod
    def export_test_collection(
        cls,
        tests: list[tmt.base.core.Test],
        keys: Optional[list[str]] = None,
        **kwargs: Any,
    ) -> str:
        """Export a collection of tests to Jira."""
        if not tests:
            return ''

        jira_instance = cls._create_jira_instance()
        for test in tests:
            cls.export_test(test, jira_instance=jira_instance)
        return ''
