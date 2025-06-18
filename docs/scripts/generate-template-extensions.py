#!/usr/bin/env python3

import sys
import textwrap

from tmt.utils import Path
from tmt.utils.templates import TEMPLATE_FILTERS, TEMPLATE_TESTS, render_template_file_into_file

HELP = textwrap.dedent("""
Usage: generate-template-extensions.py <TEMPLATE-PATH> <OUTPUT-PATH>

Generate docs for all custom Jinja2 template filters and tests.
""").strip()


def main() -> None:
    if len(sys.argv) != 3:
        print(HELP)

        sys.exit(1)

    template_filepath = Path(sys.argv[1])
    output_filepath = Path(sys.argv[2])

    render_template_file_into_file(
        template_filepath,
        output_filepath,
        FILTERS=TEMPLATE_FILTERS,
        TESTS=TEMPLATE_TESTS,
    )


if __name__ == '__main__':
    main()
