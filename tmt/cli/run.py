"""
``tmt run`` and its subcommands
"""

from typing import Any, Optional

import tmt
import tmt.base.core
import tmt.plugins.plan_shapers
import tmt.steps
import tmt.steps.cleanup
import tmt.steps.discover
import tmt.steps.execute
import tmt.steps.finish
import tmt.steps.prepare
import tmt.steps.provision
import tmt.steps.report
from tmt.cli import CliInvocation, Context, CustomGroup, pass_context
from tmt.cli._root import (
    _load_policies,
    again_option,
    environment_options,
    filter_option,
    force_dry_options,
    main,
    policy_options,
    recipe_options,
    verbosity_options,
    workdir_root_options,
)
from tmt.options import create_options_decorator, option
from tmt.utils import Path, effective_workdir_root


@main.group(chain=True, invoke_without_command=True, cls=CustomGroup)
@pass_context
@option(
    '-i',
    '--id',
    'id_',
    help='Run id (name or directory path).',
    metavar="ID",
)
@option(
    '-l',
    '--last',
    help='Execute the last run once again.',
    is_flag=True,
)
@option(
    '-r',
    '--rm',
    '--remove',
    'remove',
    is_flag=True,
    help='Remove the workdir when test run is finished.',
)
@option(
    '-k',
    '--keep',
    is_flag=True,
    help="""
         Keep all files in the run workdir after testing is done (skip pruning during the finish
         step).
         """,
)
@option(
    '--scratch',
    is_flag=True,
    help='Remove the run workdir before executing to start from scratch.',
)
@option(
    '--follow',
    is_flag=True,
    help='Output the logfile as it grows.',
)
@option(
    '-a',
    '--all',
    help='Run all steps, customize some.',
    is_flag=True,
)
@option(
    '-u',
    '--until',
    choices=tmt.steps.STEPS,
    help='Enable given step and all preceding steps.',
)
@option(
    '-s',
    '--since',
    choices=tmt.steps.STEPS,
    help='Enable given step and all following steps.',
)
@option(
    '-A',
    '--after',
    choices=tmt.steps.STEPS,
    help='Enable all steps after the given one.',
)
@option(
    '-B',
    '--before',
    choices=tmt.steps.STEPS,
    help='Enable all steps before the given one.',
)
@option(
    '-S',
    '--skip',
    choices=tmt.steps.STEPS,
    help='Skip given step(s) during test run execution.',
    multiple=True,
)
@option(
    '--on-plan-error',
    choices=['quit', 'continue'],
    default='quit',
    help="""
         What to do when plan fails to finish. Quit by default, or continue with the next plan.
         """,
)
@environment_options
@workdir_root_options
@verbosity_options
@force_dry_options
@again_option
@policy_options
@recipe_options
def run(
    context: Context,
    id_: Optional[str],
    workdir_root: Optional[Path],
    policy_file: Optional[Path],
    policy_name: Optional[str],
    policy_root: Optional[Path],
    recipe: Optional[Path],
    **kwargs: Any,
) -> None:
    """
    Run test steps.
    """

    # Initialize
    logger = context.obj.logger.descend(logger_name='run', extra_shift=0)
    logger.apply_verbosity_options(**kwargs)

    policies = _load_policies(policy_name, policy_file, policy_root)

    context.obj.run = tmt.Run(
        id_=Path(id_) if id_ is not None else None,
        tree=context.obj.tree,
        cli_invocation=CliInvocation.from_context(context),
        workdir_root=effective_workdir_root(workdir_root),
        policies=policies,
        recipe_path=recipe,
        logger=logger,
    )


for plugin_class in tmt.plugins.plan_shapers._PLAN_SHAPER_PLUGIN_REGISTRY.iter_plugins():
    run = create_options_decorator(plugin_class.run_options())(run)


# Steps options
run.add_command(tmt.steps.discover.DiscoverPlugin.command())
run.add_command(tmt.steps.provision.ProvisionPlugin.command())
run.add_command(tmt.steps.prepare.PreparePlugin.command())
run.add_command(tmt.steps.execute.ExecutePlugin.command())
run.add_command(tmt.steps.report.ReportPlugin.command())
run.add_command(tmt.steps.finish.FinishPlugin.command())
run.add_command(tmt.steps.cleanup.CleanupPlugin.command())
run.add_command(tmt.steps.Login.command())
run.add_command(tmt.steps.Reboot.command())


@run.command(name='plans')
@pass_context
@option(
    '-n',
    '--name',
    'names',
    metavar='[REGEXP|.]',
    multiple=True,
    help="Regular expression to match plan name or '.' for current directory.",
)
@filter_option
@option(
    '-c',
    '--condition',
    'conditions',
    metavar="EXPR",
    multiple=True,
    help="Use arbitrary Python expression for filtering.",
)
@option(
    '--link',
    'links',
    metavar="RELATION:TARGET",
    multiple=True,
    help="""
         Filter by linked objects (regular expressions are supported for both relation and target).
         """,
)
@option(
    '--default',
    is_flag=True,
    help="Use default plans even if others are available.",
)
@verbosity_options
def run_plans(context: Context, **kwargs: Any) -> None:
    """
    Select plans which should be executed.

    Regular expression can be used to filter plans by name.
    Use '.' to select plans under the current working directory.
    """

    tmt.base.core.Plan.store_cli_invocation(context)


@run.command(name='tests')
@pass_context
@option(
    '-n',
    '--name',
    'names',
    metavar='[REGEXP|.]',
    multiple=True,
    help="Regular expression to match test name or '.' for current directory.",
)
@filter_option
@option(
    '-c',
    '--condition',
    'conditions',
    metavar="EXPR",
    multiple=True,
    help="Use arbitrary Python expression for filtering.",
)
@option(
    '--link',
    'links',
    metavar="RELATION:TARGET",
    multiple=True,
    help="""
         Filter by linked objects (regular expressions are supported for both relation and target).
         """,
)
@option(
    '--failed-only',
    is_flag=True,
    default=False,
    help="""
         Select only failed tests from a previous run.
         Used when rerunning existing runs and requires either --id or --last option.
         """,
)
@verbosity_options
def run_tests(context: Context, **kwargs: Any) -> None:
    """
    Select tests which should be executed.

    Regular expression can be used to filter tests by name.
    Use '.' to select tests under the current working directory.
    """

    tmt.base.core.Test.store_cli_invocation(context)


# TODO: commands is unknown, needs revisit
@run.result_callback()
@pass_context
def finito(
    click_context: Context,
    /,
    commands: Any,
    *args: Any,
    **kwargs: Any,
) -> None:
    """
    Run tests if run defined
    """

    if click_context.obj.run:
        click_context.obj.run.go()
