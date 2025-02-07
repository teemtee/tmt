#!/usr/bin/env python3

import re
import sys
import textwrap
from re import Pattern
from typing import Any

import tmt.plugins
import tmt.steps.provision
from tmt.utils import GeneralError, Path, yaml_to_dict
from tmt.utils.templates import render_template_file

HELP = textwrap.dedent("""
Usage: generate-runner-guest-matrix.py <TEMPLATE-PATH> <FOO> <OUTPUT-PATH>

Generate page with runner vs guest compatibility matrix.
""").strip()


def main() -> None:
    if len(sys.argv) != 4:
        print(HELP)

        sys.exit(1)

    template_filepath = Path(sys.argv[1])
    definitions_filepath = Path(sys.argv[2])
    output_filepath = Path(sys.argv[3])

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

    except re.error as exc:
        raise GeneralError(f"Invalid 'unsupported' pattern '{exc.pattern}'.") from exc

    try:
        unknown_environments: list[Pattern[str]] = [
            re.compile(pattern) for pattern in definitions['unknown']
        ]

    except re.error as exc:
        raise GeneralError(f"Invalid 'unknown' pattern '{exc.pattern}'.") from exc

    try:
        notes: dict[Pattern[str], Any] = {
            re.compile(note['pattern']): note for note in definitions['notes']
        }

    except re.error as exc:
        raise GeneralError(f"Invalid 'notes' pattern '{exc.pattern}'.") from exc

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

    output_filepath.write_text(
        render_template_file(
            template_filepath,
            LOGGER=logger,
            MATRIX=matrix,
            NOTES=notes.values(),
        ),
    )


if __name__ == '__main__':
    main()
