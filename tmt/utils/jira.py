import urllib.parse
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, Optional, Union, cast

import fmf.utils

import tmt.base
import tmt.log
import tmt.utils
from tmt.plugins import ModuleImporter

if TYPE_CHECKING:
    import jira

# Config section item for issue trackers
IssueTracker = dict[Any, Any]

# Test, plan or story
TmtObject = Union['tmt.base.Test', 'tmt.base.Plan', 'tmt.base.Story']


import_jira: ModuleImporter['jira'] = ModuleImporter(  # type: ignore[valid-type]
    'jira',
    tmt.utils.ReportError,
    "Install 'tmt+link-jira' to use the Jira linking.")


def prepare_url_params(tmt_object: 'tmt.base.Core') -> dict[str, str]:
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
    """ A Jira instance configured with url and token """

    def __init__(self, issue_tracker: IssueTracker, logger: tmt.log.Logger):
        """ Initialize Jira instance from the issue tracker config """

        def assert_string(key: str) -> str:
            value = issue_tracker.get(key)
            if not isinstance(value, str):
                raise tmt.utils.GeneralError(
                    f"Invalid '{key}' value '{value}' in issue tracker config.")
            return value

        self.url: str = assert_string("url")
        self.tmt_web_url: str = assert_string("tmt-web-url")
        self.token: str = assert_string("token")

        self.logger = logger
        jira_module = import_jira(logger)

        # ignore[attr-defined]: it is defined, but mypy seems to fail
        # detecting it correctly.
        self.jira = jira_module.JIRA(  # type: ignore[attr-defined]
            server=self.url,
            token_auth=self.token)

    @classmethod
    def from_issue_url(
            cls,
            issue_url: str,
            logger: tmt.log.Logger) -> Optional['JiraInstance']:
        """ Search configured issues trackers for matching Jira instance """

        # Check for the 'link' config section, exit if config missing
        try:
            config_tree = tmt.utils.Config().fmf_tree
            link_config = cast(Optional[fmf.Tree], config_tree.find('/link'))
        except tmt.utils.MetadataError:
            return None
        if not link_config:
            return None

        # Check the list of configured issues trackers
        issue_trackers: Any = link_config.data.get('issue-tracker')

        if not issue_trackers:
            raise tmt.utils.GeneralError(
                "No 'issue-tracker' section found in the 'link' config.")

        if not isinstance(issue_trackers, list):
            raise tmt.utils.GeneralError(
                "The 'issue-tracker' section should be a 'list'.")

        # Find Jira instance matching the issue url
        issue_tracker: Any
        for issue_tracker in issue_trackers:
            if not isinstance(issue_tracker, dict):
                raise tmt.utils.GeneralError(
                    "Issue tracker config should be a 'dict'.")

            # Tracker type must match
            issue_tracker_type: Any = issue_tracker.get("type")
            if not isinstance(issue_tracker_type, str) or issue_tracker_type != "jira":
                continue

            # Issue url must match
            jira_server_url: Any = issue_tracker.get("url")
            if not isinstance(jira_server_url, str):
                raise tmt.utils.GeneralError(
                    "Issue tracker 'url' should be a string.")

            if issue_url.startswith(jira_server_url):
                return JiraInstance(cast(IssueTracker, issue_tracker), logger=logger)

        return None

    def add_link_to_issue(
            self,
            issue_url: str,
            tmt_objects: Sequence[TmtObject]) -> None:
        """ Link one or more tmt objects to the given Jira issue """

        # Prepare a nice title for the link
        title = "tmt: " + fmf.utils.listed(
                [tmt_object.name for tmt_object in tmt_objects])

        # Prepare the tmt web service link from all tmt objects
        web_link_parameters: dict[str, str] = {}
        for tmt_object in tmt_objects:
            web_link_parameters.update(prepare_url_params(tmt_object))
        web_link = urllib.parse.urljoin(
            self.tmt_web_url,
            "?" + urllib.parse.urlencode(web_link_parameters))

        # Add link to the issue
        issue_id = issue_url.split('/')[-1]
        self.jira.add_simple_link(issue_id, {"url": web_link, "title": title})
        self.logger.print(f"Add link '{title}' to Jira issue '{issue_url}'.")


def save_link_to_metadata(
        tmt_object: TmtObject,
        link: 'tmt.base.Link',
        logger: tmt.log.Logger) -> None:
    """ Store the link into the object metadata on disk """
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
        links: 'tmt.base.Links',
        separate: bool = False,
        logger: tmt.log.Logger) -> None:
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

    # TODO: Shall we cover all relations instead?
    for link in links.get("verifies"):

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
                jira_instance.add_link_to_issue(link.target, [tmt_object])

        # Link all provided tests, plan or stories with a single link
        # (e.g. the issue is covered by a test run under the given plan)
        else:
            jira_instance.add_link_to_issue(link.target, tmt_objects)
