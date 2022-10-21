""" Command line interface for the Test Management Tool """

import os
from typing import Any, List

import click

import tmt
import tmt.options
import tmt.plugins
import tmt.utils
from tmt.cli.clean import clean
from tmt.cli.click_context_object import ContextObject
from tmt.cli.click_group import CustomGroup
from tmt.cli.common_options import verbosity_options
from tmt.cli.init import init
from tmt.cli.lint import lint
from tmt.cli.plans import plans
from tmt.cli.run import run
from tmt.cli.setup import setup
from tmt.cli.status import status
from tmt.cli.stories import stories
from tmt.cli.tests import tests

# Explore available plugins (need to detect all supported methods first)
tmt.plugins.explore()


@click.group(invoke_without_command=True, cls=CustomGroup)
@click.pass_context
@click.option(
    '-r', '--root', metavar='PATH', show_default=True,
    help="Path to the tree root, '.' by default.")
@click.option(
    '-c', '--context', metavar='DATA', multiple=True,
    help='Set the fmf context. Use KEY=VAL or KEY=VAL1,VAL2... format '
         'to define individual dimensions or the @FILE notation to load data '
         'from provided yaml file. Can be specified multiple times. ')
@verbosity_options
@click.option(
    '--version', is_flag=True,
    help='Show tmt version and commit hash.')
def main(
        click_contex: click.core.Context,
        root: str,
        context: List[str],
        **kwargs: Any) -> None:
    """ Test Management Tool """
    # Show current tmt version and exit
    if kwargs.get('version'):
        print(f"tmt version: {tmt.__version__}")
        raise SystemExit(0)

    # Disable coloring if NO_COLOR is set
    if 'NO_COLOR' in os.environ:
        click_contex.color = False

    # Save click context and fmf context for future use
    tmt.utils.Common._save_context(click_contex)

    # Initialize metadata tree (from given path or current directory)
    tree = tmt.Tree(root or os.curdir)

    # TODO: context object details need checks
    click_contex.obj = ContextObject(
        common=tmt.utils.Common(),
        fmf_context=tmt.utils.context_to_dict(context),
        steps=set(),
        tree=tree
        )

    # Show overview of available tests, plans and stories
    if click_contex.invoked_subcommand is None:
        tmt.Test.overview(tree)
        tmt.Plan.overview(tree)
        tmt.Story.overview(tree)


# Add subcommands/subgroups
main.add_command(run)
main.add_command(tests)
main.add_command(plans)
main.add_command(stories)
main.add_command(init)
main.add_command(status)
main.add_command(clean)
main.add_command(lint)
main.add_command(setup)
