"""
Custom tmt sphinx extensions
"""

import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sphinx.application import Sphinx


# TODO: Figure out how to use sphinx's source caching check
# https://github.com/sphinx-doc/sphinx/issues/11556#issuecomment-3201453172


def generate_tmt_docs(app: "Sphinx") -> None:
    """
    Run `make generate` to populate the auto-generated sources
    """

    conf_dir = Path(app.confdir)
    subprocess.run(["make", "generate"], cwd=conf_dir, check=True)


def setup(app: "Sphinx") -> None:
    # Generate sources after loading configuration. That should build
    # everything, including the logo, before Sphinx starts checking
    # whether all input files exist.
    app.connect("builder-inited", generate_tmt_docs)
    # Check a cached version of the linkcheck results
    app.setup_extension("linkcheck_cache")
    # Do sphinx-apidoc
    app.setup_extension("sphinx_apidoc")
    # Various other extensions
    app.setup_extension("generate_lint_checks")
    app.setup_extension("generate_hardware_matrix")
    app.setup_extension("generate_test_runner_guest_matrix")
