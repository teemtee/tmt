"""
Custom tmt sphinx extensions
"""

import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sphinx.application import Sphinx


def generate_tmt_docs(app: "Sphinx", config: Any) -> None:
    """
    Run `make generate` to populate the auto-generated sources
    """

    conf_dir = Path(app.confdir)
    subprocess.run(["make", "generate"], cwd=conf_dir, check=True)


def setup(app: "Sphinx") -> None:
    from linkcheck_cache import linkcheck_cache

    # Generate sources after loading configuration. That should build
    # everything, including the logo, before Sphinx starts checking
    # whether all input files exist.
    app.connect("config-inited", generate_tmt_docs)
    # Check a cached version of the linkcheck results
    app.connect("linkcheck-process-uri", linkcheck_cache)
