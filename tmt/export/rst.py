from typing import Any, Optional

import tmt.base
import tmt.export
import tmt.export.template
import tmt.utils
from tmt.utils import Path


@tmt.base.Story.provides_export('rst')
class RestructuredExporter(tmt.export.ExportPlugin):
    @classmethod
    def export_story(cls,
                     story: tmt.base.Story,
                     keys: Optional[list[str]] = None,
                     template: Optional[Path] = None,
                     include_title: bool = True) -> str:
        return tmt.export.template.TemplateExporter.render_template(
            template_filepath=template,
            default_template_filename='default-story.rst.j2',
            keys=keys,
            STORY=story,
            INCLUDE_TITLE=include_title)

    @classmethod
    def export_story_collection(cls,
                                stories: list[tmt.base.Story],
                                keys: Optional[list[str]] = None,
                                template: Optional[Path] = None,
                                include_title: bool = True,
                                **kwargs: Any) -> str:
        return '\n\n'.join([
            cls.export_story(story, keys=keys, template=template, include_title=include_title)
            for story in stories])
