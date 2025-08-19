"""
Custom tmt sphinx extensions
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sphinx.application import Sphinx


# TODO: Figure out how to use sphinx's source caching check
# https://github.com/sphinx-doc/sphinx/issues/11556#issuecomment-3201453172


def generate_tmt_docs(app: Sphinx) -> None:
    """
    Run `make generate` to populate the auto-generated sources
    """

    conf_dir = Path(app.confdir)
    subprocess.run(["make", "generate"], cwd=conf_dir, check=True)


def setup(app: Sphinx) -> None:
    from sphinx_apidoc import sphinx_apidoc

    # Do sphinx-apidoc
    app.connect("builder-inited", sphinx_apidoc)
    # Generate sources after loading configuration. That should build
    # everything, including the logo, before Sphinx starts checking
    # whether all input files exist.
    app.connect("builder-inited", generate_tmt_docs)
    # Check a cached version of the linkcheck results
    app.setup_extension("linkcheck_cache")
