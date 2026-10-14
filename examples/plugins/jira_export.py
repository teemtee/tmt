"""Example external exporter loaded through ``TMT_PLUGINS=examples/plugins``."""

from typing import Any

import tmt.base.core
from tmt.export.jira import JiraExportContext, JiraExporter


@tmt.base.core.Test.provides_export('jira-example')
class SiteJiraExporter(JiraExporter):
    """Reuse Jira discovery, identity, schema resolution and CRUD unchanged."""

    @classmethod
    def enrich_payload(
        cls, test: tmt.base.core.Test, context: JiraExportContext, fields: dict[str, Any]
    ) -> None:
        """Add a site label based on resolved test metadata, including in dry runs."""
        if 'smoke' in test.tag:
            fields['labels'].append('site-smoke')

    @classmethod
    def post_export(cls, test: tmt.base.core.Test, context: JiraExportContext) -> None:
        """Preview a post-export action and show where optional integrations belong."""
        if context.dry_run:
            test._logger.info('site action', f'would process {test.name}')
            return
        assert context.issue_key is not None
        # A metadata integration could call another system here using the resolved
        # test, UUID and Jira issue key. This example only logs the action.
        test._logger.info('site action', f'process {context.issue_key} for {test.name}')
