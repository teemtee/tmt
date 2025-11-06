"""
Sphinx extension to generate ``code/template-extensions.rst`` file
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sphinx.application import Sphinx

from tmt.utils import Path
from tmt.utils.templates import TEMPLATE_FILTERS, TEMPLATE_TESTS, render_template_file_into_file


def generate_template_extensions(app: "Sphinx") -> None:
    """
    Generate ``code/template-extensions.rst`` file
    """

    template_filepath = Path(app.confdir / "templates/template-extensions.rst.j2")
    output_filepath = Path(app.confdir / "code/template-extensions.rst")
    (app.confdir / "code").mkdir(exist_ok=True)

    render_template_file_into_file(
        template_filepath,
        output_filepath,
        FILTERS=TEMPLATE_FILTERS,
        TESTS=TEMPLATE_TESTS,
    )


def setup(app: "Sphinx"):
    app.connect("builder-inited", generate_template_extensions)
