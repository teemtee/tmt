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


def setup(app: Sphinx) -> None:
    # This is a meta extension that gatheres all of the individual extensions
    # in the ext folder.
    app.setup_extension("linkcheck_cache")
    app.setup_extension("sphinx_apidoc")
    app.setup_extension("generate_lint_checks")
    app.setup_extension("generate_hardware_matrix")
    app.setup_extension("generate_test_runner_guest_matrix")
    app.setup_extension("generate_template_extensions")
    app.setup_extension("generate_stories")
    app.setup_extension("generate_plugins")
