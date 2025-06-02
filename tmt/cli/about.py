"""``tmt about`` implementation"""

import json
import re
from typing import Any

from click import echo

import tmt.utils
import tmt.utils.hints
import tmt.utils.rest
from tmt.cli import Context, CustomGroup, pass_context
from tmt.cli._root import main
from tmt.options import option
from tmt.plugins import PluginRegistry, iter_plugin_registries
from tmt.utils import GeneralError
from tmt.utils.templates import render_template, render_template_file

TEMPLATES_DIRECTORY = tmt.utils.resource_files('cli/templates/about')


@main.group(invoke_without_command=True, cls=CustomGroup)
@pass_context
def about(context: Context) -> None:
    """
    Show info about tmt itself, its plugins, documentation and other
    components.
    """

    if context.invoked_subcommand is None:
        echo(context.get_help(), color=context.color)


def _render_plugins_list_rest() -> str:
    registry_intro_map: dict[str, str] = {
        r'export\.([a-z]+)': 'Export plugins for {{ MATCH.group(1).lower() }}',
        r'test.check': 'Test check plugins',
        r'test.framework': 'Test framework plugins',
        r'package_managers': 'Package manager plugins',
        r'plan_shapers': 'Plan shapers',
        r'prepare.feature': 'prepare/feature plugins',
        r'step\.([a-z]+)': '{{ MATCH.group(1).capitalize() }} step plugins',
    }

    def find_intro(registry: PluginRegistry[Any]) -> str:
        for pattern, intro_template in registry_intro_map.items():
            match = re.match(pattern, registry.name)

            if match is None:
                continue

            return render_template(intro_template, MATCH=match)

        raise GeneralError(f"Unknown plugin registry '{registry.name}'.")

    return render_template_file(
        TEMPLATES_DIRECTORY / 'plugins-ls.rst.j2',
        REGISTRIES=iter_plugin_registries(),
        find_intro=find_intro,
    )


def _ls(context: Context, how: str, content: Any) -> None:
    print = context.obj.logger.print  # noqa: A001

    if how in ('pretty', 'rest'):
        print(
            tmt.utils.rest.render_rst(content, context.obj.logger) if how == 'pretty' else content
        )

    elif how in ('json', 'yaml'):
        print(json.dumps(content) if how == 'json' else tmt.utils.dict_to_yaml(content))


@about.group(invoke_without_command=True, cls=CustomGroup)
@pass_context
def plugins(context: Context) -> None:
    """
    Show info about tmt plugins.
    """

    if context.invoked_subcommand is None:
        echo(context.get_help(), color=context.color)


@plugins.command(name='ls')
@option(
    '-h',
    '--how',
    choices=['json', 'yaml', 'rest', 'pretty'],
    default='pretty',
    help='Output format.',
)
@pass_context
def plugins_ls(context: Context, how: str) -> None:
    """
    List discovered tmt plugins.
    """

    if how in ('pretty', 'rest'):
        _ls(context, how, _render_plugins_list_rest())

    elif how in ('json', 'yaml'):
        _ls(
            context,
            how,
            {
                registry.name: list(registry.iter_plugin_ids())
                for registry in iter_plugin_registries()
            },
        )


@about.group(invoke_without_command=True, cls=CustomGroup)
@option('--hint', 'hint_ids', metavar='ID', multiple=True, help='Hint to display.')
@pass_context
def hints(context: Context, hint_ids: Any) -> None:
    """
    Show hints on various topics.
    """

    if hint_ids:
        for hint in tmt.utils.hints.get_hints(*hint_ids):
            context.obj.logger.print(hint.render(context.obj.logger))

    elif context.invoked_subcommand is None:
        echo(context.get_help(), color=context.color)


@hints.command(name='ls')
@option(
    '-h',
    '--how',
    choices=['json', 'yaml', 'rest', 'pretty'],
    default='pretty',
    help='Output format.',
)
@pass_context
def hints_ls(context: Context, how: str) -> None:
    """
    List discovered tmt hints.
    """

    if how in ('pretty', 'rest'):
        _ls(
            context,
            how,
            render_template_file(
                TEMPLATES_DIRECTORY / 'hints-ls.rst.j2',
                HINTS=tmt.utils.hints.HINTS,
            ),
        )

    elif how in ('json', 'yaml'):
        _ls(context, how, {hint_id: hint.text for hint_id, hint in tmt.utils.hints.HINTS.items()})
