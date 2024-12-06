from enum import Enum

from tmt._compat.pydantic import HttpUrl

from . import BaseConfig


class IssueTrackerType(str, Enum):
    jira = 'jira'


class IssueTracker(BaseConfig):
    type: IssueTrackerType
    url: HttpUrl
    tmt_web_url: HttpUrl
    token: str


class LinkConfig(BaseConfig):
    issue_tracker: list[IssueTracker]
