"""Export resolved local tmt tests to Jira Cloud."""

import email.utils
import re
from copy import deepcopy
from typing import Any, Literal, Optional, cast

import tmt.base.core
import tmt.convert
import tmt.export
import tmt.log
import tmt.utils.git
from tmt.container import container, simple_field
from tmt.identifier import ID_KEY, generate_uuid
from tmt.utils import ExportError
from tmt.utils.jira import JiraInstance

# Issue link type for test case → requirement relationship
LINK_TYPE_TESTS = 'pair'  # outward="tests", inward="is tested by"

ISSUE_TYPE = 'Test Case'
UUID_FIELD = 'ID'
URL_FIELD = 'URL'
POLARION_FIELD = 'External issue URL'
TARGET_STATUS = 'Active'

RE_BUGZILLA_ID = re.compile(r'show_bug\.cgi\?(?:.*&)?id=(\d+)')

# Fields Jira populates by itself or from the request context, even when
# ``createmeta`` reports them as required without a default value.
SYSTEM_POPULATED_FIELDS = {'reporter', 'project', 'issuetype'}


@container
class JiraExportContext:
    """
    Context passed to both extension hooks for one resolved test.

    ``issue_key`` is populated before enrichment for updates, and after
    creation for new issues. It is None for a dry run of a new issue.
    ``fields`` maps known field identifiers to resolved Jira IDs.
    Extensions must honor ``dry_run`` for all external and local writes.
    """

    jira: JiraInstance
    project: str
    issue_type_id: str
    uuid_field: str
    fields: dict[str, str]
    dry_run: bool
    issue_key: Optional[str] = None
    uuid: Optional[str] = None
    automation_url: Optional[str] = None
    polarion_case_url: Optional[str] = None


@container
class JiraIssueLinkOperation:
    """A validated, directed relationship to create during application."""

    type: str
    target: str
    direction: Literal['outward', 'inward']


@container
class JiraRemoteLinkOperation:
    """A remote link to create during application."""

    action: Literal['add', 'remove']
    url: Optional[str] = None
    title: str = 'tmt automation'
    global_id: Optional[str] = None


@container
class JiraTransitionOperation:
    """A validated target status and, for existing issues, its transition ID."""

    status: str
    id: Optional[str] = None


@container
class JiraExportPlan:
    """Prepared fields and operations for one resolved test, without source writes."""

    test: tmt.base.core.Test
    context: JiraExportContext
    payload: dict[str, Any]
    action: Literal['create', 'update']
    persist_uuid: bool
    backlink: bool
    issue_links: list[JiraIssueLinkOperation] = simple_field(default_factory=list)
    remote_links: list[JiraRemoteLinkOperation] = simple_field(default_factory=list)
    transition: Optional[JiraTransitionOperation] = None

    def to_dict(self) -> dict[str, Any]:
        """Return a credential-free representation suitable for YAML/JSON inspection."""
        return {
            'test': self.test.name,
            'action': self.action,
            'issue': self.context.issue_key,
            'uuid': self.context.uuid,
            'destinations': dict(self.context.fields),
            'fields': deepcopy(self.payload),
            'issue-links': [
                {'type': link.type, 'target': link.target, 'direction': link.direction}
                for link in self.issue_links
            ],
            'remote-links': [
                {
                    'action': link.action,
                    'url': link.url,
                    'title': link.title,
                    'global-id': link.global_id,
                }
                for link in self.remote_links
            ],
            'transition': {
                'status': self.transition.status,
                'id': self.transition.id,
                'resolve-after-create': self.transition.id is None,
            }
            if self.transition
            else None,
            'metadata': {'persist-uuid': self.persist_uuid, 'backlink': self.backlink},
        }


@tmt.base.core.Test.provides_export('jira')
class JiraExporter(tmt.export.ExportPlugin):
    """
    Export test metadata to Jira as ``Test Case`` work items.

    The ``--jira-url``, ``--jira-user``, ``--jira-token`` and
    ``--project-id`` options are required.

    Existing ``Test Case`` issues are located first by the tmt UUID stored
    in the ``ID`` custom field, then by an ``implements`` link in the fmf
    metadata pointing to the configured Jira instance. Use ``--create`` to
    create a new ``Test Case`` when none is found, and ``--link-jira`` to
    write the Jira issue URL back into the fmf metadata as an ``implements``
    link for future lookups.

    Use ``--bugzilla`` to recreate Bugzilla ``verifies`` links as remote
    links on the Jira ``Test Case``. Use ``--polarion`` to populate the
    ``External issue URL`` custom field with the test's Polarion test case
    link.

    The whole selected collection is validated and prepared before any
    UUID is persisted or any Jira issue is written. Dry-run output displays
    the prepared plan. Subclasses can override :py:meth:`enrich_payload` and
    :py:meth:`post_export` without replacing discovery, identity or CRUD.

    .. code-block:: shell

        tmt tests export --how jira --create --link-jira \\
            --jira-url https://issues.redhat.com \\
            --jira-user me@example.com --jira-token TOKEN \\
            --project-id RHELTEST
    """

    _logger: tmt.log.Logger = tmt.log.Logger.get_bootstrap_logger()

    @classmethod
    def enrich_payload(
        cls, test: tmt.base.core.Test, context: JiraExportContext, fields: dict[str, Any]
    ) -> None:
        """
        Enrich a create/update payload in place, also called during dry runs.

        This is a preparation hook: do not perform local or external writes,
        even for live exports. Identity and create routing fields must remain
        intact. Use the resolved test and context for enrichment or validation.
        """

    @classmethod
    def post_export(cls, test: tmt.base.core.Test, context: JiraExportContext) -> None:
        """
        Perform optional actions after CRUD, links, transitions and backlinks.

        Called for dry runs too; a new issue has no key in that case. Hooks
        doing writes must check ``context.dry_run``. Exceptions propagate;
        completed Jira writes cannot be rolled back by the exporter.
        """

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
        return {
            'type': 'doc',
            'version': 1,
            'content': [
                {'type': 'paragraph', 'content': [{'type': 'text', 'text': line}]}
                for line in text.splitlines()
                if line.strip()
            ]
            or [{'type': 'paragraph', 'content': []}],
        }

    @classmethod
    def _create_jira_instance(cls) -> JiraInstance:
        """Validate credentials and initialize a Cloud-only export client."""
        required = ['jira_url', 'jira_token', 'jira_user', 'project_id']
        values = {option: tmt.base.core.Test._opt(option) for option in required}
        missing = [f"--{option.replace('_', '-')}" for option in required if not values[option]]
        if missing:
            raise ExportError(f"Missing required Jira options: {', '.join(missing)}.")
        return JiraInstance(
            url=str(values['jira_url']).rstrip('/'),
            email=values['jira_user'],
            token=values['jira_token'],
            logger=cls._logger,
            cloud=True,
        )

    @staticmethod
    def _resolve_schema(jira: JiraInstance) -> tuple[str, dict[str, str]]:
        """Resolve known custom field IDs and reject overlapping destinations."""
        uuid_field = jira.resolve_field_id(UUID_FIELD)
        if not re.fullmatch(r'customfield_\d+', uuid_field):
            raise ExportError('The Jira UUID destination must be a custom field.')

        fields = {'url': jira.resolve_field_id(URL_FIELD)}
        if tmt.base.core.Test._opt('polarion'):
            fields['polarion'] = jira.resolve_field_id(POLARION_FIELD)

        reserved = {
            'summary',
            'description',
            'components',
            'labels',
            'assignee',
            'project',
            'issuetype',
        }
        resolved = [uuid_field, *fields.values()]
        if reserved.intersection(resolved) or len(set(resolved)) != len(resolved):
            raise ExportError('Resolved Jira fields overlap managed destinations.')

        return uuid_field, fields

    @staticmethod
    def _validate_test(test: tmt.base.core.Test) -> None:
        """Validate source metadata before any exporter-owned writes."""
        valid, message = tmt.utils.git.validate_git_status(test)
        if valid:
            return
        if test.opt('ignore_git_validation'):
            test._logger.warning(f"Exporting regardless: '{message}'.")
            return
        raise ExportError(
            f"Can't export due to '{message}'.\nUse --ignore-git-validation to export regardless."
        )

    @staticmethod
    def _find_case_key(test: tmt.base.core.Test, context: JiraExportContext) -> Optional[str]:
        """Lookup UUID independently of components, then check local backlinks."""
        import jira as jira_module

        candidates: set[str] = set()
        uuid = test.node.get(ID_KEY)
        if uuid:
            key = context.jira.find_issue_by_uuid(
                str(uuid),
                project_id=context.project,
                issue_type=context.issue_type_id,
                uuid_field=context.uuid_field,
            )
            if key:
                candidates.add(key)

        prefix = f'{context.jira.url}/browse/'
        for link in test.link.get('implements') if test.link else []:
            if not isinstance(link.target, str) or not link.target.startswith(prefix):
                continue
            key = link.target[len(prefix) :]
            try:
                issue = context.jira.jira.issue(
                    key, fields=f'project,issuetype,{context.uuid_field}'
                )
            except jira_module.JIRAError as error:
                if error.status_code != 404:
                    raise
                test._logger.warning(f"Jira issue '{key}' from implements link not found in Jira.")
                continue
            if (
                str(issue.fields.issuetype.id) != context.issue_type_id
                or str(issue.fields.project.key) != context.project
            ):
                test._logger.warning(
                    f"Ignoring Jira backlink '{key}' outside the configured project or issue type."
                )
                continue
            jira_uuid = getattr(issue.fields, context.uuid_field, None)
            if uuid and jira_uuid and str(uuid) != str(jira_uuid):
                raise ExportError(
                    f"Jira backlink '{key}' has a different UUID from '{test.name}'."
                )
            candidates.add(key)

        if len(candidates) > 1:
            raise ExportError(f"Ambiguous Jira identity for '{test.name}': {sorted(candidates)}.")
        if not candidates:
            return None
        key = candidates.pop()
        test._logger.print(f"Found Jira issue: '{key}'.", color='blue')
        return key

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
    def _resolve_uuid(test: tmt.base.core.Test, context: JiraExportContext) -> str:
        """Resolve or generate identity in memory, leaving metadata untouched."""
        uuid = cast(Optional[str], test.node.get(ID_KEY))
        if uuid:
            return uuid
        if context.issue_key:
            issue = context.jira.jira.issue(context.issue_key, fields=context.uuid_field)
            jira_uuid = getattr(issue.fields, context.uuid_field, None)
            if jira_uuid:
                return str(jira_uuid)
        return generate_uuid()

    @staticmethod
    def _resolve_contact(test: tmt.base.core.Test, jira: JiraInstance) -> Optional[str]:
        """Preserve display names and parse only actual email address forms."""
        if not test.contact:
            return None
        contact = test.contact[0].strip()
        if '@' in contact:
            contact = email.utils.parseaddr(contact)[1] or contact
        account_id = jira.resolve_account_id(contact) if contact else None
        if contact and not account_id:
            test._logger.warning(f"Could not resolve Jira account for '{contact}'.")
        return account_id

    @classmethod
    def _build_fields(cls, test: tmt.base.core.Test, context: JiraExportContext) -> dict[str, Any]:
        """Assemble Jira field dict for create or update."""
        title = test.summary or test.name
        if not title.strip():
            raise ExportError('Jira title must not be empty.')

        fields: dict[str, Any] = {
            'summary': title,
            'description': cls._text_to_adf(test.description) if test.description else None,
            context.uuid_field: context.uuid,
        }
        if context.issue_key is None:
            fields.update(
                project={'key': context.project}, issuetype={'id': context.issue_type_id}
            )
        if test.component:
            fields['components'] = [{'name': component} for component in test.component]
        labels = list(test.tag)
        if test.tier is not None:
            labels.append(f'Tier{test.tier}')
        if labels:
            fields['labels'] = labels

        account_id = cls._resolve_contact(test, context.jira)
        if account_id:
            fields['assignee'] = {'accountId': account_id}

        if context.automation_url:
            fields[context.fields['url']] = context.automation_url
        if context.polarion_case_url and 'polarion' in context.fields:
            fields[context.fields['polarion']] = context.polarion_case_url

        return fields

    @staticmethod
    def _choice_tokens(choice: Any, field_id: str) -> set[tuple[str, str]]:
        """Normalize scalar choices and object IDs/names without conflating IDs and values."""
        scalar_types = (str, int, float, bool)
        if isinstance(choice, dict):
            tokens: set[tuple[str, str]] = set()
            for key in ('id', 'value', 'name'):
                value = choice.get(key)
                if value is None:
                    continue
                if not isinstance(value, scalar_types):
                    break
                tokens.add(('id' if key == 'id' else 'value', str(value)))
            else:
                if tokens:
                    return tokens
        elif isinstance(choice, scalar_types):
            return {('value', str(choice))}
        raise ExportError(
            f"Unsupported choice for Jira field '{field_id}': expected a scalar or "
            'an object with scalar id/value/name attributes.'
        )

    @staticmethod
    def _validate_payload(plan: JiraExportPlan) -> None:
        """Check field availability, required values and exposed Jira select options."""
        context = plan.context
        metadata = context.jira.field_metadata(
            context.project, context.issue_type_id, context.issue_key
        )
        for field_id, value in plan.payload.items():
            if field_id in ('project', 'issuetype'):
                continue
            if field_id not in metadata:
                raise ExportError(
                    f"Jira field '{field_id}' is not available for '{plan.test.name}'."
                )
            field = metadata[field_id]
            if field.get('required') and value in (None, '', []):
                raise ExportError(f"Required Jira field '{field_id}' cannot be cleared.")
            if 'allowedValues' not in field or value in (None, []):
                continue
            options = field['allowedValues']
            if not isinstance(options, list):
                raise ExportError(
                    f"Unsupported allowedValues for Jira field '{field_id}': expected a list."
                )
            allowed: list[set[tuple[str, str]]] = []
            allowed_tokens: set[tuple[str, str]] = set()
            for option in options:
                if isinstance(option, dict) and option.get('disabled'):
                    continue
                tokens = JiraExporter._choice_tokens(option, field_id)
                allowed.append(tokens)
                allowed_tokens.update(tokens)
            for item in value if isinstance(value, list) else [value]:
                if isinstance(item, dict) and not {'id', 'value', 'name'}.intersection(item):
                    continue
                tokens = JiraExporter._choice_tokens(item, field_id)
                valid = (
                    tokens.issubset(allowed_tokens)
                    if len(tokens) == 1
                    else any(tokens.issubset(option) for option in allowed)
                )
                if not valid:
                    raise ExportError(
                        f"Value '{item}' is not allowed for Jira field '{field_id}'."
                    )
        if context.issue_key is None:
            for field_id, field in metadata.items():
                if (
                    field_id in SYSTEM_POPULATED_FIELDS
                    or field.get('key') in SYSTEM_POPULATED_FIELDS
                ):
                    continue
                if (
                    field.get('required')
                    and not field.get('hasDefaultValue')
                    and field_id not in plan.payload
                ):
                    raise ExportError(
                        f"Missing required Jira field '{field_id}' for '{plan.test.name}'."
                    )

    @staticmethod
    def _prepare_links(plan: JiraExportPlan) -> None:
        """Validate targets and enumerate link additions during preparation."""
        test, context = plan.test, plan.context
        if not test.link:
            return

        verifies_targets = [
            str(link.target)
            for link in test.link.get('verifies')
            if not isinstance(link.target, tmt.base.core.FmfId)
        ]
        if not verifies_targets:
            return

        jira = context.jira.jira
        existing: set[tuple[str, str, str]] = set()
        remote_urls: set[str] = set()
        if context.issue_key:
            links = jira.issue(context.issue_key, fields='issuelinks').fields.issuelinks
            for link in links:
                for direction, endpoint in [
                    ('outward', 'outwardIssue'),
                    ('inward', 'inwardIssue'),
                ]:
                    target = getattr(link, endpoint, None)
                    if target:
                        existing.add((str(link.type.name), direction, str(target.key)))
            remote_urls = {
                str(remote_link.object.url) for remote_link in jira.remote_links(context.issue_key)
            }

        prefix = f'{context.jira.url}/browse/'
        for target in verifies_targets:
            if target.startswith(prefix):
                key = target[len(prefix) :]
                identity = (LINK_TYPE_TESTS, 'outward', key)
                if identity in existing:
                    test._logger.info('verifies', f'{key} (already linked)', color='green')
                    continue
                if key == context.issue_key:
                    raise ExportError(f"Jira issue '{key}' cannot link to itself.")
                jira.issue(key, fields='summary')
                plan.issue_links.append(
                    JiraIssueLinkOperation(type=LINK_TYPE_TESTS, target=key, direction='outward')
                )
                existing.add(identity)
                continue

            bz_match = RE_BUGZILLA_ID.search(target)
            if bz_match:
                if not test.opt('bugzilla'):
                    continue
                bz_id = bz_match.group(1)
                if target in remote_urls:
                    test._logger.info('verifies (BZ)', f'{bz_id} (already linked)', color='green')
                    continue
                plan.remote_links.append(
                    JiraRemoteLinkOperation(action='add', url=target, title=f'BZ#{bz_id}')
                )
                remote_urls.add(target)
                continue

            test._logger.warning(f"Skipping unrecognised verifies link: {target}")

    @staticmethod
    def _prepare_transition(plan: JiraExportPlan) -> None:
        """Resolve existing transitions and validate the workflow status for new issues."""
        context = plan.context
        context.jira.validate_status(context.project, context.issue_type_id, TARGET_STATUS)
        if context.issue_key:
            current = context.jira.jira.issue(
                context.issue_key, fields='status'
            ).fields.status.name
            if current == TARGET_STATUS:
                return
            transition_id = context.jira.resolve_transition_id(context.issue_key, TARGET_STATUS)
        else:
            # Jira cannot expose transitions for an issue which does not exist yet.
            transition_id = None
        plan.transition = JiraTransitionOperation(status=TARGET_STATUS, id=transition_id)

    @classmethod
    def _prepare_payload(
        cls, test: tmt.base.core.Test, context: JiraExportContext
    ) -> JiraExportPlan:
        """Build and enrich one payload, then validate its fields and operations."""
        context.automation_url = test.web_link()
        if test.opt('polarion'):
            context.polarion_case_url = cls._find_polarion_case_url(test)
        fields = cls._build_fields(test, context)
        identity = deepcopy(
            {
                key: fields[key]
                for key in (context.uuid_field, 'project', 'issuetype')
                if key in fields
            }
        )
        context_identity = (
            context.uuid,
            context.issue_key,
            context.uuid_field,
            context.project,
            context.issue_type_id,
        )
        cls.enrich_payload(test, context, fields)
        if any(
            fields.get(key) != value for key, value in identity.items()
        ) or context_identity != (
            context.uuid,
            context.issue_key,
            context.uuid_field,
            context.project,
            context.issue_type_id,
        ):
            raise ExportError('Jira payload enrichment must preserve identity and create routing.')
        plan = JiraExportPlan(
            test=test,
            context=context,
            payload=fields,
            action='update' if context.issue_key else 'create',
            persist_uuid=test.node.get(ID_KEY) != context.uuid,
            backlink=bool(test.opt('link_jira')),
        )
        cls._validate_payload(plan)
        cls._prepare_links(plan)
        cls._prepare_transition(plan)
        return plan

    @staticmethod
    def _log_metadata(
        test: tmt.base.core.Test,
        summary: str,
        uuid: str,
        labels: list[str],
        polarion_case_url: Optional[str] = None,
    ) -> None:
        """Log exported test case metadata."""
        if polarion_case_url:
            test._logger.info('polarion', polarion_case_url, color='green')
        test._logger.info('summary', summary, color='green')
        test._logger.info('uuid', uuid, color='green')
        test._logger.info('labels', ' '.join(labels), color='green')
        test._logger.info('components', ' '.join(test.component), color='green')
        test._logger.info('enabled', str(test.enabled), color='green')

    @classmethod
    def _apply_plan(cls, plan: JiraExportPlan) -> None:
        """Apply a fully prepared test's Jira and local metadata operations."""
        test, context = plan.test, plan.context
        jira = context.jira.jira
        if plan.persist_uuid:
            with test.node as data:  # type: ignore[reportUnknownVariableType,unused-ignore]
                cast(dict[str, Any], data)[ID_KEY] = context.uuid
        if context.issue_key is None:
            context.issue_key = str(jira.create_issue(fields=plan.payload).key)
            test._logger.print(f"Test case '{context.issue_key}' created.", color='blue')
        else:
            jira.issue(context.issue_key).update(fields=plan.payload)
            test._logger.print(f"Test case '{context.issue_key}' updated.", color='blue')

        labels = list(test.tag)
        if test.tier is not None:
            labels.append(f'Tier{test.tier}')
        cls._log_metadata(
            test,
            test.summary or test.name,
            context.uuid or '',
            labels,
            context.polarion_case_url,
        )

        if plan.transition:
            transition_id = plan.transition.id
            if transition_id is None:
                current = jira.issue(context.issue_key, fields='status').fields.status.name
                if current != plan.transition.status:
                    transition_id = context.jira.resolve_transition_id(
                        context.issue_key, plan.transition.status
                    )
            if transition_id:
                jira.transition_issue(context.issue_key, transition_id)
                test._logger.info('status', plan.transition.status, color='green')

        for link in plan.issue_links:
            source, destination = (
                (context.issue_key, link.target)
                if link.direction == 'outward'
                else (link.target, context.issue_key)
            )
            jira.create_issue_link(type=link.type, inwardIssue=source, outwardIssue=destination)
            test._logger.info('verifies', link.target, color='green')

        for remote in plan.remote_links:
            if remote.action == 'remove':
                jira.delete_remote_link(context.issue_key, global_id=remote.global_id)
            else:
                assert remote.url is not None
                jira.add_remote_link(
                    context.issue_key,
                    destination={'url': remote.url, 'title': remote.title},
                    globalId=remote.global_id,
                )

        if plan.backlink:
            with test.node as data:  # type: ignore[reportUnknownVariableType,unused-ignore]
                tmt.convert.add_link(
                    f'{context.jira.url}/browse/{context.issue_key}',
                    cast(dict[str, Any], data),
                    system=tmt.convert.SYSTEM_OTHER,
                    type_='implements',
                )

        test._logger.print(
            f"Test case '{test.summary or test.name}' successfully exported to Jira.",
            color='magenta',
        )

    @classmethod
    def prepare_test_collection(
        cls,
        tests: list[tmt.base.core.Test],
        *,
        jira_instance: Optional[JiraInstance] = None,
    ) -> list[JiraExportPlan]:
        """
        Prepare a whole collection without Jira or metadata writes.

        Resolve identities before payload enrichment and reject duplicate UUIDs
        and target issue keys, including identities restored from backlinks.
        Enrichment hooks must be side-effect free during this phase. Plans can
        be inspected through ``to_dict()`` before :py:meth:`apply_test_collection`.
        """
        if not tests:
            return []
        for test in tests:
            cls._validate_test(test)
            if test.opt('duplicate'):
                raise ExportError(
                    'Jira export requires unique UUIDs; --duplicate is not supported.'
                )
        jira = jira_instance or cls._create_jira_instance()
        project = str(tmt.base.core.Test._opt('project_id'))
        uuid_field, fields = cls._resolve_schema(jira)
        issue_type_id = jira.resolve_issue_type_id(project, ISSUE_TYPE)
        contexts: list[JiraExportContext] = []
        uuids: set[str] = set()
        issue_keys: set[str] = set()
        for test in tests:
            context = JiraExportContext(
                jira=jira,
                project=project,
                issue_type_id=issue_type_id,
                uuid_field=uuid_field,
                fields=fields,
                dry_run=test.is_dry_run,
            )
            context.issue_key = cls._find_case_key(test, context)
            if context.issue_key is None and not test.opt('create'):
                raise ExportError(
                    f"Jira issue not found for '{test.name}'. "
                    "Use --create to create a new test case."
                )
            context.uuid = cls._resolve_uuid(test, context)
            if context.uuid in uuids:
                raise ExportError(f"Multiple selected tests share UUID '{context.uuid}'.")
            if context.issue_key and context.issue_key in issue_keys:
                raise ExportError(
                    f"Multiple selected tests target Jira issue '{context.issue_key}'."
                )
            uuids.add(context.uuid)
            if context.issue_key:
                issue_keys.add(context.issue_key)
            contexts.append(context)
        return [
            cls._prepare_payload(test, context)
            for test, context in zip(tests, contexts, strict=True)
        ]

    @classmethod
    def apply_test_collection(cls, plans: list[JiraExportPlan]) -> None:
        """Apply validated plans, or display them in ordinary dry-run output."""
        completed: list[str] = []
        for plan in plans:
            test, context = plan.test, plan.context
            if context.dry_run:
                action = 'updated' if context.issue_key else 'created'
                test._logger.print(
                    f"Test case '{context.issue_key or test.name}' would be {action}."
                )
                test._logger.print(tmt.utils.to_yaml(plan.to_dict()))
                cls.post_export(test, context)
                continue
            try:
                cls._apply_plan(plan)
                cls.post_export(test, context)
            except Exception as error:
                raise ExportError(
                    f"Jira export failed for '{test.name}': {error}. "
                    f"Completed tests: {completed}. Current test may have partial writes."
                ) from error
            completed.append(test.name)
            test._logger.debug('Jira export plan', plan.to_dict())

    @classmethod
    def export_test(cls, test: tmt.base.core.Test, jira_instance: JiraInstance) -> None:
        """Prepare and apply one test with the same validation and hooks as a collection."""
        cls.apply_test_collection(cls.prepare_test_collection([test], jira_instance=jira_instance))

    @classmethod
    def export_test_collection(
        cls, tests: list[tmt.base.core.Test], keys: Optional[list[str]] = None, **kwargs: Any
    ) -> str:
        """Prepare the entire selected collection before beginning any writes."""
        cls.apply_test_collection(cls.prepare_test_collection(tests))
        return ''
