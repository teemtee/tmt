""" Command line interface for tmt clean command """

import collections
import os
from typing import Any

import click
from click import echo, style

import tmt
import tmt.options
import tmt.utils
from tmt.cli.click_group import CustomGroup
from tmt.cli.common_options import (dry_options, verbosity_options,
                                    workdir_root_options)


@click.group(chain=True, invoke_without_command=True, cls=CustomGroup)
@click.pass_context
@verbosity_options
@dry_options
def clean(context: click.core.Context, **kwargs: Any) -> None:
    """
    Clean workdirs, guests or images.

    Without any command, clean everything, stop the guests, remove
    all runs and then remove all images. Search for runs in
    /var/tmp/tmt, if runs are stored elsewhere, the path to them can
    be set using a subcommand (either runs or guests subcommand).

    The subcommands can be chained, the order of cleaning is always
    the same, irrespective of the order on the command line. First, all
    the guests are cleaned, followed by runs and images.
    """
    echo(style('clean', fg='red'))
    clean_obj = tmt.Clean(parent=context.obj.common, context=context)
    context.obj.clean = clean_obj
    context.obj.clean_partials = collections.defaultdict(list)
    exit_code = 0
    if context.invoked_subcommand is None:
        # Set path to default
        context.params['workdir_root'] = tmt.utils.WORKDIR_ROOT
        # Create another level to the hierarchy so that logging indent is
        # consistent between the command and subcommands
        clean_obj = tmt.Clean(parent=clean_obj, context=context)
        if os.path.exists(tmt.utils.WORKDIR_ROOT):
            if not clean_obj.guests():
                exit_code = 1
            if not clean_obj.runs():
                exit_code = 1
        else:
            clean_obj.warn(
                f"Directory '{tmt.utils.WORKDIR_ROOT}' does not exist, "
                f"skipping guest and run cleanup.")
        clean_obj.images()
        raise SystemExit(exit_code)


# FIXME: Click deprecation, see function finito for more info
clean_callback = clean.result_callback
if clean_callback is None:
    clean_callback = clean.resultcallback


# ignore[misc]: untyped decorator. This might be a click issue, but it's
# probably caused by how we initialize clean_callback.
@clean_callback()  # type: ignore[misc]
@click.pass_context
def perform_clean(
        click_context: click.core.Context,
        commands: Any,
        *args: Any,
        **kwargs: Any) -> None:
    """
    Perform clean actions in the correct order.

    We need to ensure that guests are always cleaned before the run workdirs
    even if the user specified them in reverse order.
    """
    clean_order = ("guests", "runs", "images")
    exit_code = 0
    for phase in clean_order:
        for partial in click_context.obj.clean_partials[phase]:
            if not partial():
                exit_code = 1
    raise SystemExit(exit_code)


@clean.command(name='runs')
@click.pass_context
@workdir_root_options
@click.option(
    '-l', '--last', is_flag=True, help='Clean the workdir of the last run.')
@click.option(
    '-i', '--id', 'id_', metavar="ID",
    help='Run id (name or directory path) to clean workdir of.')
@click.option(
    '-k', '--keep', type=int,
    help='The number of latest workdirs to keep, clean the rest.')
@verbosity_options
@dry_options
def clean_runs(
        context: click.core.Context,
        workdir_root: str,
        last: bool,
        id_: str,
        keep: int,
        **kwargs: Any) -> None:
    """
    Clean workdirs of past runs.

    Remove all runs in '/var/tmp/tmt' by default.
    """
    defined = [last is True, id_ is not None, keep is not None]
    if defined.count(True) > 1:
        raise tmt.utils.GeneralError(
            "Options --last, --id and --keep cannot be used together.")
    if keep is not None and keep < 0:
        raise tmt.utils.GeneralError("--keep must not be a negative number.")
    if not os.path.exists(workdir_root):
        raise tmt.utils.GeneralError(f"Path '{workdir_root}' doesn't exist.")
    clean_obj = tmt.Clean(parent=context.obj.clean, context=context)
    context.obj.clean_partials["runs"].append(clean_obj.runs)


@clean.command(name='guests')
@click.pass_context
@workdir_root_options
@click.option(
    '-l', '--last', is_flag=True, help='Stop the guest of the last run.')
@click.option(
    '-i', '--id', 'id_', metavar="ID",
    help='Run id (name or directory path) to stop the guest of.')
@click.option(
    '-h', '--how', metavar='METHOD',
    help='Stop guests of the specified provision method.')
@verbosity_options
@dry_options
def clean_guests(
        context: click.core.Context,
        workdir_root: str,
        last: bool,
        id_: int,
        **kwargs: Any) -> None:
    """
    Stop running guests of runs.

    Stop guests of all runs in '/var/tmp/tmt' by default.
    """
    if last and id_ is not None:
        raise tmt.utils.GeneralError(
            "Options --last and --id cannot be used together.")
    if not os.path.exists(workdir_root):
        raise tmt.utils.GeneralError(f"Path '{workdir_root}' doesn't exist.")
    clean_obj = tmt.Clean(parent=context.obj.clean, context=context)
    context.obj.clean_partials["guests"].append(clean_obj.guests)


@clean.command(name='images')
@click.pass_context
@verbosity_options
@dry_options
def clean_images(context: click.core.Context, **kwargs: Any) -> None:
    """
    Remove images of supported provision methods.

    Currently supported methods are:
     - testcloud
    """
    # FIXME: If there are more provision methods supporting this,
    #        we should add options to specify which provision should be
    #        cleaned, similarly to guests.
    clean_obj = tmt.Clean(parent=context.obj.clean, context=context)
    context.obj.clean_partials["images"].append(clean_obj.images)
