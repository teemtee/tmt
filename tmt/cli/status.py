""" ``tmt status`` implementation """

from typing import Any, Optional

import tmt.utils
from tmt.cli import CliInvocation, Context, pass_context
from tmt.cli._root import main, verbosity_options, workdir_root_options
from tmt.options import option
from tmt.utils import Path, effective_workdir_root


@main.command()
@pass_context
@workdir_root_options
@option(
    '-i', '--id', metavar="ID", multiple=True,
    help='Run id(name or directory path) to show status of. Can be specified multiple times.')
@option(
    '--abandoned', is_flag=True, default=False,
    help='List runs which have provision step completed but finish step not yet done.')
@option(
    '--active', is_flag=True, default=False,
    help='List runs where at least one of the enabled steps has not been finished.')
@option(
    '--finished', is_flag=True, default=False,
    help='List all runs which have all enabled steps completed.')
@verbosity_options
def status(
        context: Context,
        _workdir_root: Optional[str],
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

    workdir_root = Path(_workdir_root) if _workdir_root is not None else None
    if workdir_root and not workdir_root.exists():
        raise tmt.utils.GeneralError(f"Path '{workdir_root}' doesn't exist.")
    status_obj = tmt.Status(
        logger=context.obj.logger.clone().apply_verbosity_options(**kwargs),
        cli_invocation=CliInvocation.from_context(context),
        workdir_root=effective_workdir_root(workdir_root))
    status_obj.show()
