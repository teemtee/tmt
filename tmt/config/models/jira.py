"""Configuration for exporting local test metadata to Jira Cloud."""

from typing import Literal, Optional

from tmt._compat.pydantic import Field
from tmt.container import MetadataContainer

ManagedJiraField = Literal['summary', 'description', 'components', 'labels', 'assignee']
DEFAULT_MANAGED_FIELDS: tuple[ManagedJiraField, ...] = (
    'summary',
    'description',
    'components',
    'labels',
    'assignee',
)


class JiraFieldMapping(MetadataContainer):
    """Map one resolved scalar test attribute to a Jira field."""

    source: Literal['tier', 'summary', 'description', 'name']
    type: Literal['text', 'single-select'] = 'text'
    values: Optional[dict[str, str]] = None


class JiraLinkMapping(MetadataContainer):
    """Map a relation to same-instance issue links and/or remote web links."""

    issue_type: Optional[str] = None
    direction: Literal['outward', 'inward'] = 'outward'
    remote: bool = False


class JiraExportConfig(MetadataContainer):
    """Small Jira schema profile from user defaults or selected YAML files."""

    project: Optional[str] = None
    issue_type: str = 'Task'
    uuid_field: Optional[str] = None
    # None disables URL export, 'remote-link' uses a Jira web link, otherwise
    # the value identifies a Jira field by ID or unique name.
    automation_url: Optional[str] = 'remote-link'
    title: str = '{summary}'
    status: Optional[str] = None
    managed_fields: list[ManagedJiraField] = Field(
        default_factory=lambda: list(DEFAULT_MANAGED_FIELDS)
    )
    fields: dict[str, JiraFieldMapping] = Field(default_factory=dict)
    links: dict[str, JiraLinkMapping] = Field(default_factory=dict)
