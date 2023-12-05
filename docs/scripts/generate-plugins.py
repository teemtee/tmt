#!/usr/bin/env python3

import sys
import textwrap

import tmt.log
import tmt.plugins
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
        STEP=step_name,
        REGISTRY=registry,
        container_fields=tmt.utils.container_fields,
        container_field=tmt.utils.container_field))


if __name__ == '__main__':
    main()
