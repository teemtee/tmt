"""
Sphinx extension to generate ``spec/lint.rst`` file
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sphinx.application import Sphinx

from tmt.base.core import LintableCollection, Story, Test
from tmt.base.plan import Plan
from tmt.lint import Linter
from tmt.utils import Path
from tmt.utils.templates import render_template_file_into_file


def _sort_linters(linters: list[Linter]) -> list[Linter]:
    """
    Sort a list of linters by their ID
    """
    return sorted(linters, key=lambda x: x.id)


def generate_lint_checks(app: "Sphinx") -> None:
    """
    Generate ``spec/lint.rst`` file
    """

    template_filepath = Path(app.confdir / "templates/lint-checks.rst.j2")
    output_filepath = Path(app.confdir / "spec/lint.rst")
    (app.confdir / "spec").mkdir(exist_ok=True)

    linters = {
        'TEST_LINTERS': _sort_linters(Test.get_linter_registry()),
        'PLAN_LINTERS': _sort_linters(Plan.get_linter_registry()),
        'STORY_LINTERS': _sort_linters(Story.get_linter_registry()),
        'COLLECTION_LINTERS': _sort_linters(LintableCollection.get_linter_registry()),
    }

    render_template_file_into_file(template_filepath, output_filepath, **linters)


def setup(app: "Sphinx"):
    app.connect("builder-inited", generate_lint_checks)
