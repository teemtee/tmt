""" ``tmt init`` implementation """

from typing import Any

import click

import tmt.templates
import tmt.utils
from tmt.cli import Context, pass_context
from tmt.cli._root import force_dry_options, main, verbosity_options
from tmt.options import option
from tmt.utils import Path


@main.command()
@pass_context
@click.argument('path', default='.')
@option(
    '-t', '--template', default='empty',
    choices=['empty', *tmt.templates.INIT_TEMPLATES],
    help="Use this template to populate the tree.")
@verbosity_options
@force_dry_options
def init(
        context: Context,
        path: str,
        template: str,
        force: bool,
        **kwargs: Any) -> None:
    """
    Initialize a new tmt tree.

    By default tree is created in the current directory.
    Provide a PATH to create it in a different location.

    \b
    A tree can be optionally populated with example metadata:
    * 'mini' template contains a minimal plan and no tests,
    * 'base' template contains a plan and a beakerlib test,
    * 'full' template contains a 'full' story, an 'full' plan and a shell test.
    """

    tmt.Tree.store_cli_invocation(context)
    tmt.Tree.init(logger=context.obj.logger, path=Path(path), template=template, force=force)
