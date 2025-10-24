from typing import TYPE_CHECKING

from .domain import TmtDomain

if TYPE_CHECKING:
    from sphinx.application import Sphinx


def setup(app: "Sphinx") -> None:
    app.add_domain(TmtDomain)
