""" Command line interface for tmt lint command """

from typing import Any

import click

from tmt.cli.common_options import (filter_options, fix_options,
                                    fmf_source_options, verbosity_options)
from tmt.cli.plans import plans_lint
from tmt.cli.stories import stories_lint
from tmt.cli.tests import tests_lint


@click.command(name='lint')
@click.pass_context
@filter_options
@fmf_source_options
@fix_options
@verbosity_options
def lint(context: click.core.Context, **kwargs: Any) -> None:
    """
    Check all the present metadata against the specification.

    Combines all the partial linting (tests, plans and stories)
    into one command. Options are applied to all parts of the lint.

    Regular expression can be used to filter metadata by name.
    Use '.' to select tests, plans and stories under the current
    working directory.
    """
    exit_code = 0
    for command in (tests_lint, plans_lint, stories_lint):
        try:
            context.forward(command)
        except SystemExit as e:
            exit_code |= e.code
    raise SystemExit(exit_code)
