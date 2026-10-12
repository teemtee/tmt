"""Export resolved local tmt tests to a configurable Jira Cloud schema."""

import email.utils
import re
import string
from copy import deepcopy
from typing import Any, Literal, Optional, cast

import tmt.base.core
import tmt.base.links
import tmt.config
import tmt.convert
import tmt.export
import tmt.log
import tmt.utils.git
from tmt.config.models.jira import JiraExportConfig
from tmt.config.models.link import IssueTrackerType
from tmt.container import container, simple_field
from tmt.identifier import ID_KEY, generate_uuid
from tmt.utils import ExportError, Path
from tmt.utils.jira import JiraInstance


@container
class JiraExportContext:
    """
    Context passed to both extension hooks for one resolved test.

    ``issue_key`` is populated before enrichment for updates, and after
    creation for new issues. It is None for a dry run of a new issue.
    ``fields`` maps configured field identifiers to resolved Jira IDs.
    Extensions must honor ``dry_run`` for all external and local writes.
    """

    jira: JiraInstance
    config: JiraExportConfig
    project: str
    issue_type_id: str
    uuid_field: str
    fields: dict[str, str]
    dry_run: bool
    issue_key: Optional[str] = None
    uuid: Optional[str] = None
    automation_url: Optional[str] = None


@container
class JiraIssueLinkOperation:
    """A validated, directed relationship to create during application."""

    type: str
    target: str
    direction: Literal['outward', 'inward']


@container
class JiraRemoteLinkOperation:
    """A remote link to add/update or an owned automation link to remove."""

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
    Export tests to Jira Cloud using local metadata and a configured schema.

    Supply authentication with ``--jira-url``, ``--jira-user`` and
    ``--jira-token``. Configure a project and a custom UUID field with
    ``--project-id`` and ``--jira-uuid-field`` or the ``/export/jira`` node
    in the tmt configuration tree. Issue type defaults to ``Task``;
    automation URLs use remote web links by default. Status transitions
    and fmf relationship mappings are opt-in.

    Repeated ``--jira-profile`` files layer over user defaults; explicit schema
    options take precedence. Credentials also accept ``TMT_JIRA_URL``,
    ``TMT_JIRA_USER`` and ``TMT_JIRA_TOKEN`` or existing user Jira connections.
    ``managed-fields`` controls ownership of ordinary Jira fields.
    Jira Summary defaults to the resolved fmf summary, falling back to the
    fmf name, and Jira Description uses the resolved fmf description.
    The ``title`` format customizes Summary independently of Description.

    Use ``--create`` to allow creation, ``--dry`` to preview the same
    payload without writes, and ``--link-jira`` to opt into metadata
    backlinks. Existing UUIDs are preserved and looked up independently
    of components. Subclasses can override :py:meth:`enrich_payload` and
    :py:meth:`post_export` without replacing discovery, identity or CRUD.
    The entire collection is prepared before any writes, and normal dry-run
    output displays its fields, clears, URLs, links and transition operations.

    This exporter uses Cloud REST v3 and ADF descriptions. Existing Jira
    linking utilities retain Server/Data Center support.
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
        """Encode text for Jira Cloud REST v3 rich-text fields."""
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
    def _configuration(cls) -> JiraExportConfig:
        """Layer user defaults, selected YAML profiles in order, and CLI overrides."""
        config = tmt.config.Config(cls._logger).jira_export or JiraExportConfig()
        data = config.model_dump(by_alias=True)
        for profile in tmt.base.core.Test._opt('jira_profile') or []:
            path = Path(profile)
            try:
                overlay = tmt.utils.yaml_to_dict(path.read_text())
            except (OSError, tmt.utils.GeneralError) as error:
                raise ExportError(f"Unable to read Jira profile '{path}': {error}.") from error
            # Mapping entries merge so a repository can change one select option
            # or link setting. An explicitly empty mapping clears inherited entries.
            cls._merge_profile(data, overlay)
        config = JiraExportConfig.from_yaml(tmt.utils.to_yaml(data))
        overrides = {
            'project_id': 'project',
            'jira_issue_type': 'issue_type',
            'jira_uuid_field': 'uuid_field',
            'jira_automation_url': 'automation_url',
            'jira_title': 'title',
            'jira_status': 'status',
        }
        for option, attribute in overrides.items():
            value = tmt.base.core.Test._opt(option)
            if value is not None:
                setattr(config, attribute, value)
        if config.automation_url == 'none':
            config.automation_url = None
        if config.status == 'none':
            config.status = None
        cls._validate_title_format(config.title)
        return config

    @classmethod
    def _merge_profile(cls, data: dict[str, Any], overlay: dict[str, Any]) -> None:
        """Merge bounded nested schema mappings while replacing scalar/list values."""
        for key, value in overlay.items():
            if isinstance(value, dict) and value and isinstance(data.get(key), dict):
                cls._merge_profile(data[key], value)
            else:
                data[key] = value

    @staticmethod
    def _validate_title_format(title: str) -> None:
        """Reject unsupported or malformed title formats before identity generation."""
        try:
            for _, field_name, spec, conversion in string.Formatter().parse(title):
                if field_name is not None and (
                    field_name not in ('name', 'summary') or spec or conversion
                ):
                    raise ValueError('Only {name} and {summary} placeholders are supported')
        except ValueError as error:
            raise ExportError(f"Invalid Jira title format '{title}': {error}.") from error

    @classmethod
    def _create_jira_instance(cls) -> JiraInstance:
        """Validate credentials and initialize a Cloud-only export client."""
        required = ['jira_url', 'jira_token', 'jira_user']
        values = {option: tmt.base.core.Test._opt(option) for option in required}
        if not all(values.values()):
            link_config = tmt.config.Config(cls._logger).link
            if link_config:
                trackers = [
                    tracker
                    for tracker in link_config.issue_tracker
                    if tracker.type == IssueTrackerType.jira
                    and (
                        not values['jira_url']
                        or str(tracker.url).rstrip('/') == str(values['jira_url']).rstrip('/')
                    )
                ]
                if len(trackers) > 1:
                    raise ExportError(
                        'Multiple Jira connections configured; '
                        'select one with --jira-url or TMT_JIRA_URL.'
                    )
                if trackers:
                    tracker = trackers[0]
                    values = {
                        'jira_url': values['jira_url'] or str(tracker.url),
                        'jira_user': values['jira_user'] or tracker.email,
                        'jira_token': values['jira_token'] or tracker.token,
                    }
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
    def _resolve_schema(jira: JiraInstance, config: JiraExportConfig) -> dict[str, str]:
        """Resolve configured fields and reject overlapping managed destinations."""
        if not config.project or not config.uuid_field:
            raise ExportError(
                'Configure a Jira project and UUID field in /export/jira or with '
                '--project-id and --jira-uuid-field.'
            )
        identifiers = [config.uuid_field, *config.fields]
        if config.automation_url is not None and config.automation_url != 'remote-link':
            identifiers.append(config.automation_url)
        resolved = {identifier: jira.resolve_field_id(identifier) for identifier in identifiers}
        if not re.fullmatch(r'customfield_\d+', resolved[config.uuid_field]):
            raise ExportError('The Jira UUID destination must be a custom field.')
        reserved = {
            'summary',
            'description',
            'components',
            'labels',
            'assignee',
            'project',
            'issuetype',
        }
        if reserved.intersection(resolved.values()) or len(set(resolved.values())) != len(
            identifiers
        ):
            raise ExportError('Configured Jira fields overlap managed destinations.')
        for relation, mapping in config.links.items():
            if relation not in tmt.base.links.Links._relations:
                raise ExportError(f"Unknown fmf link relation '{relation}'.")
            if not mapping.issue_type and not mapping.remote:
                raise ExportError(f"Link mapping '{relation}' has no destination.")
            if mapping.issue_type:
                jira.validate_link_type(mapping.issue_type)
        return resolved

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
                    f"Ignoring Jira backlink '{key}' outside configured project/type."
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
        """Build owned fields, including explicit clears for empty source metadata."""
        config = context.config
        title = config.title.format(name=test.name, summary=test.summary or test.name)
        if not title.strip():
            raise ExportError('Jira title must not be empty.')
        description = test.description
        ordinary_fields: dict[str, Any] = {
            'summary': title,
            'description': cls._text_to_adf(description) if description else None,
            'components': [{'name': component} for component in test.component],
            'labels': list(test.tag),
        }
        fields: dict[str, Any] = {context.uuid_field: context.uuid}
        fields.update(
            {key: value for key, value in ordinary_fields.items() if key in config.managed_fields}
        )
        if context.issue_key is None:
            # Jira requires a title on creation, even when Jira owns later edits.
            fields['summary'] = title
            fields.update(
                project={'key': context.project}, issuetype={'id': context.issue_type_id}
            )
        if 'assignee' in config.managed_fields:
            account_id = cls._resolve_contact(test, context.jira)
            if account_id:
                fields['assignee'] = {'accountId': account_id}
            elif not test.contact:
                fields['assignee'] = None
        # An unresolved nonempty contact leaves the assignee unchanged, with a warning.
        if config.automation_url is not None and config.automation_url != 'remote-link':
            fields[context.fields[config.automation_url]] = context.automation_url
        for destination, mapping in config.fields.items():
            value = getattr(test, mapping.source)
            if value is None or value == '':
                fields[context.fields[destination]] = None
                continue
            text = str(value)
            if mapping.values is not None:
                if text not in mapping.values:
                    raise ExportError(f"No configured value for '{mapping.source}={text}'.")
                text = mapping.values[text]
            fields[context.fields[destination]] = (
                {'value': text} if mapping.type == 'single-select' else text
            )
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
                    field.get('required')
                    and not field.get('hasDefaultValue')
                    and field_id not in plan.payload
                ):
                    raise ExportError(
                        f"Missing required Jira field '{field_id}' for '{plan.test.name}'."
                    )
        for destination, mapping in context.config.fields.items():
            field_id = context.fields[destination]
            if (
                field_id in plan.payload
                and mapping.type == 'single-select'
                and metadata[field_id].get('schema', {}).get('type') != 'option'
            ):
                raise ExportError(f"Jira field '{field_id}' is not a single-select field.")

    @staticmethod
    def _prepare_links(plan: JiraExportPlan) -> None:
        """Validate targets and enumerate all link additions, updates and removals."""
        test, context = plan.test, plan.context
        jira = context.jira.jira
        remote_urls: set[str] = set()
        remote_links = []
        if context.issue_key and (
            context.config.links or context.config.automation_url == 'remote-link'
        ):
            remote_links = jira.remote_links(context.issue_key)
            remote_urls = {str(link.object.url) for link in remote_links}
        if context.config.automation_url == 'remote-link':
            global_id = f'tmt:uuid:{context.uuid}'
            if context.automation_url:
                plan.remote_links.append(
                    JiraRemoteLinkOperation(
                        action='add', url=context.automation_url, global_id=global_id
                    )
                )
                remote_urls.add(context.automation_url)
            elif any(getattr(link, 'globalId', None) == global_id for link in remote_links):
                plan.remote_links.append(
                    JiraRemoteLinkOperation(action='remove', global_id=global_id)
                )
        if not context.config.links or not test.link:
            return
        existing: set[tuple[str, str, str]] = set()
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
        prefix = f'{context.jira.url}/browse/'
        for relation, mapping in context.config.links.items():
            for link in test.link.get(cast(tmt.base.links._RawLinkRelationName, relation)):
                if not isinstance(link.target, str):
                    continue
                target = link.target
                if target.startswith(prefix) and mapping.issue_type:
                    key = target[len(prefix) :]
                    identity = (mapping.issue_type, mapping.direction, key)
                    if identity in existing:
                        continue
                    if key == context.issue_key:
                        raise ExportError(f"Jira issue '{key}' cannot link to itself.")
                    jira.issue(key, fields='summary')
                    plan.issue_links.append(
                        JiraIssueLinkOperation(
                            type=mapping.issue_type, target=key, direction=mapping.direction
                        )
                    )
                    existing.add(identity)
                elif (
                    mapping.remote
                    and re.match(r'^https?://', target)
                    and target not in remote_urls
                ):
                    plan.remote_links.append(
                        JiraRemoteLinkOperation(action='add', url=target, title=relation)
                    )
                    remote_urls.add(target)

    @staticmethod
    def _prepare_transition(plan: JiraExportPlan) -> None:
        """Resolve existing transitions and validate the workflow status for new issues."""
        context = plan.context
        status = context.config.status
        if not status:
            return
        context.jira.validate_status(context.project, context.issue_type_id, status)
        if context.issue_key:
            current = context.jira.jira.issue(
                context.issue_key, fields='status'
            ).fields.status.name
            if current == status:
                return
            transition_id = context.jira.resolve_transition_id(context.issue_key, status)
        else:
            # Jira cannot expose transitions for an issue which does not exist yet.
            transition_id = None
        plan.transition = JiraTransitionOperation(status=status, id=transition_id)

    @classmethod
    def _prepare_payload(
        cls, test: tmt.base.core.Test, context: JiraExportContext
    ) -> JiraExportPlan:
        """Build and enrich one payload, then validate its fields and operations."""
        context.automation_url = test.web_link() if context.config.automation_url else None
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
        for link in plan.issue_links:
            source, destination = (
                (context.issue_key, link.target)
                if link.direction == 'outward'
                else (link.target, context.issue_key)
            )
            jira.create_issue_link(type=link.type, inwardIssue=source, outwardIssue=destination)
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

    @classmethod
    def prepare_test_collection(
        cls,
        tests: list[tmt.base.core.Test],
        *,
        jira_instance: Optional[JiraInstance] = None,
        config: Optional[JiraExportConfig] = None,
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
        config = config or cls._configuration()
        cls._validate_title_format(config.title)
        jira = jira_instance or cls._create_jira_instance()
        fields = cls._resolve_schema(jira, config)
        assert config.project
        assert config.uuid_field
        issue_type_id = jira.resolve_issue_type_id(config.project, config.issue_type)
        contexts: list[JiraExportContext] = []
        uuids: set[str] = set()
        issue_keys: set[str] = set()
        for test in tests:
            context = JiraExportContext(
                jira=jira,
                config=config,
                project=config.project,
                issue_type_id=issue_type_id,
                uuid_field=fields[config.uuid_field],
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
        return [cls._prepare_payload(test, context) for test, context in zip(tests, contexts)]

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
