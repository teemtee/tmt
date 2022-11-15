""" Command line interface for tmt tests command """

import os
from typing import Any, List, Optional

import click
import fmf
from click import echo
from fmf.utils import listed

import tmt
import tmt.convert
import tmt.identifier
import tmt.templates
import tmt.utils
from tmt.cli.click_group import CustomGroup
from tmt.cli.common_options import (filter_options, filter_options_long,
                                    fix_options, fmf_source_options,
                                    force_dry_options, verbosity_options)


@click.group(invoke_without_command=True, cls=CustomGroup)
@click.pass_context
@verbosity_options
def tests(context: click.core.Context, **kwargs: Any) -> None:
    """
    Manage tests (L1 metadata).

    Check available tests, inspect their metadata.
    Convert old metadata into the new fmf format.
    """

    # Show overview of available tests
    if context.invoked_subcommand is None:
        tmt.Test.overview(context.obj.tree)


@tests.command(name='ls')
@click.pass_context
@filter_options
@verbosity_options
def tests_ls(context: click.core.Context, **kwargs: Any) -> None:
    """
    List available tests.

    Regular expression can be used to filter tests by name.
    Use '.' to select tests under the current working directory.
    """
    tmt.Test._save_context(context)
    for test in context.obj.tree.tests():
        test.ls()


@tests.command(name='show')
@click.pass_context
@filter_options
@verbosity_options
def tests_show(context: click.core.Context, **kwargs: Any) -> None:
    """
    Show test details.

    Regular expression can be used to filter tests by name.
    Use '.' to select tests under the current working directory.
    """
    tmt.Test._save_context(context)
    for test in context.obj.tree.tests():
        test.show()
        echo()


@tests.command(name='lint')
@click.pass_context
@filter_options
@fmf_source_options
@fix_options
@verbosity_options
def tests_lint(context: click.core.Context, **kwargs: Any) -> None:
    """
    Check tests against the L1 metadata specification.

    Regular expression can be used to filter tests for linting.
    Use '.' to select tests under the current working directory.
    """
    # FIXME: Workaround https://github.com/pallets/click/pull/1840 for click 7
    context.params.update(**kwargs)
    tmt.Test._save_context(context)
    exit_code = 0
    for test in context.obj.tree.tests():
        if not test.lint():
            exit_code = 1
        echo()
    raise SystemExit(exit_code)


_test_templates = listed(tmt.templates.TEST, join='or')


@tests.command(name='create')
@click.pass_context
@click.argument('name')
@click.option(
    '-t', '--template', metavar='TEMPLATE',
    help='Test template ({}).'.format(_test_templates),
    prompt='Template ({})'.format(_test_templates))
@verbosity_options
@force_dry_options
def tests_create(
        context: click.core.Context,
        name: str,
        template: str,
        force: bool,
        **kwargs: Any) -> None:
    """
    Create a new test based on given template.

    Specify directory name or use '.' to create tests under the
    current working directory.
    """
    tmt.Test._save_context(context)
    tmt.Test.create(name, template, context.obj.tree.root, force)


@tests.command(name='import')
@click.pass_context
@click.argument('paths', nargs=-1, metavar='[PATH]...')
@click.option(
    '--nitrate / --no-nitrate', default=True,
    help='Import test metadata from Nitrate.')
@click.option(
    '--polarion / --no-polarion', default=False,
    help='Import test metadata from Polarion.')
@click.option(
    '--purpose / --no-purpose', default=True,
    help='Migrate description from PURPOSE file.')
@click.option(
    '--makefile / --no-makefile', default=True,
    help='Convert Beaker Makefile metadata.')
@click.option(
    '--restraint / --no-restraint', default=False,
    help='Convert restraint metadata file.')
@click.option(
    '--general / --no-general', default=True,
    help='Detect components from linked nitrate general plans '
         '(overrides Makefile/restraint component).')
@click.option(
    '--polarion-case-id',
    help='Polarion Test case ID to import data from.')
@click.option(
    '--link-polarion / --no-link-polarion', default=True,
    help='Add Polarion link to fmf testcase metadata.')
@click.option(
    '--type', 'types', metavar='TYPE', default=['multihost'], multiple=True,
    show_default=True,
    help="Convert selected types from Makefile into tags. "
         "Use 'all' to convert all detected types.")
@click.option(
    '--disabled', default=False, is_flag=True,
    help='Import disabled test cases from Nitrate as well.')
@click.option(
    '--manual', default=False, is_flag=True,
    help='Import manual test cases from Nitrate.')
@click.option(
    '--plan', metavar='PLAN', type=int,
    help='Identifier of test plan from which to import manual test cases.')
@click.option(
    '--case', metavar='CASE', type=int,
    help='Identifier of manual test case to be imported.')
@click.option(
    '--with-script', default=False, is_flag=True,
    help='Import manual cases with non-empty script field in Nitrate.')
@verbosity_options
@force_dry_options
def tests_import(
        context: click.core.Context,
        paths: List[str],
        makefile: bool,
        restraint: bool,
        general: bool,
        types: List[str],
        nitrate: bool,
        polarion: bool,
        polarion_case_id: Optional[str],
        link_polarion: bool,
        purpose: bool,
        disabled: bool,
        manual: bool,
        plan: int,
        case: int,
        with_script: bool,
        **kwargs: Any) -> None:
    """
    Import old test metadata into the new fmf format.

    Accepts one or more directories where old metadata are stored.
    By default all available sources and current directory are used.
    The following test metadata are converted for each source:

    \b
    makefile ..... summary, component, duration, require
    restraint .... name, description, entry_point, owner, max_time, repoRequires
    purpose ...... description
    nitrate ...... contact, component, tag, environment, relevancy, enabled
    polarion ..... summary, enabled, assignee, id, component, tag, description, link
    """
    tmt.Test._save_context(context)

    if manual:
        if not (case or plan):
            raise tmt.utils.GeneralError(
                "Option --case or --plan is mandatory when using --manual.")
        else:
            tmt.convert.read_manual(plan, case, disabled, with_script)
            return

    if not paths:
        paths = ['.']
    for path in paths:
        # Make sure we've got a real directory
        path = os.path.realpath(path)
        if not os.path.isdir(path):
            raise tmt.utils.GeneralError(
                "Path '{0}' is not a directory.".format(path))
        # Gather old metadata and store them as fmf
        common, individual = tmt.convert.read(
            path, makefile, restraint, nitrate, polarion, polarion_case_id, link_polarion,
            purpose, disabled, types, general)
        # Add path to common metadata if there are virtual test cases
        if individual:
            root = fmf.Tree(path).root
            common['path'] = os.path.join('/', os.path.relpath(path, root))
        # Store common metadata
        common_path = os.path.join(path, 'main.fmf')
        tmt.convert.write(common_path, common)
        # Store individual data (as virtual tests)
        for testcase in individual:
            testcase_path = os.path.join(
                path, str(testcase['extra-nitrate']) + '.fmf')
            tmt.convert.write(testcase_path, testcase)
        # Adjust runtest.sh content and permission if needed
        tmt.convert.adjust_runtest(os.path.join(path, 'runtest.sh'))


@tests.command(name='export')
@click.pass_context
@filter_options_long
@click.option(
    '-h', '--how', metavar='METHOD',
    help='Use specified method for export (nitrate or polarion).')
@click.option(
    '--nitrate', is_flag=True,
    help="Export test metadata to Nitrate, deprecated by '--how nitrate'.")
@click.option(
    '--project-id', help='Use specific Polarion project ID.')
@click.option(
    '--link-polarion / --no-link-polarion', default=True,
    help='Add Polarion link to fmf testcase metadata')
@click.option(
    '--bugzilla', is_flag=True,
    help="Link Nitrate case to Bugzilla specified in the 'link' attribute "
         "with the relation 'verifies'.")
@click.option(
    '--ignore-git-validation', is_flag=True,
    help="Ignore unpublished git changes and export to Nitrate. "
         "The case might not be able to be scheduled!")
@click.option(
    '--create', is_flag=True,
    help="Create test cases in nitrate if they don't exist.")
@click.option(
    '--general / --no-general', default=False,
    help="Link Nitrate case to component's General plan. Disabled by default. "
         "Note that this will unlink any previously connected general plans.")
@click.option(
    '--link-runs / --no-link-runs', default=False,
    help="Link Nitrate case to all open runs of descendant plans of "
         "General plan. Disabled by default. Implies --general option.")
@click.option(
    '--format', 'format_', default='yaml', show_default=True, metavar='FORMAT',
    help='Output format (yaml or dict).')
@click.option(
    '--fmf-id', is_flag=True,
    help='Show fmf identifiers instead of test metadata.')
@click.option(
    '--duplicate / --no-duplicate', default=False, show_default=True,
    help='Allow or prevent creating duplicates in Nitrate by searching for '
         'existing test cases with the same fmf identifier.')
@click.option(
    '-n', '--dry', is_flag=True,
    help="Run in dry mode. No changes, please.")
@click.option(
    '-d', '--debug', is_flag=True,
    help='Provide as much debugging details as possible.')
def tests_export(
        context: click.core.Context,
        format_: str,
        how: str,
        nitrate: bool,
        bugzilla: bool,
        **kwargs: Any) -> None:
    """
    Export test data into the desired format.

    Regular expression can be used to filter tests by name.
    Use '.' to select tests under the current working directory.
    """
    tmt.Test._save_context(context)
    if nitrate:
        context.obj.common.warn(
            "Option '--nitrate' is deprecated, please use '--how nitrate' instead.")
        how = 'nitrate'
    if bugzilla and not how:
        raise tmt.utils.GeneralError(
            "The --bugzilla option is supported only with --nitrate "
            "or --polarion for now.")

    if how == 'nitrate' or how == 'polarion':
        for test in context.obj.tree.tests():
            test.export(format_=tmt.base.ExportFormat(how))
    elif format_ in ['dict', 'yaml']:
        keys = None
        if kwargs.get('fmf_id'):
            keys = ['fmf-id']

        # Do not be fooled by explicit DICT, YAML export format is honored by
        # the `else` branch, and applied to `tests` list as a whole.
        tests = [test.export(format_=tmt.base.ExportFormat.DICT, keys=keys)
                 for test in context.obj.tree.tests()]
        if format_ == 'dict':
            echo(tests, nl=False)
        else:
            echo(tmt.utils.dict_to_yaml(tests), nl=False)
    else:
        raise tmt.utils.GeneralError(
            f"Invalid test export format '{format_}'.")


@tests.command(name="id")
@click.pass_context
@filter_options
@verbosity_options
@force_dry_options
def tests_id(context: click.core.Context, **kwargs: Any) -> None:
    """
    Generate a unique id for each selected test.

    A new UUID is generated for each test matching the provided
    filter and the value is stored to disk. Existing identifiers
    are kept intact.
    """
    tmt.Test._save_context(context)
    for test in context.obj.tree.tests():
        tmt.identifier.id_command(test.node, "test", dry=kwargs["dry"])
