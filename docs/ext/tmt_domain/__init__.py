"""
Sphinx domain for tmt object documentations.

The purpose of this extension is to offer native sphinx documentation helpers
primarily meant to improve compilation speed, cross-referencing, and finetuning
the generated documents.
"""

from typing import TYPE_CHECKING

from .domain import TmtDomain

if TYPE_CHECKING:
    from sphinx.application import Sphinx


def setup(app: "Sphinx") -> None:
    """
    Setup ``tmt_domain`` sphinx extension.
    """
    app.add_domain(TmtDomain)
