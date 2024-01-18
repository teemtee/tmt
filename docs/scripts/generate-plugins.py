#!/usr/bin/env python3

import dataclasses
import sys
import textwrap
from typing import Any

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
from tmt.utils import Path, render_template_file

HELP = textwrap.dedent("""
Usage: generate-plugins.py <STEP-NAME> <TEMPLATE-PATH> <OUTPUT-PATH>

Generate pages for step plugins sources.
""").strip()


def _is_ignored(
        step_data: type[tmt.steps.StepData],
        field: dataclasses.Field[Any],
        metadata: tmt.utils.FieldMetadata) -> bool:
    if field.name in ('how', '_OPTIONLESS_FIELDS'):
        return True

    if metadata.internal is True:
        return True

    if hasattr(step_data, '_OPTIONLESS_FIELDS') and field.name in step_data._OPTIONLESS_FIELDS:
        return True

    return False


def _is_inherited(
        step_data: type[tmt.steps.StepData],
        field: dataclasses.Field[Any],
        metadata: tmt.utils.FieldMetadata) -> bool:

    return field.name in ('name', 'where', 'order', 'summary')


def container_ignored_fields(step_data: type[tmt.steps.StepData]) -> list[str]:
    """ Collect container field names that are never displayed """

    field_names: list[str] = []

    for field in tmt.utils.container_fields(step_data):
        _, _, _, metadata = tmt.utils.container_field(step_data, field.name)

        if _is_ignored(step_data, field, metadata):
            field_names.append(field.name)

    return field_names


def container_inherited_fields(step_data: type[tmt.steps.StepData]) -> list[str]:
    """ Collect container field names that are inherited from parent """

    field_names: list[str] = []

    for field in tmt.utils.container_fields(step_data):
        _, _, _, metadata = tmt.utils.container_field(step_data, field.name)

        if _is_inherited(step_data, field, metadata):
            field_names.append(field.name)

    return field_names


def container_intrinsic_fields(step_data: type[tmt.steps.StepData]) -> list[str]:
    """ Collect container fields specific for the given step data """

    field_names: list[str] = []

    for field in tmt.utils.container_fields(step_data):
        _, _, _, metadata = tmt.utils.container_field(step_data, field.name)

        if _is_ignored(step_data, field, metadata):
            continue

        if _is_inherited(step_data, field, metadata):
            continue

        field_names.append(field.name)

    return field_names


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
        registry = tmt.steps.discover.DiscoverPlugin._supported_methods

    elif step_name == 'execute':
        registry = tmt.steps.execute.ExecutePlugin._supported_methods

    elif step_name == 'finish':
        registry = tmt.steps.finish.FinishPlugin._supported_methods

    elif step_name == 'prepare':
        registry = tmt.steps.prepare.PreparePlugin._supported_methods

    elif step_name == 'provision':
        registry = tmt.steps.provision.ProvisionPlugin._supported_methods

    elif step_name == 'report':
        registry = tmt.steps.report.ReportPlugin._supported_methods

    else:
        raise tmt.utils.GeneralError(f"Unhandled step name '{step_name}'.")

    # ... and render the template.
    output_filepath.write_text(render_template_file(
        template_filepath,
        LOGGER=logger,
        STEP=step_name,
        REGISTRY=registry,
        container_fields=tmt.utils.container_fields,
        container_field=tmt.utils.container_field,
        container_ignored_fields=container_ignored_fields,
        container_inherited_fields=container_inherited_fields,
        container_intrinsic_fields=container_intrinsic_fields))


if __name__ == '__main__':
    main()
