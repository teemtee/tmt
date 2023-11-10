from typing import Any, Optional

import tmt.base
import tmt.export
import tmt.utils
from tmt.utils import Path


@tmt.base.FmfId.provides_export('template')
@tmt.base.Test.provides_export('template')
@tmt.base.Plan.provides_export('template')
@tmt.base.Story.provides_export('template')
class TemplateExporter(tmt.export.ExportPlugin):
    @classmethod
    def render_template(
            cls,
            *,
            template_filepath: Optional[Path] = None,
            default_template_filename: str,
            keys: Optional[list[str]] = None,
            **variables: Any
            ) -> str:
        return tmt.utils.render_template_file(
            template_filepath or tmt.export.TEMPLATES_DIRECTORY / default_template_filename,
            KEYS=keys,
            **variables
            )

    @classmethod
    def export_fmfid_collection(cls,
                                fmf_ids: list[tmt.base.FmfId],
                                keys: Optional[list[str]] = None,
                                template: Optional[Path] = None,
                                **kwargs: Any) -> str:
        return '\n\n'.join([
            cls.render_template(
                template_filepath=template,
                default_template_filename='default-fmfid.j2',
                keys=keys,
                FMF_ID=fmf_id)
            for fmf_id in fmf_ids
            ])

    @classmethod
    def export_test_collection(cls,
                               tests: list[tmt.base.Test],
                               keys: Optional[list[str]] = None,
                               template: Optional[Path] = None,
                               **kwargs: Any) -> str:
        return '\n\n'.join([
            cls.render_template(
                template_filepath=template,
                default_template_filename='default-test.j2',
                keys=keys,
                TEST=test)
            for test in tests
            ])

    @classmethod
    def export_plan_collection(cls,
                               plans: list[tmt.base.Plan],
                               keys: Optional[list[str]] = None,
                               template: Optional[Path] = None,
                               **kwargs: Any) -> str:
        return '\n\n'.join([
            cls.render_template(
                template_filepath=template,
                default_template_filename='default-plan.j2',
                keys=keys,
                PLAN=plan)
            for plan in plans
            ])

    @classmethod
    def export_story_collection(cls,
                                stories: list[tmt.base.Story],
                                keys: Optional[list[str]] = None,
                                template: Optional[Path] = None,
                                include_title: bool = True,
                                **kwargs: Any) -> str:
        return '\n\n'.join([
            cls.render_template(
                template_filepath=template,
                default_template_filename='default-story.j2',
                keys=keys,
                STORY=story,
                INCLUDE_TITLE=include_title)
            for story in stories
            ])
