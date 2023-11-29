#!/usr/bin/env python3

import sys
import textwrap

import tmt.checks
import tmt.plugins
import tmt.steps.report
import tmt.utils
from tmt.utils import Path, render_template_file

HELP = textwrap.dedent("""
Usage: generate-test-checks.py <TEMPLATE-PATH> <OUTPUT-PATH>

Generate pages for test checks from their fmf specifications.
""").strip()


def main() -> None:
    if len(sys.argv) != 3:
        print(HELP)

        sys.exit(1)

    template_filepath = Path(sys.argv[1])
    output_filepath = Path(sys.argv[2])

    # We will need a logger...
    logger = tmt.Logger.create()
    logger.add_console_handler()

    # ... explore available plugins...
    tmt.plugins.explore(logger)

    # ... and render the template.
    output_filepath.write_text(render_template_file(
        template_filepath,
        REGISTRY=tmt.checks._CHECK_PLUGIN_REGISTRY,
        container_fields=tmt.utils.container_fields,
        container_field=tmt.utils.container_field))


if __name__ == '__main__':
    main()
