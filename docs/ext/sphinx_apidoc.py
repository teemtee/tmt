"""
Sphinx extension to generate code/autodocs files
"""

from typing import TYPE_CHECKING

from sphinx.util import logging

if TYPE_CHECKING:
    from sphinx.application import Sphinx

logger = logging.getLogger(__name__)


def sphinx_apidoc(app: "Sphinx") -> None:
    """
    Run `sphinx-apidoc`
    """

    from sphinx.ext import apidoc

    # inspired from https://github.com/sphinx-contrib/apidoc
    conf_dir = app.confdir
    root = conf_dir.parent
    # call sphinx-apidoc
    # TODO: Clean the folder before running sphinx-apidoc
    logger.info("Running sphinx-apidoc")
    (conf_dir / "code/autodocs").mkdir(exist_ok=True)
    apidoc.main(
        [
            "--force",
            "--implicit-namespaces",
            "--no-toc",
            "-o",
            str(conf_dir / "code/autodocs"),
            str(root / "tmt"),
        ]
    )


def setup(app: "Sphinx"):
    app.connect("builder-inited", sphinx_apidoc)
