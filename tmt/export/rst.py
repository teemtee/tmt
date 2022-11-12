import re
from typing import Any, List, Optional

import fmf.utils

import tmt.base
import tmt.export
import tmt.utils


@tmt.base.Story.provides_export('rst')
class RestructuredExporter(tmt.export.ExportPlugin):
    @classmethod
    def export_story(cls,
                     story: tmt.base.Story,
                     keys: Optional[List[str]] = None,
                     include_title: bool = True) -> str:
        output = ''

        # Title and its anchor
        if include_title:
            depth = len(re.findall('/', story.name)) - 1
            if story.title and story.title != story.node.parent.get('title'):
                title = story.title
            else:
                title = re.sub('.*/', '', story.name)
            output += f'\n.. _{story.name}:\n'
            output += '\n{}\n{}\n'.format(title, '=~^:-><'[depth] * len(title))

        # Summary, story and description
        if story.summary and story.summary != story.node.parent.get('summary'):
            output += '\n{}\n'.format(story.summary)
        if story.story != story.node.parent.get('story'):
            output += '\n*{}*\n'.format(story.story.strip())
        # Insert note about unimplemented feature (leaf nodes only)
        if not story.node.children and not story.implemented:
            output += '\n.. note:: This is a draft, '
            output += 'the story is not implemented yet.\n'
        if (story.description and
                story.description != story.node.parent.get('description')):
            output += '\n{}\n'.format(story.description)

        # Examples
        if story.example and story.example != story.node.parent.get('example'):
            examples = tmt.utils.listify(story.example)
            first = True
            for example in examples:
                if first:
                    output += '\nExamples::\n\n'
                    first = False
                else:
                    output += '\n::\n\n'
                output += tmt.utils.format(
                    '', example, wrap=False, indent=4,
                    key_color=None, value_color=None) + '\n'

        # Status
        if not story.node.children:
            status = []
            for coverage in ['implemented', 'verified', 'documented']:
                if getattr(story, coverage):
                    status.append(coverage)
            output += "\nStatus: {}\n".format(
                fmf.utils.listed(status) if status else 'idea')

        return output

    @classmethod
    def export_story_collection(cls,
                                stories: List[tmt.base.Story],
                                keys: Optional[List[str]] = None,
                                include_title: bool = True,
                                **kwargs: Any) -> str:
        return '\n'.join([cls.export_story(story, include_title=include_title)
                         for story in stories])
