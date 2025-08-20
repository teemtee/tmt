"""
Custom tmt sphinx extensions
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from sphinx.util import logging

if TYPE_CHECKING:
    from sphinx.application import Sphinx


logger = logging.getLogger(__name__)

# TODO: Figure out how to use sphinx's source caching check
# https://github.com/sphinx-doc/sphinx/issues/11556#issuecomment-3201453172


def sphinx_apidoc(app: Sphinx) -> None:
    """
    Run `shpinx-apidoc`
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


def generate_tmt_docs(app: Sphinx) -> None:
    """
    Run `make generate` to populate the auto-generated sources
    """

    conf_dir = Path(app.confdir)
    subprocess.run(["make", "generate"], cwd=conf_dir, check=True)


def setup(app: Sphinx) -> None:
    from generate_hardware_matrix import generate_hardware_matrix
    from generate_lint_checks import generate_lint_checks
    from generate_template_extensions import generate_template_extensions
    from generate_test_runner_guest_matrix import generate_test_runner_guest_matrix

    # Do sphinx-apidoc
    app.connect("builder-inited", sphinx_apidoc)
    app.connect("builder-inited", generate_lint_checks)
    app.connect("builder-inited", generate_hardware_matrix)
    app.connect("builder-inited", generate_test_runner_guest_matrix)
    app.connect("builder-inited", generate_template_extensions)
    # Generate sources after loading configuration. That should build
    # everything, including the logo, before Sphinx starts checking
    # whether all input files exist.
    app.connect("builder-inited", generate_tmt_docs)
