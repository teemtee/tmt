import json
import re
import urllib.parse
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, Optional, Union, cast

import fmf.utils

import tmt.base.core
import tmt.config
import tmt.log
import tmt.utils
import tmt.utils.hints
from tmt.config.models.link import IssueTracker, IssueTrackerType
from tmt.plugins import ModuleImporter

if TYPE_CHECKING:
    import jira

    import tmt.base.links
    import tmt.base.plan

# Test, plan or story
TmtObject = Union['tmt.base.core.Test', 'tmt.base.plan.Plan', 'tmt.base.core.Story']


import_jira: ModuleImporter['jira'] = ModuleImporter(  # type: ignore[valid-type]
    'jira', tmt.utils.ReportError, 'jira'
)


tmt.utils.hints.register_hint(
    'jira',
    """
    For linking tests, plans and stories to Jira, ``jira`` package is required by tmt.

    To quickly test ``jira`` presence, you can try running ``python -c 'import jira'``.

    * Users who installed tmt from system repositories should install ``tmt+link-jira`` package.
    * Users who installed tmt from PyPI should install ``tmt[link-jira]`` extra.
    """,
)


def prepare_url_params(tmt_object: 'tmt.base.core.Core') -> dict[str, str]:
    """
    Prepare url parameters prefixed with tmt object type

    This is the format in which the tmt web API accepts the
    specification of the objects to be displayed to the user.
    """

    tmt_type = tmt_object.__class__.__name__.lower()
    fmf_id = tmt_object.fmf_id

    url_params: dict[str, Any] = {
        f'{tmt_type}-url': fmf_id.url,
        f'{tmt_type}-name': fmf_id.name,
    }

    if fmf_id.path:
        url_params[f'{tmt_type}-path'] = fmf_id.path
    if fmf_id.ref:
        url_params[f'{tmt_type}-ref'] = fmf_id.ref

    return url_params


class JiraInstance:
    """
    A Jira instance configured with url and token
    """

    def __init__(
        self,
        *,
        url: str,
        email: str,
        token: str,
        logger: tmt.log.Logger,
        tmt_web_url: Optional[str] = None,
        cloud: bool = False,
    ) -> None:
        """
        Initialize a Jira instance from raw connection details.

        ``tmt_web_url`` is only needed by :py:meth:`add_link_to_issue`;
        callers that only export/report test data can leave it unset.
        Use :py:meth:`from_issue_tracker` to construct one from a
        configured issue tracker instead.

        ``cloud`` opts into REST v3 and Cloud routing for exporters using
        ADF. Other consumers retain SDK deployment detection and defaults.
        """

        self.url = url
        self.tmt_web_url = tmt_web_url
        self.email = email
        self.token = token

        self.logger = logger
        jira_module = import_jira(logger)

        client_options: dict[str, Any] = {}
        if cloud:
            client_options = {'get_server_info': False, 'options': {'rest_api_version': '3'}}

        self.jira = jira_module.JIRA(  # type: ignore[attr-defined]
            server=self.url,
            basic_auth=(self.email, self.token),
            **client_options,
        )
        if cloud:
            self.jira.deploymentType = 'Cloud'

        # Caches for schema resolution (issue type IDs and custom field IDs).
        # Populated on first lookup to minimize network requests.
        self._issue_types: dict[str, list[tuple[str, str]]] = {}
        self._fields_by_name: Optional[dict[str, list[str]]] = None
        self._field_ids: set[str] = set()
        self._accounts: dict[str, Optional[str]] = {}
        self._issue_statuses: dict[tuple[str, str], set[str]] = {}
        self._link_types: Optional[list[str]] = None
        self._create_fields: dict[tuple[str, str], dict[str, Any]] = {}

    @classmethod
    def from_issue_tracker(
        cls,
        issue_tracker: IssueTracker,
        logger: tmt.log.Logger,
    ) -> 'JiraInstance':
        """
        Initialize Jira instance from the issue tracker config
        """

        return cls(
            url=str(issue_tracker.url),
            email=issue_tracker.email,
            token=issue_tracker.token,
            tmt_web_url=str(issue_tracker.tmt_web_url),
            logger=logger,
        )

    @classmethod
    def from_issue_url(
        cls,
        issue_url: str,
        logger: tmt.log.Logger,
    ) -> Optional['JiraInstance']:
        """
        Search configured issues trackers for matching Jira instance
        """

        # Check for the 'link' config section, exit if config missing
        try:
            link_config = tmt.config.Config(logger).link
        except tmt.utils.SpecificationError:
            raise
        if not link_config:
            return None

        # Find Jira instance matching the issue url
        for issue_tracker in link_config.issue_tracker:
            # Tracker type must match
            if issue_tracker.type != IssueTrackerType.jira:
                continue

            # Issue url must match
            if issue_url.startswith(str(issue_tracker.url)):
                return JiraInstance.from_issue_tracker(issue_tracker, logger=logger)

        return None

    def add_link_to_issue(
        self,
        link: 'tmt.base.links.Link',
        tmt_objects: Sequence[TmtObject],
    ) -> None:
        """
        Link one or more tmt objects to the given Jira issue
        """

        # Prepare a nice title for the link
        title = (
            "tmt: "
            + fmf.utils.listed([tmt_object.name for tmt_object in tmt_objects])
            + f" ({link.relation})"
        )

        # Prepare the tmt web service link from all tmt objects
        assert self.tmt_web_url is not None
        web_link_parameters: dict[str, str] = {}
        for tmt_object in tmt_objects:
            web_link_parameters.update(prepare_url_params(tmt_object))
        web_link = urllib.parse.urljoin(
            self.tmt_web_url, "?" + urllib.parse.urlencode(web_link_parameters)
        )

        # Add link to the issue
        assert isinstance(link.target, str)
        issue_id = link.target.split('/')[-1]
        self.jira.add_simple_link(issue_id, {"url": web_link, "title": title})
        self.logger.print(f"Add link '{title}' to Jira issue '{link.target}'.")

    #
    # Connection utilities for the export and report plugins. Plain
    # passthroughs to ``self.jira`` (create_issue, add_comment, ...) don't
    # get a wrapper here; callers use the ``jira`` SDK client directly.
    #

    @staticmethod
    def field_jql_id(field_id: str) -> str:
        """Extract the numeric part of a ``customfield_XXXXX`` ID for JQL's ``cf[XXXXX]``."""
        return field_id.rsplit('_', 1)[-1]

    def resolve_issue_type_id(self, project_id: str, name: str) -> str:
        """
        Resolve an issue type ID or name within a project.

        Issue type IDs are project-specific, so this cannot be a fixed
        constant shared across Jira instances or projects.
        """
        if project_id not in self._issue_types:
            self._issue_types[project_id] = []
            # This SDK method calls project/{key}/statuses, not createmeta.
            # Returned issue types include their available workflow statuses.
            for issue_type in self.jira.issue_types_for_project(project_id):
                type_id = str(issue_type.id)
                self._issue_types[project_id].append((type_id, str(issue_type.name)))
                self._issue_statuses[(project_id, type_id)] = {
                    str(status.name) for status in getattr(issue_type, 'statuses', [])
                }

        issue_types = self._issue_types[project_id]
        if any(type_id == name for type_id, _ in issue_types):
            return name
        matches = [type_id for type_id, type_name in issue_types if type_name == name]
        if not matches:
            raise tmt.utils.ExportError(f"No '{name}' issue type found in project '{project_id}'.")
        if len(matches) > 1:
            raise tmt.utils.ExportError(
                f"Multiple issue types named '{name}' in project '{project_id}': {matches}. "
                "Configure an issue type ID."
            )
        return matches[0]

    def validate_status(self, project_id: str, issue_type: str, status: str) -> None:
        """Check that a target status belongs to the project's issue type workflow."""
        type_id = self.resolve_issue_type_id(project_id, issue_type)
        if status not in self._issue_statuses[(project_id, type_id)]:
            raise tmt.utils.ExportError(
                f"Status '{status}' is not available for issue type '{type_id}' "
                f"in project '{project_id}'."
            )

    def validate_link_type(self, name: str) -> None:
        """Validate a configured relationship type name, caching the visible schema."""
        if self._link_types is None:
            self._link_types = [str(link_type.name) for link_type in self.jira.issue_link_types()]
        if self._link_types.count(name) != 1:
            raise tmt.utils.ExportError(f"Expected one Jira relationship type named '{name}'.")

    def field_metadata(
        self, project_id: str, issue_type_id: str, issue_key: Optional[str] = None
    ) -> dict[str, Any]:
        """Return editable or project/type create fields with required flags and options."""
        if issue_key:
            return cast(dict[str, Any], self.jira.editmeta(issue_key)['fields'])
        cache_key = (project_id, issue_type_id)
        if cache_key not in self._create_fields:
            raw_fields: list[dict[str, Any]]
            if self.jira.deploymentType == 'Cloud':
                # The SDK's public project_issue_fields wrapper rejects Cloud
                # and expects the Server/DC response shape. Use its authenticated
                # transport with the supported Cloud endpoint, not legacy createmeta.
                path = (
                    f'issue/createmeta/{urllib.parse.quote(project_id, safe="")}/issuetypes/'
                    f'{urllib.parse.quote(issue_type_id, safe="")}'
                )
                raw_fields = []
                while True:
                    page = self.jira._get_json(
                        path, params={'startAt': len(raw_fields), 'maxResults': 50}
                    )
                    values = page['fields']
                    raw_fields.extend(values)
                    if len(raw_fields) >= page['total']:
                        break
                    if not values:
                        raise tmt.utils.ExportError(
                            'Jira create field metadata pagination stalled.'
                        )
            elif hasattr(self.jira, 'project_issue_fields'):
                raw_fields = [
                    field.raw
                    for field in self.jira.project_issue_fields(
                        project_id, issue_type_id, maxResults=0
                    )
                ]
            else:
                # Jira SDK 3.5 exposes the same paginated API under its old name.
                raw_fields = []
                while True:
                    page = self.jira.createmeta_fieldtypes(
                        project_id, issue_type_id, startAt=len(raw_fields), maxResults=50
                    )
                    values = page.get('values', [])
                    raw_fields.extend(values)
                    if not values or len(raw_fields) >= page['total']:
                        break
            self._create_fields[cache_key] = {
                str(field.get('fieldId') or field.get('key') or field['id']): field
                for field in raw_fields
            }
        return self._create_fields[cache_key]

    def resolve_field_id(self, name: str) -> str:
        """
        Resolve a field ID or a unique display name to its field ID.

        Field IDs are assigned per Jira instance and are not guaranteed to
        be the same across different instances or projects.
        """
        if self._fields_by_name is None:
            self._fields_by_name = {}
            for field in self.jira.fields():
                self._field_ids.add(str(field['id']))
                field_name = field.get('name')
                if field_name:
                    self._fields_by_name.setdefault(field_name, []).append(str(field['id']))

        if name in self._field_ids:
            return name
        matches = self._fields_by_name.get(name, [])
        if not matches:
            raise tmt.utils.ExportError(f"No '{name}' custom field found in Jira.")
        if len(matches) > 1:
            raise tmt.utils.ExportError(
                f"Multiple fields named '{name}' found in Jira: {matches}. Configure a field ID."
            )
        return matches[0]

    def resolve_transition_id(self, issue_key: str, target_status_name: str) -> str:
        """
        Resolve the transition ID that moves an issue to ``target_status_name``.

        Transition IDs are defined by the issue's workflow, which can
        differ between issue types, projects and Jira instances.
        """
        matches = [
            str(transition['id'])
            for transition in self.jira.transitions(issue_key)
            if transition.get('to', {}).get('name') == target_status_name
        ]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise tmt.utils.ExportError(
                f"Multiple transitions to status '{target_status_name}' for '{issue_key}'."
            )
        raise tmt.utils.ExportError(
            f"No transition to status '{target_status_name}' available for '{issue_key}'."
        )

    def transition_issue(self, key: str, target_status_name: str) -> None:
        """Transition an issue to ``target_status_name``, resolving the transition ID first."""
        self.jira.transition_issue(key, self.resolve_transition_id(key, target_status_name))

    def resolve_account_id(self, query: str) -> Optional[str]:
        """
        Resolve a Jira Cloud ``accountId`` from an email address, display name or username.

        Jira Cloud's REST API no longer accepts a ``name`` (login) when
        assigning issues; an ``accountId`` looked up via the user search
        endpoint is required instead.

        The search performs a loose match and, when nothing really
        matches, has been observed to fall back to returning arbitrary
        unrelated users rather than an empty list. A candidate is
        therefore only accepted when its email, display name or username
        matches (case-insensitively). Prefer exact email matches, then exact
        display names or usernames. Ambiguous matches warn and return None;
        exporters should preserve an existing assignment in this case.
        All decisions are cached for the lifetime of this connection.
        """
        target = query.strip().lower()
        if target in self._accounts:
            return self._accounts[target]
        emails: set[str] = set()
        names: set[str] = set()
        for user in self.jira.search_users(query=query, maxResults=0):
            user_email = getattr(user, 'emailAddress', '').lower()
            user_display = getattr(user, 'displayName', '').lower()
            user_name = getattr(user, 'name', '').lower()
            if target == user_email:
                emails.add(str(user.accountId))
            elif target in (user_display, user_name):
                names.add(str(user.accountId))
        matches = emails or names
        account_id = next(iter(matches)) if len(matches) == 1 else None
        if len(matches) > 1:
            self.logger.warning(
                f"Ambiguous Jira contact '{query}' matches accounts {sorted(matches)}. "
                "Preserving the existing assignee."
            )
        self._accounts[target] = account_id
        return account_id

    def find_issue_by_uuid(
        self, uuid: str, *, project_id: str, issue_type: str, uuid_field: str
    ) -> Optional[str]:
        """
        Find a unique issue by UUID within a configured project and issue type.

        Accept an issue type ID/name and a custom field ID/unique name. This
        public read-only lookup is shared by metadata export and future result
        reporting. Component assignments and fmf backlinks do not affect it.
        Multiple matches fail explicitly; a missing match returns None.
        """
        field_id = self.resolve_field_id(uuid_field)
        if not re.fullmatch(r'customfield_\d+', field_id):
            raise tmt.utils.ExportError('The Jira UUID destination must be a custom field.')
        type_id = self.resolve_issue_type_id(project_id, issue_type)
        issues = self.search_issues(
            f'project={json.dumps(project_id)} AND issuetype={json.dumps(type_id)} '
            f'AND cf[{self.field_jql_id(field_id)}]={json.dumps(uuid)}',
            max_results=2,
            fields=['key'],
        )
        if len(issues) > 1:
            raise tmt.utils.ExportError(f"Multiple Jira issues match UUID '{uuid}'.")
        return str(issues[0]['key']) if issues else None

    def search_issues(
        self, jql: str, max_results: int = 50, fields: Optional[list[str]] = None
    ) -> list[dict[str, Any]]:
        """
        Run a JQL search and return raw issues up to the requested limit.

        Cloud uses enhanced search through the SDK's authenticated transport,
        including with Jira SDK 3.5 on Python 3.9. Server/Data Center retains
        SDK routing. Cloud token pagination is followed when a response page
        is smaller than the requested limit; nonpositive limits fetch all pages.
        """
        if self.jira.deploymentType == 'Cloud':
            issues: list[dict[str, Any]] = []
            params: dict[str, Any] = {
                'jql': jql,
                'fields': fields if fields is not None else ['summary'],
            }
            tokens: set[str] = set()
            while True:
                params['maxResults'] = max_results - len(issues) if max_results > 0 else 50
                page = self.jira._get_json('search/jql', params=dict(params))
                issues.extend(page['issues'])
                if max_results > 0 and len(issues) >= max_results:
                    return issues[:max_results]
                token = page.get('nextPageToken')
                if page.get('isLast', not token):
                    return issues
                if not isinstance(token, str) or not token or token in tokens:
                    raise tmt.utils.ExportError('Jira Cloud search pagination did not advance.')
                tokens.add(token)
                params['nextPageToken'] = token

        result = self.jira.search_issues(
            jql,
            maxResults=max_results,
            json_result=True,
            fields=fields if fields is not None else ['summary'],
        )
        assert isinstance(result, dict)  # json_result=True guarantees a dict
        return cast(list[dict[str, Any]], result.get('issues', []))

    def get_linked_issue_keys(self, key: str) -> set[str]:
        """Return the keys of issues already linked to ``key`` via an issue link."""
        issuelinks = self.jira.issue(key, fields='issuelinks').fields.issuelinks
        keys: set[str] = set()
        for issuelink in issuelinks:
            other = getattr(issuelink, 'inwardIssue', None) or getattr(
                issuelink, 'outwardIssue', None
            )
            if other:
                keys.add(str(other.key))
        return keys

    def get_linked_remote_urls(self, key: str) -> set[str]:
        """Return the URLs of remote (web) links already present on ``key``."""
        return {str(remote_link.object.url) for remote_link in self.jira.remote_links(key)}


def save_link_to_metadata(
    tmt_object: TmtObject,
    link: 'tmt.base.links.Link',
    logger: tmt.log.Logger,
) -> None:
    """
    Store the link into the object metadata on disk
    """

    # Try to add the link relation to object's data if it is not already there
    #
    # cast & ignore: data is basically a container with test/plan/story
    # metadata. As such, it has a lot of keys and values of
    # various data types.
    with tmt_object.node as data:  # type: ignore[reportUnknownVariableType,unused-ignore]
        data = cast(dict[str, Any], data)
        link_data = {link.relation: link.target}

        # Add the 'link' section
        if "link" not in data:
            logger.print(f"Add link '{link.target}' to '{tmt_object.name}'.")
            data["link"] = [link_data]
            return

        # Update the existing 'link' section
        if link_data not in data["link"]:
            logger.print(f"Add link '{link.target}' to '{tmt_object.name}'.")
            data['link'].append(link_data)
        else:
            logger.print(f"Link '{link.target}' already present in '{tmt_object.name}'.")


def link(
    *,
    tmt_objects: Sequence[TmtObject],
    links: 'tmt.base.links.Links',
    separate: bool = False,
    logger: tmt.log.Logger,
) -> None:
    """
    Link provided tmt object(s) with related Jira issue(s)

    The link is added to the following two locations:

        1. test, plan or story metadata on disk (always)
        2. tmt web link added to the Jira issue (if configured)

    :param tmt_objects: list of tmt tests, plan or stories to be linked
    :param links: target jira issues to be linked
    :param separate: by default a single link is created for all
        provided tmt objects (e.g. test + plan covering an issue), if
        True, separate links will be created for each tmt object
    :param logger: a logger instance for logging
    """

    for link in links.get():
        # Save the link to test/plan/story metadata on disk
        for tmt_object in tmt_objects:
            save_link_to_metadata(tmt_object, link, logger)

        # Detect Jira instance based on the issue url
        if not isinstance(link.target, str):
            continue
        jira_instance = JiraInstance.from_issue_url(issue_url=link.target, logger=logger)
        if not jira_instance:
            logger.debug(f"No Jira instance found for issue '{link.target}'.")
            continue

        # Link each provided test, plan or story separately
        # (e.g. the issue is covered by several individual tests)
        if separate:
            for tmt_object in tmt_objects:
                jira_instance.add_link_to_issue(link, [tmt_object])

        # Link all provided tests, plan or stories with a single link
        # (e.g. the issue is covered by a test run under the given plan)
        else:
            jira_instance.add_link_to_issue(link, tmt_objects)
