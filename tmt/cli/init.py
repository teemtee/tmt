""" Command line interface for tmt init command """

from typing import Any

import click
from fmf.utils import listed

import tmt
import tmt.templates
from tmt.cli.common_options import force_dry_options, verbosity_options


@click.command()
@click.pass_context
@click.argument('path', default='.')
@click.option(
    '-t', '--template', default='empty', metavar='TEMPLATE',
    type=click.Choice(['empty'] + tmt.templates.INIT_TEMPLATES),
    help='Template ({}).'.format(
        listed(tmt.templates.INIT_TEMPLATES, join='or')))
@verbosity_options
@force_dry_options
def init(
        context: click.core.Context,
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

    tmt.Tree._save_context(context)
    tmt.Tree.init(path, template, force)
