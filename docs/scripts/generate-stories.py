#!/usr/bin/env python3

import sys
import textwrap
from unittest.mock import Mock as MagicMock

import tmt.plugins
from tmt.utils import Path

HELP = textwrap.dedent("""
Usage: generate-stories.py <TEMPLATE-PATH>

Generate pages for stories from their fmf specifications.
""").strip()

# Mock extra modules


class Mock(MagicMock):
    @classmethod
    def __getattr__(cls, name: str) -> 'Mock':
        return Mock()


MOCK_MODULES = ['testcloud', 'testcloud.image', 'testcloud.instance']
sys.modules.update((mod_name, Mock()) for mod_name in MOCK_MODULES)


AREA_TITLES = {
    '/stories/docs': 'Documentation',
    '/stories/cli': 'Command Line',
    '/stories/install': 'Installation',
    '/stories/features': 'Features',
    '/stories/deferred': 'Deferred',
    '/spec/core': 'Core',
    '/spec/tests': 'Tests',
    '/spec/plans': 'Plans',
    '/spec/stories': 'Stories',
    '/spec/context': 'Context',
    '/spec/policy': 'Policy',
    '/spec/hardware': 'Hardware',
    '/spec/results': 'Results',
}


def main() -> None:
    if len(sys.argv) != 2:
        print(HELP)

        sys.exit(1)

    story_template_filepath = Path(sys.argv[1])

    # We will need a logger...
    logger = tmt.Logger.create()
    logger.add_console_handler()

    # Explore available plugins
    tmt.plugins.explore(logger)

    # Generate stories
    tree = tmt.Tree(logger=logger, path=Path.cwd())

    for area, title in AREA_TITLES.items():
        logger.info(f'Generating rst files from {area}')

        with open(f"{area.lstrip('/')}.rst", 'w') as doc:
            # Anchor and title
            doc.write(f'.. _{area}:\n\n')
            doc.write(f"{title}\n{'=' * len(title)}\n")
            # Included stories
            for story in tree.stories(names=[area], whole=True):
                if not story.enabled:
                    continue

                rendered = story.export(
                    format='rst',
                    include_title=story.name != area,
                    template=story_template_filepath,
                )

                doc.write(rendered)
                doc.write('\n\n')


if __name__ == '__main__':
    main()
