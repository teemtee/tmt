""" Command line interface for tmt plans command """

from typing import Any

import click
from click import echo
from fmf.utils import listed

import tmt
import tmt.identifier
import tmt.templates
import tmt.utils
from tmt.cli.click_group import CustomGroup
from tmt.cli.common_options import (filter_options, filter_options_long,
                                    fmf_source_options, force_dry_options,
                                    remote_plan_options, verbosity_options)


@click.group(invoke_without_command=True, cls=CustomGroup)
@click.pass_context
@verbosity_options
@remote_plan_options
def plans(context: click.core.Context, **kwargs: Any) -> None:
    """
    Manage test plans (L2 metadata).

    \b
    Search for available plans.
    Explore detailed test step configuration.
    """
    tmt.Plan._save_context(context)

    # Show overview of available plans
    if context.invoked_subcommand is None:
        tmt.Plan.overview(context.obj.tree)


@plans.command(name='ls')
@click.pass_context
@filter_options
@verbosity_options
@remote_plan_options
def plans_ls(context: click.core.Context, **kwargs: Any) -> None:
    """
    List available plans.

    Regular expression can be used to filter plans by name.
    Use '.' to select plans under the current working directory.
    """
    tmt.Plan._save_context(context)
    for plan in context.obj.tree.plans():
        plan.ls()


@plans.command(name='show')
@click.pass_context
@filter_options
@verbosity_options
@remote_plan_options
def plans_show(context: click.core.Context, **kwargs: Any) -> None:
    """
    Show plan details.

    Regular expression can be used to filter plans by name.
    Use '.' to select plans under the current working directory.
    """
    tmt.Plan._save_context(context)
    for plan in context.obj.tree.plans():
        plan.show()
        echo()


@plans.command(name='lint')
@click.pass_context
@filter_options
@fmf_source_options
@verbosity_options
def plans_lint(context: click.core.Context, **kwargs: Any) -> None:
    """
    Check plans against the L2 metadata specification.

    Regular expression can be used to filter plans by name.
    Use '.' to select plans under the current working directory.
    """
    # FIXME: Workaround https://github.com/pallets/click/pull/1840 for click 7
    context.params.update(**kwargs)
    tmt.Plan._save_context(context)
    exit_code = 0
    for plan in context.obj.tree.plans():
        if not plan.lint():
            exit_code = 1
        echo()
    raise SystemExit(exit_code)


_plan_templates = listed(tmt.templates.PLAN, join='or')


@plans.command(name='create')
@click.pass_context
@click.argument('name')
@click.option(
    '-t', '--template', metavar='TEMPLATE',
    help='Plan template ({}).'.format(_plan_templates),
    prompt='Template ({})'.format(_plan_templates))
@click.option(
    '--discover', metavar='YAML', multiple=True,
    help='Discover phase content in yaml format.')
@click.option(
    '--provision', metavar='YAML', multiple=True,
    help='Provision phase content in yaml format.')
@click.option(
    '--prepare', metavar='YAML', multiple=True,
    help='Prepare phase content in yaml format.')
@click.option(
    '--execute', metavar='YAML', multiple=True,
    help='Execute phase content in yaml format.')
@click.option(
    '--report', metavar='YAML', multiple=True,
    help='Report phase content in yaml format.')
@click.option(
    '--finish', metavar='YAML', multiple=True,
    help='Finish phase content in yaml format.')
@verbosity_options
@force_dry_options
def plans_create(
        context: click.core.Context,
        name: str,
        template: str,
        force: bool,
        **kwargs: Any) -> None:
    """ Create a new plan based on given template. """
    tmt.Plan._save_context(context)
    tmt.Plan.create(name, template, context.obj.tree.root, force)


@plans.command(name='export')
@click.pass_context
@filter_options_long
@click.option(
    '--format', 'format_', default='yaml', show_default=True, metavar='FORMAT',
    help='Output format.')
@click.option(
    '-d', '--debug', is_flag=True,
    help='Provide as much debugging details as possible.')
def plans_export(context: click.core.Context, format_: str, **kwargs: Any) -> None:
    """
    Export plans into desired format.

    Regular expression can be used to filter plans by name.
    Use '.' to select plans under the current working directory.
    """
    tmt.Plan._save_context(context)
    plans = [plan.export(format_=tmt.base.ExportFormat.DICT) for plan in context.obj.tree.plans()]

    # Choose proper format
    if format_ == 'dict':
        echo(plans)
    elif format_ == 'yaml':
        echo(tmt.utils.dict_to_yaml(plans))
    else:
        raise tmt.utils.GeneralError(
            f"Invalid plan export format '{format_}'.")


@plans.command(name="id")
@click.pass_context
@filter_options
@verbosity_options
@force_dry_options
def plans_id(context: click.core.Context, **kwargs: Any) -> None:
    """
    Generate a unique id for each selected plan.

    A new UUID is generated for each plan matching the provided
    filter and the value is stored to disk. Existing identifiers
    are kept intact.
    """
    tmt.Plan._save_context(context)
    for plan in context.obj.tree.plans():
        tmt.identifier.id_command(plan.node, "plan", dry=kwargs["dry"])
