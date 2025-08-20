"""
Sphinx extension to generate ``spec/*`` and ``stories/*`` files
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sphinx.application import Sphinx

import sys
from unittest.mock import Mock as MagicMock

import tmt.plugins
from tmt.utils import Path

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
    '/spec/recipe': 'Recipe',
    '/spec/hardware': 'Hardware',
    '/spec/results': 'Results',
}


def generate_stories(app: "Sphinx") -> None:
    """
    Generate ``spec/*`` and ``stories/*`` files
    """

    story_template_filepath = Path(app.confdir / "templates/story.rst.j2")
    (app.confdir / "spec").mkdir(exist_ok=True)
    (app.confdir / "stories").mkdir(exist_ok=True)

    # We will need a logger...
    logger = tmt.Logger.create()
    logger.add_console_handler()

    # Explore available plugins
    tmt.plugins.explore(logger)

    # Generate stories
    tree = tmt.Tree(logger=logger, path=Path.cwd())

    for area, title in AREA_TITLES.items():
        logger.info(f'Generating rst files from {area}')

        with (app.confdir / f"{area.lstrip('/')}.rst").open('w') as doc:
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


def setup(app: "Sphinx"):
    app.connect("builder-inited", generate_stories)
