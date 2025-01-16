""" ``tmt about`` implementation """

import json
import re
import textwrap
from typing import Any

from click import echo

import tmt.utils
import tmt.utils.rest
from tmt.cli import Context, CustomGroup, pass_context
from tmt.cli._root import main
from tmt.options import option
from tmt.plugins import PluginRegistry, iter_plugin_registries
from tmt.utils import GeneralError
from tmt.utils.templates import render_template


@main.group(invoke_without_command=True, cls=CustomGroup)
@pass_context
def about(context: Context) -> None:
    """ Show info about tmt itself """

    if context.invoked_subcommand is None:
        echo(context.get_help(), color=context.color)


def _render_plugins_list_rest() -> str:
    registry_intro_map: dict[str, str] = {
        r'export\.([a-z]+)': 'Export plugins for {{ MATCH.group(1).lower() }}',
        r'test.check': 'Test check plugins',
        r'test.framework': 'Test framework plugins',
        r'package_manager': 'Package manager plugins',
        r'step\.([a-z]+)': '{{ MATCH.group(1).capitalize() }} step plugins'
        }

    def find_intro(registry: PluginRegistry[Any]) -> str:
        for pattern, intro_template in registry_intro_map.items():
            match = re.match(pattern, registry.name)

            if match is None:
                continue

            return render_template(intro_template, MATCH=match)

        raise GeneralError(f"Unknown plugin registry '{registry.name}'.")

    template = textwrap.dedent("""
        {% for registry in REGISTRIES %}
            {% set intro = find_intro(registry) %}
        {{ intro }}
        {# {{ "-" * intro | length }} #}

            {% if registry %}
                {% for plugin_id in registry.iter_plugin_ids() %}
        * ``{{ plugin_id }}``
                {% endfor %}
            {% else %}
        No plugins discovered.
            {% endif %}

        ----

        {% endfor %}
    """)

    return render_template(template, REGISTRIES=iter_plugin_registries(), find_intro=find_intro)


@about.group(invoke_without_command=True, cls=CustomGroup)
@pass_context
def plugins(context: Context) -> None:
    if context.invoked_subcommand is None:
        echo(context.get_help(), color=context.color)


@plugins.command(name='ls')
@option(
    '-h', '--how',
    choices=['json', 'yaml', 'rest', 'pretty'],
    default='pretty',
    help='Output format.')
@pass_context
def plugins_ls(context: Context, how: str) -> None:
    print = context.obj.logger.print  # noqa: A001

    if how in ('pretty', 'rest'):
        text_output = _render_plugins_list_rest()

        print(
            tmt.utils.rest.render_rst(text_output, context.obj.logger)
            if how == 'pretty' else text_output)

    elif how in ('json', 'yaml'):
        structured_output = {
            registry.name: list(registry.iter_plugin_ids())
            for registry in iter_plugin_registries()
            }

        print(json.dumps(structured_output) if how ==
              'json' else tmt.utils.dict_to_yaml(structured_output))
