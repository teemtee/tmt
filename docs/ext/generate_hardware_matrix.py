"""
Sphinx extension to generate ``plugins/hardware-matrix.rst`` file
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sphinx.application import Sphinx

import tmt.plugins
import tmt.steps.provision
from tmt.utils import Path
from tmt.utils.templates import render_template_file_into_file


def generate_hardware_matrix(app: "Sphinx") -> None:
    """
    Generate ``plugins/hardware-matrix.rst`` file
    """

    template_filepath = Path(app.confdir / "templates/hardware-matrix.rst.j2")
    output_filepath = Path(app.confdir / "plugins/hardware-matrix.rst")
    (app.confdir / "plugins").mkdir(exist_ok=True)

    # We will need a logger...
    logger = tmt.Logger.create()
    logger.add_console_handler()

    # Explore available *export* plugins - do not import other plugins, we don't need them.
    tmt.plugins._explore_packages(logger)

    known_methods = sorted(
        tmt.steps.provision.ProvisionPlugin._supported_methods.iter_plugin_ids()
    )

    tree = tmt.Tree(logger=logger, path=Path.cwd())

    logger.info('Generating reST file for HW requirement support matrix')

    matrix: dict[str, dict[str, tuple[bool, str]]] = {}
    notes: list[str] = []

    for story in tree.stories(logger=logger, names=['^/spec/hardware/.*'], whole=True):
        hw_requirement = story.name.replace('/spec/hardware/', '')

        if hw_requirement == 'arch':
            continue

        # C420: current implementation creates a new tuple for each method
        # https://github.com/teemtee/tmt/pull/3662#discussion_r2040669353
        matrix[hw_requirement] = {method: (False, int) for method in known_methods}  # noqa: C420

        if not story.link:
            pass

        for link in story.link.get(relation='implemented-by'):
            implemented_by_method = Path(link.target).stem

            if implemented_by_method == 'mrack':
                implemented_by_method = 'beaker'

            elif implemented_by_method == 'testcloud':
                implemented_by_method = 'virtual.testcloud'

            if implemented_by_method not in matrix[hw_requirement]:
                raise Exception(f'{implemented_by_method} unknown')

            if link.note:
                notes.append(f'``{hw_requirement}`` with ``{implemented_by_method}``: {link.note}')

                matrix[hw_requirement][implemented_by_method] = (True, len(notes))

            else:
                matrix[hw_requirement][implemented_by_method] = (True, None)

    render_template_file_into_file(
        template_filepath,
        output_filepath,
        LOGGER=logger,
        MATRIX=matrix,
        NOTES=notes,
    )


def setup(app: "Sphinx"):
    app.connect("builder-inited", generate_hardware_matrix)
