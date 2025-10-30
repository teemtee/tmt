"""
Sphinx extension to generate ``guide/test-runner-guest-compatibility-matrix.inc.rst`` file
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sphinx.application import Sphinx

import re
from re import Pattern
from typing import Any

import tmt.plugins
import tmt.steps.provision
from tmt.utils import GeneralError, Path, yaml_to_dict
from tmt.utils.templates import render_template_file_into_file


def generate_test_runner_guest_matrix(app: "Sphinx") -> None:
    """
    Generate ``guide/test-runner-guest-compatibility-matrix.inc.rst`` file
    """

    template_filepath = Path(
        app.confdir / "templates/test-runner-guest-compatibility-matrix.inc.rst.j2"
    )
    definitions_filepath = Path(app.confdir / "test-runner-guest-compatibility.yaml")
    output_filepath = Path(app.confdir / "guide/test-runner-guest-compatibility-matrix.inc.rst")
    (app.confdir / "guide").mkdir(exist_ok=True)

    # We will need a logger...
    logger = tmt.Logger.create()
    logger.add_console_handler()

    # Explore available *export* plugins - do not import other plugins, we don't need them.
    tmt.plugins._explore_packages(logger)

    logger.info('Generating reST file for runner/guest compatibility matrix')

    definitions = yaml_to_dict(definitions_filepath.read_text())

    environment_names: list[str] = definitions['environments']

    try:
        unsupported_environments: list[Pattern[str]] = [
            re.compile(pattern) for pattern in definitions['unsupported']
        ]

    except re.error as error:
        raise GeneralError("Invalid 'unsupported' pattern.") from error

    try:
        unknown_environments: list[Pattern[str]] = [
            re.compile(pattern) for pattern in definitions['unknown']
        ]

    except re.error as error:
        raise GeneralError("Invalid 'unknown' pattern.") from error

    try:
        notes: dict[Pattern[str], Any] = {
            re.compile(note['pattern']): note for note in definitions['notes']
        }

    except re.error as error:
        raise GeneralError("Invalid 'notes' pattern.") from error

    matrix: dict[str, list[tuple[str, str]]] = {}

    for runner in environment_names:
        matrix[runner] = []

        for guest in environment_names:
            combination_key = f'{runner} + {guest}'

            for pattern, note in notes.items():
                if not pattern.match(combination_key):
                    continue

                matrix[runner].append(('supported-with-caveats', note))

                break

            else:
                if any(pattern.match(combination_key) for pattern in unsupported_environments):
                    matrix[runner].append(('unsupported', None))

                elif any(pattern.match(combination_key) for pattern in unknown_environments):
                    matrix[runner].append(('unknown', None))

                else:
                    matrix[runner].append(('supported', None))

    render_template_file_into_file(
        template_filepath,
        output_filepath,
        LOGGER=logger,
        MATRIX=matrix,
        NOTES=notes.values(),
    )


def setup(app: "Sphinx"):
    app.connect("builder-inited", generate_test_runner_guest_matrix)
