#!/usr/bin/env python3

import sys
import textwrap

from tmt.utils import Path
from tmt.utils.templates import TEMPLATE_FILTERS, render_template_file

HELP = textwrap.dedent("""
Usage: generate-template-filters.py <TEMPLATE-PATH> <OUTPUT-PATH>

Generate docs for all known Jinja2 template filters.
""").strip()


def main() -> None:
    if len(sys.argv) != 3:
        print(HELP)

        sys.exit(1)

    template_filepath = Path(sys.argv[1])
    output_filepath = Path(sys.argv[2])

    output_filepath.write_text(render_template_file(template_filepath, TEMPLATES=TEMPLATE_FILTERS))


if __name__ == '__main__':
    main()
