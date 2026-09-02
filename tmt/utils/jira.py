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
    ):
        """
        Initialize a Jira instance from raw connection details.

        ``tmt_web_url`` is only needed by :py:meth:`add_link_to_issue`;
        callers that only export/report test data can leave it unset.
        Use :py:meth:`from_issue_tracker` to construct one from a
        configured issue tracker instead.
        """

        self.url = url
        self.tmt_web_url = tmt_web_url
        self.email = email
        self.token = token

        self.logger = logger
        jira_module = import_jira(logger)

        # ignore[attr-defined]: it is defined, but mypy seems to fail
        # detecting it correctly.
        #
        # get_server_info=False: skips an extra server-info request and,
        # with it, the library's own PyPI update check, neither of which
        # tmt needs. That request is also how the SDK detects Cloud vs
        # Server/Data Center (self.jira.deploymentType), which several
        # SDK methods use to decide which API to call -- e.g. search_issues
        # falls back to the removed /rest/api/2/search on non-Cloud. Since
        # this is always Jira Cloud here, set it directly instead.
        #
        # options={'rest_api_version': '3'}: the SDK defaults to the v2 API
        # for everything except search (which it special-cases to v3 for
        # Cloud). v2 doesn't understand Atlassian Document Format, which
        # this module relies on for descriptions and comments, and its
        # search endpoint has since been removed by Atlassian.
        self.jira = jira_module.JIRA(  # type: ignore[attr-defined]
            server=self.url,
            basic_auth=(self.email, self.token),
            get_server_info=False,
            options={'rest_api_version': '3'},
        )
        self.jira.deploymentType = 'Cloud'

        # Caches for schema resolution (issue type IDs and custom field IDs).
        # Populated on first lookup to minimize network requests.
        self._issue_types: Optional[dict[str, str]] = None
        self._fields_by_name: Optional[dict[str, list[str]]] = None

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
        Resolve an issue type name (e.g. ``Test Case``) to its ID within a project.

        Issue type IDs are project-specific, so this cannot be a fixed
        constant shared across Jira instances or projects.
        """
        if self._issue_types is None:
            self._issue_types = {
                issue_type.name: str(issue_type.id)
                for issue_type in self.jira.issue_types_for_project(project_id)
            }

        if name not in self._issue_types:
            raise tmt.utils.ConvertError(
                f"No '{name}' issue type found in project '{project_id}'."
            )
        return self._issue_types[name]

    def resolve_field_id(self, name: str) -> str:
        """
        Resolve a custom field's display name (e.g. ``External issue URL``) to its field ID.

        Field IDs are assigned per Jira instance and are not guaranteed to
        be the same across different instances or projects.
        """
        if self._fields_by_name is None:
            self._fields_by_name = {}
            for field in self.jira.fields():
                field_name = field.get('name')
                if field_name:
                    self._fields_by_name.setdefault(field_name, []).append(str(field['id']))

        matches = self._fields_by_name.get(name, [])
        if not matches:
            raise tmt.utils.ConvertError(f"No '{name}' custom field found in Jira.")
        if len(matches) > 1:
            raise tmt.utils.ConvertError(
                f"Multiple fields named '{name}' found in Jira: {matches}."
            )
        return matches[0]

    def resolve_transition_id(self, issue_key: str, target_status_name: str) -> str:
        """
        Resolve the transition ID that moves an issue to ``target_status_name``.

        Transition IDs are defined by the issue's workflow, which can
        differ between issue types, projects and Jira instances.
        """
        for transition in self.jira.transitions(issue_key):
            if transition.get('to', {}).get('name') == target_status_name:
                return str(transition['id'])
        raise tmt.utils.ConvertError(
            f"No transition to status '{target_status_name}' available for '{issue_key}'."
        )

    def transition_issue(self, key: str, target_status_name: str) -> None:
        """Transition an issue to ``target_status_name``, resolving the transition ID first."""
        self.jira.transition_issue(key, self.resolve_transition_id(key, target_status_name))

    def resolve_account_id(self, email: str) -> Optional[str]:
        """
        Resolve a Jira Cloud ``accountId`` from an email address.

        Jira Cloud's REST API no longer accepts a ``name`` (login) when
        assigning issues; an ``accountId`` looked up via the user search
        endpoint is required instead.

        The search performs a loose match and, when nothing really
        matches, has been observed to fall back to returning arbitrary
        unrelated users rather than an empty list. A candidate is
        therefore only accepted when its email matches exactly
        (case-insensitively); this can also legitimately fail to find an
        existing account whose email is hidden by that user's Jira
        privacy settings.
        """
        for user in self.jira.search_users(query=email):
            if getattr(user, 'emailAddress', '').lower() == email.lower():
                return str(user.accountId)
        return None

    def search_issues(
        self, jql: str, max_results: int = 50, fields: Optional[list[str]] = None
    ) -> list[dict[str, Any]]:
        """Run a JQL search and return the raw matching issues."""
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
