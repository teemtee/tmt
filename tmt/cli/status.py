""" Command line interface for tmt status command """

import os
from typing import Any

import click

import tmt
import tmt.utils
from tmt.cli.common_options import verbosity_options, workdir_root_options


@click.command()
@click.pass_context
@workdir_root_options
@click.option(
    '-i', '--id', metavar="ID",
    help='Run id (name or directory path) to show status of.')
@click.option(
    '--abandoned', is_flag=True, default=False,
    help='List runs which have provision step completed but finish step '
         'not yet done.')
@click.option(
    '--active', is_flag=True, default=False,
    help='List runs where at least one of the enabled steps has not '
         'been finished.')
@click.option(
    '--finished', is_flag=True, default=False,
    help='List all runs which have all enabled steps completed.')
@verbosity_options
def status(
        context: click.core.Context,
        workdir_root: str,
        abandoned: bool,
        active: bool,
        finished: bool,
        **kwargs: Any) -> None:
    """
    Show status of runs.

    Lists past runs in the given directory filtered using options.
    /var/tmp/tmt is used by default.

    By default, status of the whole runs is listed. With more
    verbosity (-v), status of every plan is shown. By default,
    the last completed step is displayed, 'done' is used when
    all enabled steps are completed. Status of every step is
    displayed with the most verbosity (-vv).

    """
    if [abandoned, active, finished].count(True) > 1:
        raise tmt.utils.GeneralError(
            "Options --abandoned, --active and --finished cannot be "
            "used together.")
    if not os.path.exists(workdir_root):
        raise tmt.utils.GeneralError(f"Path '{workdir_root}' doesn't exist.")
    status_obj = tmt.Status(context=context)
    status_obj.show()
