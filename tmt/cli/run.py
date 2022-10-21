""" Command line interface for tmt run command """

from typing import TYPE_CHECKING, Any

import click

import tmt
import tmt.steps
from tmt.cli.click_context_object import ContextObject
from tmt.cli.click_group import CustomGroup
from tmt.cli.common_options import force_dry_options, verbosity_options

if TYPE_CHECKING:
    import tmt.steps.discover
    import tmt.steps.execute


@click.group(chain=True, invoke_without_command=True, cls=CustomGroup)
@click.pass_context
@click.option(
    '-i', '--id', 'id_', help='Run id (name or directory path).', metavar="ID")
@click.option(
    '-l', '--last', help='Execute the last run once again.', is_flag=True)
@click.option(
    '-r', '--rm', '--remove', 'remove', is_flag=True,
    help='Remove the workdir when test run is finished.')
@click.option(
    '--scratch', is_flag=True,
    help='Remove the run workdir before executing to start from scratch.')
@click.option(
    '--follow', is_flag=True,
    help='Output the logfile as it grows.')
@click.option(
    '-a', '--all', help='Run all steps, customize some.', is_flag=True)
@click.option(
    '-u', '--until', type=click.Choice(tmt.steps.STEPS), metavar='STEP',
    help='Enable given step and all preceding steps.')
@click.option(
    '-s', '--since', type=click.Choice(tmt.steps.STEPS), metavar='STEP',
    help='Enable given step and all following steps.')
@click.option(
    '-A', '--after', type=click.Choice(tmt.steps.STEPS), metavar='STEP',
    help='Enable all steps after the given one.')
@click.option(
    '-B', '--before', type=click.Choice(tmt.steps.STEPS), metavar='STEP',
    help='Enable all steps before the given one.')
@click.option(
    '-S', '--skip', type=click.Choice(tmt.steps.STEPS), metavar='STEP',
    help='Skip given step(s) during test run execution.', multiple=True)
@click.option(
    '-e', '--environment', metavar='KEY=VALUE|@FILE', multiple=True,
    help='Set environment variable. Can be specified multiple times. The '
         '"@" prefix marks a file to load (yaml or dotenv formats supported).')
@click.option(
    '--environment-file', metavar='FILE|URL', multiple=True,
    help='Set environment variables from file or url (yaml or dotenv formats '
         'are supported). Can be specified multiple times.')
@verbosity_options
@force_dry_options
def run(context: click.core.Context, id_: str, **kwargs: Any) -> None:
    """ Run test steps. """
    # Initialize
    run = tmt.Run(id_, context.obj.tree, context=context)
    context.obj.run = run


# Steps options
run.add_command(tmt.steps.discover.DiscoverPlugin.command())
run.add_command(tmt.steps.provision.ProvisionPlugin.command())
run.add_command(tmt.steps.prepare.PreparePlugin.command())
run.add_command(tmt.steps.execute.ExecutePlugin.command())
run.add_command(tmt.steps.report.ReportPlugin.command())
run.add_command(tmt.steps.finish.FinishPlugin.command())
run.add_command(tmt.steps.Login.command())
run.add_command(tmt.steps.Reboot.command())


@run.command(name='plans')
@click.pass_context
@click.option(
    '-n', '--name', 'names', metavar='[REGEXP|.]', multiple=True,
    help="Regular expression to match plan name or '.' for current directory.")
@click.option(
    '-f', '--filter', 'filters', metavar='FILTER', multiple=True,
    help="Apply advanced filter (see 'pydoc fmf.filter').")
@click.option(
    '-c', '--condition', 'conditions', metavar="EXPR", multiple=True,
    help="Use arbitrary Python expression for filtering.")
@click.option(
    '--link', 'links', metavar="RELATION:TARGET", multiple=True,
    help="Filter by linked objects (regular expressions are "
         "supported for both relation and target).")
@click.option(
    '--default', is_flag=True,
    help="Use default plans even if others are available.")
@verbosity_options
def run_plans(context: click.core.Context, **kwargs: Any) -> None:
    """
    Select plans which should be executed.

    Regular expression can be used to filter plans by name.
    Use '.' to select plans under the current working directory.
    """
    tmt.base.Plan._save_context(context)


@run.command(name='tests')
@click.pass_context
@click.option(
    '-n', '--name', 'names', metavar='[REGEXP|.]', multiple=True,
    help="Regular expression to match test name or '.' for current directory.")
@click.option(
    '-f', '--filter', 'filters', metavar='FILTER', multiple=True,
    help="Apply advanced filter (see 'pydoc fmf.filter').")
@click.option(
    '-c', '--condition', 'conditions', metavar="EXPR", multiple=True,
    help="Use arbitrary Python expression for filtering.")
@click.option(
    '--link', 'links', metavar="RELATION:TARGET", multiple=True,
    help="Filter by linked objects (regular expressions are "
         "supported for both relation and target).")
@verbosity_options
def run_tests(context: click.core.Context, **kwargs: Any) -> None:
    """
    Select tests which should be executed.

    Regular expression can be used to filter tests by name.
    Use '.' to select tests under the current working directory.
    """
    tmt.base.Test._save_context(context)


# FIXME: click 8.0 renamed resultcallback to result_callback. The former
#        name will be removed in click 8.1. However, click 8.0 will not
#        be added to F33 and F34. Get rid of this workaround once
#        all Fedora + EPEL releases have click 8.0 or newer available.
run_callback = run.result_callback
if run_callback is None:
    run_callback = run.resultcallback


# TODO: commands is unknown, needs revisit
# ignore[misc]: untyped decorator. This might be a click issue, but it's
# probably caused by how we initialize clean_callback.
@run_callback()  # type: ignore[misc]
@click.pass_context
def finito(
        click_context: click.core.Context,
        commands: Any,
        *args: Any,
        **kwargs: Any) -> None:
    """ Run tests if run defined """
    if isinstance(click_context.obj, ContextObject) and click_context.obj.run:
        click_context.obj.run.go()
