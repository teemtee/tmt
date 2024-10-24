#!/usr/bin/env python3

import dataclasses
import enum
import sys
import textwrap
from typing import Any

import tmt.checks
import tmt.log
import tmt.plugins
import tmt.steps
import tmt.steps.discover
import tmt.steps.execute
import tmt.steps.finish
import tmt.steps.prepare
import tmt.steps.provision
import tmt.steps.report
import tmt.utils
from tmt.utils import ContainerClass, Path
from tmt.utils.templates import render_template_file

REVIEWED_PLUGINS: tuple[str, ...] = (
    'prepare/ansible',
    'test-checks/avc',
    'test-checks/dmesg'
    )


HELP = textwrap.dedent("""
Usage: generate-plugins.py <STEP-NAME> <TEMPLATE-PATH> <OUTPUT-PATH>

Generate pages for step plugins sources.
""").strip()


def _is_ignored(
        container: ContainerClass,
        field: dataclasses.Field[Any],
        metadata: tmt.utils.FieldMetadata) -> bool:
    """ Check whether a given field is to be ignored in documentation """

    if field.name in ('how', '_OPTIONLESS_FIELDS'):
        return True

    if metadata.internal is True:
        return True

    return hasattr(container, '_OPTIONLESS_FIELDS') and field.name in container._OPTIONLESS_FIELDS


def _is_inherited(
        container: ContainerClass,
        field: dataclasses.Field[Any],
        metadata: tmt.utils.FieldMetadata) -> bool:
    """ Check whether a given field is inherited from step data base class """

    # TODO: for now, it's a list, but inspecting the actual tree of classes
    # would be more generic. It's good enough for now.
    return field.name in ('name', 'where', 'order', 'summary', 'enabled', 'result')


def container_ignored_fields(container: ContainerClass) -> list[str]:
    """ Collect container field names that are never displayed """

    field_names: list[str] = []

    for field in tmt.utils.container_fields(container):
        _, _, _, _, metadata = tmt.utils.container_field(container, field.name)

        if _is_ignored(container, field, metadata):
            field_names.append(field.name)

    return field_names


def container_inherited_fields(container: ContainerClass) -> list[str]:
    """ Collect container field names that are inherited from step data base class """

    field_names: list[str] = []

    for field in tmt.utils.container_fields(container):
        _, _, _, _, metadata = tmt.utils.container_field(container, field.name)

        if _is_inherited(container, field, metadata):
            field_names.append(field.name)

    return field_names


def container_intrinsic_fields(container: ContainerClass) -> list[str]:
    """ Collect container fields specific for the given step data """

    field_names: list[str] = []

    for field in tmt.utils.container_fields(container):
        _, _, _, _, metadata = tmt.utils.container_field(container, field.name)

        if _is_ignored(container, field, metadata):
            continue

        if _is_inherited(container, field, metadata):
            continue

        field_names.append(field.name)

    return field_names


def is_enum(value: Any) -> bool:
    """ Find out whether a given value is an enum member """

    return isinstance(value, enum.Enum)


def _create_step_plugin_iterator(registry: tmt.plugins.PluginRegistry[tmt.steps.Method]):
    """ Create iterator over plugins of a given registry """

    def plugin_iterator():
        for plugin_id in registry.iter_plugin_ids():
            plugin = registry.get_plugin(plugin_id).class_

            yield plugin_id, plugin, plugin._data_class

    return plugin_iterator


def _create_test_check_plugin_iterator(registry: tmt.plugins.PluginRegistry[tmt.steps.Method]):
    """ Create iterator over plugins of a test check registry """

    def plugin_iterator():
        for plugin_id in registry.iter_plugin_ids():
            plugin = registry.get_plugin(plugin_id)

            yield plugin_id, plugin, plugin._check_class

    return plugin_iterator


def main() -> None:
    if len(sys.argv) != 4:
        print(HELP)

        sys.exit(1)

    step_name = sys.argv[1]
    template_filepath = Path(sys.argv[2])
    output_filepath = Path(sys.argv[3])

    # We will need a logger...
    logger = tmt.log.Logger.create()
    logger.add_console_handler()

    # ... explore available plugins...
    tmt.plugins.explore(logger)

    if step_name == 'discover':
        plugin_generator = _create_step_plugin_iterator(
            tmt.steps.discover.DiscoverPlugin._supported_methods)

    elif step_name == 'execute':
        plugin_generator = _create_step_plugin_iterator(
            tmt.steps.execute.ExecutePlugin._supported_methods)

    elif step_name == 'finish':
        plugin_generator = _create_step_plugin_iterator(
            tmt.steps.finish.FinishPlugin._supported_methods)

    elif step_name == 'prepare':
        plugin_generator = _create_step_plugin_iterator(
            tmt.steps.prepare.PreparePlugin._supported_methods)

    elif step_name == 'provision':
        plugin_generator = _create_step_plugin_iterator(
            tmt.steps.provision.ProvisionPlugin._supported_methods)

    elif step_name == 'report':
        plugin_generator = _create_step_plugin_iterator(
            tmt.steps.report.ReportPlugin._supported_methods)

    elif step_name == 'test-checks':
        plugin_generator = _create_test_check_plugin_iterator(tmt.checks._CHECK_PLUGIN_REGISTRY)

    else:
        raise tmt.utils.GeneralError(f"Unhandled step name '{step_name}'.")

    # ... and render the template.
    output_filepath.write_text(render_template_file(
        template_filepath,
        LOGGER=logger,
        STEP=step_name,
        PLUGINS=plugin_generator,
        REVIEWED_PLUGINS=REVIEWED_PLUGINS,
        is_enum=is_enum,
        container_fields=tmt.utils.container_fields,
        container_field=tmt.utils.container_field,
        container_ignored_fields=container_ignored_fields,
        container_inherited_fields=container_inherited_fields,
        container_intrinsic_fields=container_intrinsic_fields))


if __name__ == '__main__':
    main()
