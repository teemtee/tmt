from enum import Enum

from tmt._compat.pydantic import HttpUrl
from tmt.container import MetadataContainer


class IssueTrackerType(str, Enum):
    jira = 'jira'


class IssueTracker(MetadataContainer):
    type: IssueTrackerType
    url: HttpUrl
    tmt_web_url: HttpUrl
    token: str


class LinkConfig(MetadataContainer):
    issue_tracker: list[IssueTracker]
