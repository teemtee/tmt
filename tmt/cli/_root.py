"""
Main top-level command implementations.

.. note::

    We are currently refactoring :py:mod:`tmt.cli` into smaller modules.
    As of now, this module contains vast majority of tmt commands, but
    those will be continuously extracted until only the top-level
    command remains.
"""

from typing import TYPE_CHECKING, Any, Optional

import click
import fmf
import fmf.utils
from click import echo, style

import tmt
import tmt.base
import tmt.cli
import tmt.config
import tmt.convert
import tmt.export
import tmt.identifier
import tmt.log
import tmt.options
import tmt.plugins
import tmt.steps
import tmt.templates
import tmt.trying
import tmt.utils
import tmt.utils.jira
import tmt.utils.rest
from tmt.cli import CliInvocation, Context, ContextObject, CustomGroup, pass_context
from tmt.options import Deprecated, create_options_decorator, option
from tmt.utils import Command, Path, effective_workdir_root

if TYPE_CHECKING:
    import tmt.steps.discover
    import tmt.steps.execute
    import tmt.steps.finish
    import tmt.steps.prepare
    import tmt.steps.provision
    import tmt.steps.report


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#  Common Options
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
verbosity_options = create_options_decorator(tmt.options.VERBOSITY_OPTIONS)
dry_options = create_options_decorator(tmt.options.DRY_OPTIONS)
force_dry_options = create_options_decorator(tmt.options.FORCE_DRY_OPTIONS)
again_option = create_options_decorator(tmt.options.AGAIN_OPTION)
fix_options = create_options_decorator(tmt.options.FIX_OPTIONS)
feeling_safe_option = create_options_decorator(tmt.options.FEELING_SAFE_OPTION)
workdir_root_options = create_options_decorator(tmt.options.WORKDIR_ROOT_OPTIONS)
filtering_options = create_options_decorator(tmt.options.FILTERING_OPTIONS)
filtering_options_long = create_options_decorator(tmt.options.FILTERING_OPTIONS_LONG)
filter_option = create_options_decorator(tmt.options.FILTER_OPTION)
fmf_source_options = create_options_decorator(tmt.options.FMF_SOURCE_OPTIONS)
story_flags_filter_options = create_options_decorator(tmt.options.STORY_FLAGS_FILTER_OPTIONS)
remote_plan_options = create_options_decorator(tmt.options.REMOTE_PLAN_OPTIONS)
lint_options = create_options_decorator(tmt.options.LINT_OPTIONS)
environment_options = create_options_decorator(tmt.options.ENVIRONMENT_OPTIONS)


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#  Main
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
@click.group(invoke_without_command=True, cls=CustomGroup)
@pass_context
@option(
    '-r', '--root', metavar='PATH', show_default=True, default='.',
    help="Path to the metadata tree root, '.' used by default.")
@option(
    '-c', '--context', metavar='DATA', multiple=True,
    help="""
         Set the fmf context. Use KEY=VAL or KEY=VAL1,VAL2... format to define individual
         dimensions or the @FILE notation to load data from provided yaml file. Can be specified
         multiple times.
         """)
@verbosity_options
@feeling_safe_option
@option(
    '--show-time',
    is_flag=True,
    help='If set, logging messages on the terminal would contain timestamps.')
@option(
    '--version', is_flag=True,
    help='Show tmt version and commit hash.')
@option(
    '--no-color', is_flag=True, default=False,
    help='Forces tmt to not use any colors in the output or logging.'
    )
@option(
    '--force-color', is_flag=True, default=False,
    help='Forces tmt to use colors in the output and logging.'
    )
@option(
    '--pre-check', is_flag=True, default=False, hidden=True,
    help='Run pre-checks on the git root. (Used by pre-commit wrapper).'
    )
def main(
        click_contex: Context,
        root: str,
        context: list[str],
        no_color: bool,
        force_color: bool,
        show_time: bool,
        pre_check: bool,
        **kwargs: Any) -> None:
    """ Test Management Tool """

    # Let Click know about the output width - this affects mostly --help output.
    click_contex.max_content_width = tmt.utils.OUTPUT_WIDTH

    # Show current tmt version and exit
    if kwargs.get('version'):
        print(f"tmt version: {tmt.__version__}")
        raise SystemExit(0)

    apply_colors_output, apply_colors_logging = tmt.log.decide_colorization(no_color, force_color)

    logger = tmt.log.Logger.create(
        apply_colors_output=apply_colors_output,
        apply_colors_logging=apply_colors_logging,
        **kwargs)
    logger.add_console_handler(show_timestamps=show_time)

    # Propagate color setting to Click as well.
    click_contex.color = apply_colors_output

    # ignore[reportConstantRedefinition]: it looks like a constant, but
    # this redefinition is expected and on purpose. `EXCEPTION_LOGGER`
    # starts with the bootstrap logger, but now we constructed a better
    # one, and we need to switch.
    #
    # ignore[unused-ignore]: mypy does not report this issue, and the
    # ignore fools mypy into reporting the waiver as unused.
    tmt.cli.EXCEPTION_LOGGER = logger  # type: ignore[reportConstantRedefinition,unused-ignore]

    # Save click context and fmf context for future use
    tmt.utils.Common.store_cli_invocation(click_contex)

    # Run pre-checks
    if pre_check:
        git_command = tmt.utils.Command('git', 'rev-parse', '--show-toplevel')
        git_root = git_command.run(cwd=None, logger=logger).stdout
        if not git_root:
            raise tmt.utils.RunError("git rev-parse did not produce a path", git_command, 0)
        git_root = git_root.strip()
        git_command = tmt.utils.Command(
            'git', 'ls-files', '--error-unmatch', f"{git_root}/{root}/.fmf/version"
            )
        git_command.run(cwd=None, logger=logger)

    # Initialize metadata tree (from given path or current directory)
    tree = tmt.Tree(logger=logger, path=Path(root))

    # TODO: context object details need checks
    click_contex.obj = ContextObject(
        cli_context=click_contex,
        logger=logger,
        common=tmt.utils.Common(logger=logger),
        fmf_context=tmt.utils.FmfContext.from_spec('cli', context, logger),
        steps=set(),
        tree=tree
        )

    # Show overview of available tests, plans and stories
    if click_contex.invoked_subcommand is None:
        tmt.Test.overview(tree)
        tmt.Plan.overview(tree)
        tmt.Story.overview(tree)


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#  Run
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

@main.group(chain=True, invoke_without_command=True, cls=CustomGroup)
@pass_context
@option(
    '-i', '--id', 'id_', help='Run id (name or directory path).', metavar="ID")
@option(
    '-l', '--last', help='Execute the last run once again.', is_flag=True)
@option(
    '-r', '--rm', '--remove', 'remove', is_flag=True,
    help='Remove the workdir when test run is finished.')
@option(
    '-k', '--keep', is_flag=True,
    help="""
         Keep all files in the run workdir after testing is done (skip pruning during the finish
         step).
         """)
@option(
    '--scratch', is_flag=True,
    help='Remove the run workdir before executing to start from scratch.')
@option(
    '--follow', is_flag=True,
    help='Output the logfile as it grows.')
@option(
    '-a', '--all', help='Run all steps, customize some.', is_flag=True)
@option(
    '-u', '--until', choices=tmt.steps.STEPS,
    help='Enable given step and all preceding steps.')
@option(
    '-s', '--since', choices=tmt.steps.STEPS,
    help='Enable given step and all following steps.')
@option(
    '-A', '--after', choices=tmt.steps.STEPS,
    help='Enable all steps after the given one.')
@option(
    '-B', '--before', choices=tmt.steps.STEPS,
    help='Enable all steps before the given one.')
@option(
    '-S', '--skip', choices=tmt.steps.STEPS,
    help='Skip given step(s) during test run execution.', multiple=True)
@option(
    '--on-plan-error',
    choices=['quit', 'continue'],
    default='quit',
    help="""
         What to do when plan fails to finish. Quit by default, or continue with the next plan.
         """)
@environment_options
@workdir_root_options
@verbosity_options
@force_dry_options
@again_option
def run(context: Context, id_: Optional[str], _workdir_root: Optional[str], **kwargs: Any) -> None:
    """ Run test steps. """
    # Initialize
    logger = context.obj.logger.descend(logger_name='run', extra_shift=0)
    logger.apply_verbosity_options(**kwargs)

    workdir_root = Path(_workdir_root) if _workdir_root is not None else None

    run = tmt.Run(
        id_=Path(id_) if id_ is not None else None,
        tree=context.obj.tree,
        cli_invocation=CliInvocation.from_context(context),
        workdir_root=effective_workdir_root(workdir_root),
        logger=logger
        )
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
@pass_context
@option(
    '-n', '--name', 'names', metavar='[REGEXP|.]', multiple=True,
    help="Regular expression to match plan name or '.' for current directory.")
@filter_option
@option(
    '-c', '--condition', 'conditions', metavar="EXPR", multiple=True,
    help="Use arbitrary Python expression for filtering.")
@option(
    '--link', 'links', metavar="RELATION:TARGET", multiple=True,
    help="""
         Filter by linked objects (regular expressions are supported for both relation and target).
         """)
@option(
    '--default', is_flag=True,
    help="Use default plans even if others are available.")
@verbosity_options
def run_plans(context: Context, **kwargs: Any) -> None:
    """
    Select plans which should be executed.

    Regular expression can be used to filter plans by name.
    Use '.' to select plans under the current working directory.
    """
    tmt.base.Plan.store_cli_invocation(context)


@run.command(name='tests')
@pass_context
@option(
    '-n', '--name', 'names', metavar='[REGEXP|.]', multiple=True,
    help="Regular expression to match test name or '.' for current directory.")
@filter_option
@option(
    '-c', '--condition', 'conditions', metavar="EXPR", multiple=True,
    help="Use arbitrary Python expression for filtering.")
@option(
    '--link', 'links', metavar="RELATION:TARGET", multiple=True,
    help="""
         Filter by linked objects (regular expressions are supported for both relation and target).
         """)
@option(
    '--failed-only', is_flag=True, default=False,
    help="""
         Select only failed tests from a previous run.
         Used when rerunning existing runs and requires either --id or --last option.
         """)
@verbosity_options
def run_tests(context: Context, **kwargs: Any) -> None:
    """
    Select tests which should be executed.

    Regular expression can be used to filter tests by name.
    Use '.' to select tests under the current working directory.
    """
    tmt.base.Test.store_cli_invocation(context)


# TODO: commands is unknown, needs revisit
# ignore[arg-type]: click code expects click.Context, but we use our own type for better type
# inference. See Context and ContextObjects above.
@run.result_callback()  # type: ignore[arg-type]
@pass_context
def finito(
        click_context: Context,
        commands: Any,
        *args: Any,
        **kwargs: Any) -> None:
    """ Run tests if run defined """
    if click_context.obj.run:
        click_context.obj.run.go()


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#  Test
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

# ignore[arg-type]: click code expects click.Context, but we use our own type for better type
# inference. See Context and ContextObjects above.
@main.group(invoke_without_command=True, cls=CustomGroup)  # type: ignore[arg-type]
@pass_context
@verbosity_options
def tests(context: Context, **kwargs: Any) -> None:
    """
    Manage tests (L1 metadata).

    Check available tests, inspect their metadata.
    Convert old metadata into the new fmf format.
    """

    context.obj.logger = context.obj.logger.clone() \
        .apply_verbosity_options(**kwargs)

    # Show overview of available tests
    if context.invoked_subcommand is None:
        tmt.Test.overview(context.obj.tree)


# ignore[arg-type]: click code expects click.Context, but we use our own type for better type
# inference. See Context and ContextObjects above.
@tests.command(name='ls')  # type: ignore[arg-type]
@pass_context
@filtering_options
@verbosity_options
def tests_ls(context: Context, **kwargs: Any) -> None:
    """
    List available tests.

    Regular expression can be used to filter tests by name.
    Use '.' to select tests under the current working directory.
    """
    tmt.Test.store_cli_invocation(context)
    for test in context.obj.tree.tests():
        test.ls()


# ignore[arg-type]: click code expects click.Context, but we use our own type for better type
# inference. See Context and ContextObjects above.
@tests.command(name='show')  # type: ignore[arg-type]
@pass_context
@filtering_options
@verbosity_options
def tests_show(context: Context, **kwargs: Any) -> None:
    """
    Show test details.

    Regular expression can be used to filter tests by name.
    Use '.' to select tests under the current working directory.
    """
    tmt.Test.store_cli_invocation(context)

    logger = context.obj.logger.clone() \
        .apply_verbosity_options(**kwargs)

    for test in context.obj.tree.tests(logger=logger):
        test.show()
        echo()


_script_templates = fmf.utils.listed(
    tmt.templates.MANAGER.templates['script'], join='or')

_metadata_templates = fmf.utils.listed(
    tmt.templates.MANAGER.templates['test'], join='or')


@tests.command(name='create')
@pass_context
@click.argument('names', nargs=-1, metavar='[NAME]...')
@option(
    '-t', '--template', metavar='TEMPLATE',
    help=f'Test metadata template ({_metadata_templates}).',
    prompt=f'Test template ({_metadata_templates})')
@option(
    '-s', '--script', metavar='TEMPLATE',
    help=f'Test script template ({_script_templates}).')
@option(
    '--link', metavar='[RELATION:]TARGET', multiple=True,
    help='Link created test to the relevant issues.')
@verbosity_options
@force_dry_options
def tests_create(
        context: Context,
        names: list[str],
        template: str,
        script: Optional[str],
        force: bool,
        **kwargs: Any) -> None:
    """
    Create a new test based on given template.

    Specify directory name or use '.' to create tests under the
    current working directory.
    """
    assert context.obj.tree.root is not None  # narrow type
    tmt.Test.store_cli_invocation(context)
    tmt.Test.create(
        names=names,
        template=template,
        path=context.obj.tree.root,
        script=script,
        force=force,
        logger=context.obj.logger)


@tests.command(name='import')
@pass_context
@click.argument('paths', nargs=-1, metavar='[PATH]...')
@option(
    '--nitrate / --no-nitrate', default=True, show_default=True, is_flag=True,
    help='Import test metadata from Nitrate.')
@option(
    '--polarion / --no-polarion', default=False, show_default=True, is_flag=True,
    help='Import test metadata from Polarion.')
@option(
    '--purpose / --no-purpose', default=True, show_default=True, is_flag=True,
    help='Migrate description from PURPOSE file.')
@option(
    '--makefile / --no-makefile', default=True, show_default=True, is_flag=True,
    help='Convert Beaker Makefile metadata.')
@option(
    '--restraint / --no-restraint', default=False, show_default=True, is_flag=True,
    help='Convert restraint metadata file.')
@option(
    '--general / --no-general', default=True, is_flag=True,
    help="""
         Detect components from linked nitrate general plans (overrides Makefile/restraint
         component).
         """)
@option(
    '--polarion-case-id', multiple=True,
    help="""
         Polarion Test case ID(s) to import data from. Can be provided multiple times. Can provide
         also test case name like: TEST-123:test_name
         """)
@option(
    '--link-polarion / --no-link-polarion', default=False, show_default=True, is_flag=True,
    help='Add Polarion link to fmf testcase metadata.')
@option(
    '--type', 'types', metavar='TYPE', default=['multihost'], multiple=True,
    show_default=True,
    help="""
         Convert selected types from Makefile into tags. Use 'all' to convert all detected types.
         """)
@option(
    '--disabled', default=False, is_flag=True,
    help='Import disabled test cases from Nitrate as well.')
@option(
    '--manual', default=False, is_flag=True,
    help='Import manual test cases from Nitrate.')
@option(
    '--plan', metavar='PLAN', type=int,
    help='Identifier of test plan from which to import manual test cases.')
@option(
    '--case', metavar='CASE', type=int,
    help='Identifier of manual test case to be imported.')
@option(
    '--with-script', default=False, is_flag=True,
    help='Import manual cases with non-empty script field in Nitrate.')
@verbosity_options
@force_dry_options
def tests_import(
        context: Context,
        paths: list[str],
        makefile: bool,
        restraint: bool,
        general: bool,
        types: list[str],
        nitrate: bool,
        polarion: bool,
        polarion_case_id: list[str],
        link_polarion: bool,
        purpose: bool,
        disabled: bool,
        manual: bool,
        plan: int,
        case: int,
        with_script: bool,
        dry: bool,
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
    tmt.Test.store_cli_invocation(context)

    if manual:
        if not (case or plan):
            raise tmt.utils.GeneralError(
                "Option --case or --plan is mandatory when using --manual.")
        tmt.convert.read_manual(plan, case, disabled, with_script, context.obj.logger)
        return

    if not paths:
        paths = ['.']
    for _path in paths:
        path = Path(_path)
        # Make sure we've got a real directory
        path = path.resolve()
        if not path.is_dir():
            raise tmt.utils.GeneralError(
                f"Path '{path}' is not a directory.")
        # Gather old metadata and store them as fmf
        common, individual = tmt.convert.read(
            path, makefile, restraint, nitrate, polarion, polarion_case_id, link_polarion,
            purpose, disabled, types, general, dry, context.obj.logger)
        # Add path to common metadata if there are virtual test cases
        if individual:
            # TODO: fmf is not annotated yet, fmf.Tree.root is seen by pyright as possibly
            # `Unknown` type, therefore we need to help a bit.
            node = fmf.Tree(str(path))
            assert isinstance(node.root, str)  # narrow type
            root = Path(node.root)
            common['path'] = str(Path('/') / path.relative_to(root))
        # Store common metadata
        file_name = common.get('filename', 'main.fmf')
        common_path = path / file_name
        if not dry:
            tmt.convert.write(common_path, common)
        else:
            echo(style(f"Metadata would be stored into '{common_path}'.", fg='magenta'))
        # Store individual data (as virtual tests)
        for testcase in individual:
            if nitrate and testcase.get('extra-nitrate'):
                testcase_path = path / f'{testcase["extra-nitrate"]}.fmf'
            else:
                file_name = testcase.get('filename')
                if not file_name:
                    raise tmt.utils.ConvertError(
                        'Filename was not found, please set one with --polarion-case-id.')
                testcase_path = path / file_name
            if not dry:
                tmt.convert.write(testcase_path, testcase)
            else:
                echo(style(f"Metadata would be stored into '{testcase_path}'.", fg='magenta'))
        # Adjust runtest.sh content and permission if needed
        if not dry:
            tmt.convert.adjust_runtest(path / 'runtest.sh')


_test_export_formats = list(tmt.Test.get_export_plugin_registry().iter_plugin_ids())
_test_export_default = 'yaml'


@tests.command(name='export')
@pass_context
@filtering_options_long
@option(
    '-h', '--how', default=_test_export_default, show_default=True,
    help='Output format.',
    choices=_test_export_formats)
@option(
    '--format', default=_test_export_default, show_default=True,
    help='Output format.',
    deprecated=Deprecated('1.21', hint='use --how instead'),
    choices=_test_export_formats)
@option(
    '--nitrate', is_flag=True,
    help="Export test metadata to Nitrate.",
    deprecated=Deprecated('1.21', hint="use '--how nitrate' instead"))
@option(
    '--project-id', help='Use specific Polarion project ID.')
@option(
    '--link-polarion / --no-link-polarion', default=False, is_flag=True,
    help='Add Polarion link to fmf testcase metadata')
@option(
    '--bugzilla', is_flag=True,
    help="""
         Link Nitrate case to Bugzilla specified in the 'link' attribute with the relation
         'verifies'.
         """)
@option(
    '--ignore-git-validation', is_flag=True,
    help="""
         Ignore unpublished git changes and export to Nitrate. The case might not be able to be
         scheduled!
         """)
@option(
    '--append-summary / --no-append-summary', default=False, is_flag=True,
    help="""
         Include test summary in the Nitrate/Polarion test case summary as well. By default, only
         the repository name and test name are used.
         """)
@option(
    '--create', is_flag=True,
    help="Create test cases in nitrate if they don't exist.")
@option(
    '--general / --no-general', default=False, is_flag=True,
    help="""
         Link Nitrate case to component's General plan. Disabled by default. Note that this will
         unlink any previously connected general plans.
         """)
@option(
    '--link-runs / --no-link-runs', default=False, is_flag=True,
    help="""
         Link Nitrate case to all open runs of descendant plans of General plan. Disabled by
         default. Implies --general option.
         """)
@option(
    '--fmf-id', is_flag=True,
    help='Show fmf identifiers instead of test metadata.')
@option(
    '--duplicate / --no-duplicate', default=False, show_default=True, is_flag=True,
    help="""
         Allow or prevent creating duplicates in Nitrate by searching for existing test cases with
         the same fmf identifier.
         """)
@option(
    '-n', '--dry', is_flag=True,
    help="Run in dry mode. No changes, please.")
@option(
    '-d', '--debug', is_flag=True,
    help='Provide as much debugging details as possible.')
# TODO: move to `template` export plugin options
@option(
    '--template', metavar='PATH',
    help="Path to a template to use for rendering the export. Used with '--how=template' only."
    )
def tests_export(
        context: Context,
        format: str,
        how: str,
        nitrate: bool,
        bugzilla: bool,
        template: Optional[str],
        **kwargs: Any) -> None:
    """
    Export test data into the desired format.

    Regular expression can be used to filter tests by name.
    Use '.' to select tests under the current working directory.
    """
    tmt.Test.store_cli_invocation(context)

    if nitrate:
        context.obj.common.warn(
            "Option '--nitrate' is deprecated, please use '--how nitrate' instead.")
        how = 'nitrate'

    if format != _test_export_default:
        context.obj.common.warn("Option '--format' is deprecated, please use '--how' instead.")

        how = format

    # TODO: move this "requires bugzilla" flag to export plugin level.
    if bugzilla and how not in ('nitrate', 'polarion'):
        raise tmt.utils.GeneralError(
            "The --bugzilla option is supported only with --nitrate "
            "or --polarion for now.")

    if kwargs.get('fmf_id'):
        echo(tmt.base.FmfId.export_collection(
            collection=[test.fmf_id for test in context.obj.tree.tests()],
            format=how,
            template=Path(template) if template else None
            ))

    else:
        echo(tmt.Test.export_collection(
            collection=context.obj.tree.tests(),
            format=how,
            template=Path(template) if template else None
            ))


# ignore[arg-type]: click code expects click.Context, but we use our own type for better type
# inference. See Context and ContextObjects above.
@tests.command(name="id")  # type: ignore[arg-type]
@pass_context
@filtering_options
@verbosity_options
@force_dry_options
def tests_id(context: Context, **kwargs: Any) -> None:
    """
    Generate a unique id for each selected test.

    A new UUID is generated for each test matching the provided
    filter and the value is stored to disk. Existing identifiers
    are kept intact.
    """
    tmt.Test.store_cli_invocation(context)
    for test in context.obj.tree.tests():
        tmt.identifier.id_command(context, test.node, "test", dry=kwargs["dry"])


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#  Plan
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

# ignore[arg-type]: click code expects click.Context, but we use our own type for better type
# inference. See Context and ContextObjects above.
@main.group(invoke_without_command=True, cls=CustomGroup)  # type: ignore[arg-type]
@pass_context
@verbosity_options
@remote_plan_options
def plans(context: Context, **kwargs: Any) -> None:
    """
    Manage test plans (L2 metadata).

    \b
    Search for available plans.
    Explore detailed test step configuration.
    """

    context.obj.logger = context.obj.logger.clone() \
        .apply_verbosity_options(**kwargs)

    # Show overview of available plans
    if context.invoked_subcommand is None:
        tmt.Plan.overview(context.obj.tree)


# ignore[arg-type]: click code expects click.Context, but we use our own type for better type
# inference. See Context and ContextObjects above.
@plans.command(name='ls')  # type: ignore[arg-type]
@pass_context
@filtering_options
@verbosity_options
@remote_plan_options
def plans_ls(context: Context, **kwargs: Any) -> None:
    """
    List available plans.

    Regular expression can be used to filter plans by name.
    Use '.' to select plans under the current working directory.
    """
    tmt.Plan.store_cli_invocation(context)
    for plan in context.obj.tree.plans():
        plan.ls()


# ignore[arg-type]: click code expects click.Context, but we use our own type for better type
# inference. See Context and ContextObjects above.
@plans.command(name='show')  # type: ignore[arg-type]
@pass_context
@filtering_options
@environment_options
@verbosity_options
@remote_plan_options
def plans_show(context: Context, **kwargs: Any) -> None:
    """
    Show plan details.

    Regular expression can be used to filter plans by name.
    Use '.' to select plans under the current working directory.
    """
    tmt.Plan.store_cli_invocation(context)

    logger = context.obj.logger.clone() \
        .apply_verbosity_options(**kwargs)

    for plan in context.obj.tree.plans(logger=logger):
        plan.show()
        echo()


_plan_templates = fmf.utils.listed(tmt.templates.MANAGER.templates['plan'], join='or')


@plans.command(name='create')
@pass_context
@click.argument('names', nargs=-1, metavar='[NAME]...')
@option(
    '-t', '--template', metavar='TEMPLATE',
    help=f'Plan template ({_plan_templates}).',
    prompt=f'Template ({_plan_templates})')
@option(
    '--discover', metavar='YAML', multiple=True,
    help='Discover phase content in yaml format.')
@option(
    '--provision', metavar='YAML', multiple=True,
    help='Provision phase content in yaml format.')
@option(
    '--prepare', metavar='YAML', multiple=True,
    help='Prepare phase content in yaml format.')
@option(
    '--execute', metavar='YAML', multiple=True,
    help='Execute phase content in yaml format.')
@option(
    '--report', metavar='YAML', multiple=True,
    help='Report phase content in yaml format.')
@option(
    '--finish', metavar='YAML', multiple=True,
    help='Finish phase content in yaml format.')
@option(
    '--link', metavar='[RELATION:]TARGET', multiple=True,
    help='Link created plan to the relevant issues.')
@verbosity_options
@force_dry_options
def plans_create(
        context: Context,
        names: list[str],
        template: str,
        force: bool,
        **kwargs: Any) -> None:
    """ Create a new plan based on given template. """
    assert context.obj.tree.root is not None  # narrow type
    tmt.Plan.store_cli_invocation(context)
    tmt.Plan.create(
        names=names,
        template=template,
        path=context.obj.tree.root,
        force=force,
        logger=context.obj.logger)


_plan_export_formats = list(tmt.Plan.get_export_plugin_registry().iter_plugin_ids())
_plan_export_default = 'yaml'


@plans.command(name='export')
@pass_context
@filtering_options_long
@option(
    '-h', '--how', default=_plan_export_default, show_default=True,
    help='Output format.',
    choices=_plan_export_formats)
@option(
    '--format', default=_plan_export_default, show_default=True,
    help='Output format.',
    deprecated=Deprecated('1.21', hint='use --how instead'),
    choices=_plan_export_formats)
@option(
    '-d', '--debug', is_flag=True,
    help='Provide as much debugging details as possible.')
# TODO: move to `template` export plugin options
@option(
    '--template', metavar='PATH',
    help="Path to a template to use for rendering the export. Used with '--how=template' only."
    )
@environment_options
def plans_export(
        context: Context,
        how: str,
        format: str,
        template: Optional[str],
        **kwargs: Any) -> None:
    """
    Export plans into desired format.

    Regular expression can be used to filter plans by name.
    Use '.' to select plans under the current working directory.
    """
    tmt.Plan.store_cli_invocation(context)

    if format != _test_export_default:
        context.obj.common.warn("Option '--format' is deprecated, please use '--how' instead.")

        how = format

    echo(tmt.Plan.export_collection(
        collection=context.obj.tree.plans(),
        format=how,
        template=Path(template) if template else None
        ))


# ignore[arg-type]: click code expects click.Context, but we use our own type for better type
# inference. See Context and ContextObjects above.
@plans.command(name="id")  # type: ignore[arg-type]
@pass_context
@filtering_options
@verbosity_options
@force_dry_options
def plans_id(context: Context, **kwargs: Any) -> None:
    """
    Generate a unique id for each selected plan.

    A new UUID is generated for each plan matching the provided
    filter and the value is stored to disk. Existing identifiers
    are kept intact.
    """
    tmt.Plan.store_cli_invocation(context)
    for plan in context.obj.tree.plans():
        tmt.identifier.id_command(context, plan.node, "plan", dry=kwargs["dry"])

# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#  Story
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~


# ignore[arg-type]: click code expects click.Context, but we use our own type for better type
# inference. See Context and ContextObjects above.
@main.group(invoke_without_command=True, cls=CustomGroup)  # type: ignore[arg-type]
@pass_context
@verbosity_options
def stories(context: Context, **kwargs: Any) -> None:
    """
    Manage user stories.

    \b
    Check available user stories.
    Explore coverage (test, implementation, documentation).
    """

    context.obj.logger = context.obj.logger.clone() \
        .apply_verbosity_options(**kwargs)

    # Show overview of available stories
    if context.invoked_subcommand is None:
        tmt.Story.overview(context.obj.tree)


# ignore[arg-type]: click code expects click.Context, but we use our own type for better type
# inference. See Context and ContextObjects above.
@stories.command(name='ls')  # type: ignore[arg-type]
@pass_context
@filtering_options_long
@story_flags_filter_options
@verbosity_options
def stories_ls(
        context: Context,
        implemented: bool,
        verified: bool,
        documented: bool,
        covered: bool,
        unimplemented: bool,
        unverified: bool,
        undocumented: bool,
        uncovered: bool,
        **kwargs: Any) -> None:
    """
    List available stories.

    Regular expression can be used to filter stories by name.
    Use '.' to select stories under the current working directory.
    """
    tmt.Story.store_cli_invocation(context)
    for story in context.obj.tree.stories():
        if story._match(implemented, verified, documented, covered,
                        unimplemented, unverified, undocumented, uncovered):
            story.ls()


# ignore[arg-type]: click code expects click.Context, but we use our own type for better type
# inference. See Context and ContextObjects above.
@stories.command(name='show')  # type: ignore[arg-type]
@pass_context
@filtering_options_long
@story_flags_filter_options
@verbosity_options
def stories_show(
        context: Context,
        implemented: bool,
        verified: bool,
        documented: bool,
        covered: bool,
        unimplemented: bool,
        unverified: bool,
        undocumented: bool,
        uncovered: bool,
        **kwargs: Any) -> None:
    """
    Show story details.

    Regular expression can be used to filter stories by name.
    Use '.' to select stories under the current working directory.
    """
    tmt.Story.store_cli_invocation(context)

    logger = context.obj.logger.clone() \
        .apply_verbosity_options(**kwargs)

    for story in context.obj.tree.stories(logger=logger):
        if story._match(implemented, verified, documented, covered,
                        unimplemented, unverified, undocumented, uncovered):
            story.show()
            echo()


_story_templates = fmf.utils.listed(tmt.templates.MANAGER.templates['story'], join='or')


@stories.command(name='create')
@pass_context
@click.argument('names', nargs=-1, metavar='[NAME]...')
@option(
    '-t', '--template', metavar='TEMPLATE',
    prompt=f'Template ({_story_templates})',
    help=f'Story template ({_story_templates}).')
@option(
    '--link', metavar='[RELATION:]TARGET', multiple=True,
    help='Link created story to the relevant issues.')
@verbosity_options
@force_dry_options
def stories_create(
        context: Context,
        names: list[str],
        template: str,
        force: bool,
        **kwargs: Any) -> None:
    """ Create a new story based on given template. """
    assert context.obj.tree.root is not None  # narrow type
    tmt.Story.store_cli_invocation(context)
    tmt.Story.create(
        names=names,
        template=template,
        path=context.obj.tree.root,
        force=force,
        logger=context.obj.logger)


# ignore[arg-type]: click code expects click.Context, but we use our own type for better type
# inference. See Context and ContextObjects above.
@stories.command(name='coverage')  # type: ignore[arg-type]
@option(
    '--docs', is_flag=True, help='Show docs coverage.')
@option(
    '--test', is_flag=True, help='Show test coverage.')
@option(
    '--code', is_flag=True, help='Show code coverage.')
@pass_context
@filtering_options_long
@story_flags_filter_options
@verbosity_options
def stories_coverage(
        context: Context,
        code: bool,
        test: bool,
        docs: bool,
        implemented: bool,
        verified: bool,
        documented: bool,
        covered: bool,
        unimplemented: bool,
        unverified: bool,
        undocumented: bool,
        uncovered: bool,
        **kwargs: Any) -> None:
    """
    Show code, test and docs coverage for given stories.

    Regular expression can be used to filter stories by name.
    Use '.' to select stories under the current working directory.
    """
    tmt.Story.store_cli_invocation(context)

    def headfoot(text: str) -> None:
        """ Format simple header/footer """
        echo(style(text.rjust(4) + ' ', fg='blue'), nl=False)

    header = False
    total = code_coverage = test_coverage = docs_coverage = 0
    if not any([code, test, docs]):
        code = test = docs = True
    for story in context.obj.tree.stories():
        # Check conditions
        if not story._match(
                implemented, verified, documented, covered, unimplemented,
                unverified, undocumented, uncovered):
            continue
        # Show header once
        if not header:
            if code:
                headfoot('code')
            if test:
                headfoot('test')
            if docs:
                headfoot('docs')
            headfoot('story')
            echo()
            header = True
        # Show individual stats
        status = story.coverage(code, test, docs)
        total += 1
        code_coverage += status[0]
        test_coverage += status[1]
        docs_coverage += status[2]
    # Summary
    if not total:
        return
    if code:
        headfoot(f'{round(100 * code_coverage / total)}%')
    if test:
        headfoot(f'{round(100 * test_coverage / total)}%')
    if docs:
        headfoot(f'{round(100 * docs_coverage / total)}%')
    headfoot(f"from {fmf.utils.listed(total, 'story')}")
    echo()


_story_export_formats = list(tmt.Story.get_export_plugin_registry().iter_plugin_ids())
_story_export_default = 'yaml'


@stories.command(name='export')
@pass_context
@filtering_options_long
@story_flags_filter_options
@option(
    '-h', '--how', default=_story_export_default, show_default=True,
    help='Output format.',
    choices=_story_export_formats)
@option(
    '--format', default=_story_export_default, show_default=True,
    help='Output format.',
    deprecated=Deprecated('1.21', hint='use --how instead'),
    choices=_story_export_formats)
@option(
    '-d', '--debug', is_flag=True,
    help='Provide as much debugging details as possible.')
# TODO: move to `template` export plugin options
@option(
    '--template', metavar='PATH',
    help="Path to a template to use for rendering the export. Used with '--how=rst|template' only."
    )
def stories_export(
        context: Context,
        how: str,
        format: str,
        implemented: bool,
        verified: bool,
        documented: bool,
        covered: bool,
        unimplemented: bool,
        unverified: bool,
        undocumented: bool,
        uncovered: bool,
        template: Optional[str],
        **kwargs: Any) -> None:
    """
    Export selected stories into desired format.

    Regular expression can be used to filter stories by name.
    Use '.' to select stories under the current working directory.
    """
    tmt.Story.store_cli_invocation(context)

    if format != _test_export_default:
        context.obj.common.warn("Option '--format' is deprecated, please use '--how' instead.")

        how = format

    stories = [
        story for story in context.obj.tree.stories(whole=True)
        if story._match(implemented, verified, documented, covered, unimplemented, unverified,
                        undocumented, uncovered)
        ]

    echo(tmt.Story.export_collection(
        collection=stories,
        format=how,
        template=Path(template) if template else None))


# ignore[arg-type]: click code expects click.Context, but we use our own type for better type
# inference. See Context and ContextObjects above.
@stories.command(name="id")  # type: ignore[arg-type]
@pass_context
@filtering_options_long
@story_flags_filter_options
@verbosity_options
@force_dry_options
def stories_id(
        context: Context,
        implemented: bool,
        verified: bool,
        documented: bool,
        covered: bool,
        unimplemented: bool,
        unverified: bool,
        undocumented: bool,
        uncovered: bool,
        **kwargs: Any) -> None:
    """
    Generate a unique id for each selected story.

    A new UUID is generated for each story matching the provided
    filter and the value is stored to disk. Existing identifiers
    are kept intact.
    """
    tmt.Story.store_cli_invocation(context)
    for story in context.obj.tree.stories():
        if story._match(implemented, verified, documented, covered,
                        unimplemented, unverified, undocumented, uncovered):
            tmt.identifier.id_command(context, story.node, "story", dry=kwargs["dry"])


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#  Clean
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

# Supported clean resources
CLEAN_RESOURCES: list[str] = ["guests", "runs", "images"]


@main.group(chain=True, invoke_without_command=True, cls=CustomGroup)
@pass_context
@option(
    '-l', '--last', is_flag=True,
    help='Clean resources related to the last run.')
@option(
    '-i', '--id', 'id_', metavar="ID", multiple=True,
    help='Identifier (name or directory path) of the run to be cleaned.')
@option(
    '-k', '--keep', type=int, default=None,
    help='The number of latest workdirs to keep, clean the rest.')
@option(
    '-s', '--skip', choices=CLEAN_RESOURCES,
    help='The resources which should be kept on the disk.', multiple=True)
@workdir_root_options
@verbosity_options
@dry_options
def clean(context: Context,
          last: bool,
          id_: tuple[str, ...],
          keep: Optional[int],
          skip: list[str],
          _workdir_root: Optional[str],
          **kwargs: Any) -> None:
    """
    Clean workdirs, guests or images.

    Without any command, clean everything, stop the guests, remove
    all runs and then remove all images. Search for runs in
    /var/tmp/tmt, if runs are stored elsewhere, the path to them can
    be set using a subcommand (either runs or guests subcommand).

    The subcommands can be chained, the order of cleaning is always
    the same, irrespective of the order on the command line. First, all
    the guests are cleaned, followed by runs and images.
    """
    if last and id_:
        raise tmt.utils.GeneralError(
            "Options --last and --id cannot be used together.")
    workdir_root = Path(_workdir_root) if _workdir_root is not None else None
    if workdir_root and not workdir_root.exists():
        raise tmt.utils.GeneralError(f"Path '{workdir_root}' doesn't exist.")

    context.obj.clean_logger = context.obj.logger \
        .descend(logger_name='clean', extra_shift=0) \
        .apply_verbosity_options(**kwargs)

    echo(style('clean', fg='red'))
    clean_obj = tmt.Clean(
        logger=context.obj.clean_logger,
        parent=context.obj.common,
        cli_invocation=CliInvocation.from_context(context))
    context.obj.clean = clean_obj
    exit_code = 0
    if context.invoked_subcommand is None:
        assert context.obj.clean_logger is not None  # narrow type
        workdir_root = effective_workdir_root(workdir_root)
        # Create another level to the hierarchy so that logging indent is
        # consistent between the command and subcommands
        clean_obj = tmt.Clean(
            logger=context.obj.clean_logger
            .descend(logger_name='clean', extra_shift=0)
            .apply_verbosity_options(**kwargs),
            parent=clean_obj,
            cli_invocation=CliInvocation.from_context(context),
            workdir_root=workdir_root)
        if workdir_root.exists():
            if 'guests' not in skip and not clean_obj.guests(id_, keep):
                exit_code = 1
            if 'runs' not in skip and not clean_obj.runs(id_, keep):
                exit_code = 1
        else:
            clean_obj.warn(
                f"Directory '{workdir_root}' does not exist, "
                f"skipping guest and run cleanup.")
        if 'images' not in skip and not clean_obj.images():
            exit_code = 1
        raise SystemExit(exit_code)


# ignore[arg-type]: click code expects click.Context, but we use our own type for better type
# inference. See Context and ContextObjects above.
@clean.result_callback()  # type: ignore[arg-type]
@pass_context
def perform_clean(
        click_context: Context,
        commands: Any,
        *args: Any,
        **kwargs: Any) -> None:
    """
    Perform clean actions in the correct order.

    We need to ensure that guests are always cleaned before the run workdirs
    even if the user specified them in reverse order.
    """
    clean_order = ("guests", "runs", "images")
    exit_code = 0
    for phase in clean_order:
        for partial in click_context.obj.clean_partials[phase]:
            if not partial():
                exit_code = 1
    raise SystemExit(exit_code)


@clean.command(name='runs')
@pass_context
@workdir_root_options
@option(
    '-l', '--last', is_flag=True, help='Clean the workdir of the last run.')
@option(
    '-i', '--id', 'id_', metavar="ID", multiple=True,
    help='Run id(name or directory path) to clean workdir of. Can be specified multiple times.')
@option(
    '-k', '--keep', type=int, default=None,
    help='The number of latest workdirs to keep, clean the rest.')
@verbosity_options
@dry_options
def clean_runs(
        context: Context,
        _workdir_root: Optional[str],
        last: bool,
        id_: tuple[str, ...],
        keep: Optional[int],
        **kwargs: Any) -> None:
    """
    Clean workdirs of past runs.

    Remove all runs in '/var/tmp/tmt' by default.
    """
    defined = [last is True, bool(id_), keep is not None]
    if defined.count(True) > 1:
        raise tmt.utils.GeneralError(
            "Options --last, --id and --keep cannot be used together.")
    if keep is not None and keep < 0:
        raise tmt.utils.GeneralError("--keep must not be a negative number.")
    workdir_root = Path(_workdir_root) if _workdir_root is not None else None
    if workdir_root and not workdir_root.exists():
        raise tmt.utils.GeneralError(f"Path '{workdir_root}' doesn't exist.")

    assert context.obj.clean_logger is not None  # narrow type

    clean_obj = tmt.Clean(
        logger=context.obj.clean_logger
        .descend(logger_name='clean-runs', extra_shift=0)
        .apply_verbosity_options(**kwargs),
        parent=context.obj.clean,
        cli_invocation=CliInvocation.from_context(context),
        workdir_root=effective_workdir_root(workdir_root))
    context.obj.clean_partials["runs"].append(
        lambda: clean_obj.runs(
            (context.parent and context.parent.params.get('id_', [])) or id_,
            (context.parent and context.parent.params.get('keep', [])) or keep))


@clean.command(name='guests')
@pass_context
@workdir_root_options
@option(
    '-l', '--last', is_flag=True, help='Stop the guest of the last run.')
@option(
    '-i', '--id', 'id_', metavar="ID", multiple=True,
    help='Run id(name or directory path) to stop the guest of. Can be specified multiple times.')
@option(
    '-k', '--keep', type=int, default=None,
    help='The number of latest guests to keep, clean the rest.')
@option(
    '-h', '--how', metavar='METHOD',
    help='Stop guests of the specified provision method.')
@verbosity_options
@dry_options
def clean_guests(
        context: Context,
        _workdir_root: Optional[str],
        last: bool,
        id_: tuple[str, ...],
        keep: Optional[int],
        **kwargs: Any) -> None:
    """
    Stop running guests of runs.

    Stop guests of all runs in '/var/tmp/tmt' by default.
    """
    if last and bool(id_):
        raise tmt.utils.GeneralError(
            "Options --last and --id cannot be used together.")
    workdir_root = Path(_workdir_root) if _workdir_root is not None else None
    if workdir_root and not workdir_root.exists():
        raise tmt.utils.GeneralError(f"Path '{workdir_root}' doesn't exist.")

    assert context.obj.clean_logger is not None  # narrow type
    clean_obj = tmt.Clean(
        logger=context.obj.clean_logger
        .descend(logger_name='clean-guests', extra_shift=0)
        .apply_verbosity_options(**kwargs),
        parent=context.obj.clean,
        cli_invocation=CliInvocation.from_context(context),
        workdir_root=effective_workdir_root(workdir_root))
    context.obj.clean_partials["guests"].append(
        lambda: clean_obj.guests(
            (context.parent and context.parent.params.get('id_', [])) or id_,
            (context.parent and context.parent.params.get('keep', [])) or keep))


# ignore[arg-type]: click code expects click.Context, but we use our own type for better type
# inference. See Context and ContextObjects above.
@clean.command(name='images')  # type: ignore[arg-type]
@pass_context
@verbosity_options
@dry_options
def clean_images(context: Context, **kwargs: Any) -> None:
    """
    Remove images of supported provision methods.

    Currently supported methods are:
     - testcloud
    """
    # FIXME: If there are more provision methods supporting this,
    #        we should add options to specify which provision should be
    #        cleaned, similarly to guests.
    assert context.obj.clean_logger is not None  # narrow type

    clean_obj = tmt.Clean(
        logger=context.obj.clean_logger
        .descend(logger_name='clean-images', extra_shift=0)
        .apply_verbosity_options(**kwargs),
        parent=context.obj.clean,
        cli_invocation=CliInvocation.from_context(context))
    context.obj.clean_partials["images"].append(clean_obj.images)

# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#  Setup
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~


@main.group(cls=CustomGroup)
def setup(**kwargs: Any) -> None:
    """ Setup the environment for working with tmt """


@setup.group(cls=CustomGroup)
def completion(**kwargs: Any) -> None:
    """
    Setup shell completions.

    By default, these commands only write a shell script to the output
    which can then be sourced from the shell's configuration file. Use
    the '--install' option to store and enable the configuration
    permanently.
    """


COMPLETE_VARIABLE = '_TMT_COMPLETE'
COMPLETE_SCRIPT = 'tmt-complete'


def setup_completion(shell: str, install: bool, context: Context) -> None:
    """ Setup completion based on the shell """
    config = tmt.config.Config()
    # Fish gets installed into its special location where it is automatically
    # loaded.
    if shell == 'fish':
        script = Path('~/.config/fish/completions/tmt.fish').expanduser()
    # Bash and zsh get installed to tmt's config directory.
    else:
        script = Path(config.path) / f'{COMPLETE_SCRIPT}.{shell}'

    env_var = {COMPLETE_VARIABLE: f'{shell}_source'}

    logger = context.obj.logger

    completions = Command('tmt').run(env=tmt.utils.Environment.from_dict(env_var),
                                     cwd=None,
                                     logger=context.obj.logger
                                     ).stdout
    if not completions:
        logger.warning("Unable to generate shell completion")
        return

    if install:
        Path(script).write_text(completions)
        # If requested, modify .bashrc or .zshrc
        if shell != 'fish':
            shell_config = Path(f'~/.{shell}rc').expanduser()
            shell_config.append_text('\n# Generated by tmt\n')
            shell_config.append_text(f'source {script}')

    else:
        logger.info(completions)


@completion.command(name='bash')
@pass_context
@option(
    '--install', '-i', 'install', is_flag=True,
    help="""
         Persistently store the script to tmt's configuration directory and set it up by modifying
         '~/.bashrc'.
         """)
def completion_bash(context: Context, install: bool, **kwargs: Any) -> None:
    """ Setup shell completions for bash """
    setup_completion('bash', install, context)


@completion.command(name='zsh')
@pass_context
@option(
    '--install', '-i', 'install', is_flag=True,
    help="""
         Persistently store the script to tmt's configuration directory and set it up by modifying
         '~/.zshrc'.
         """)
def completion_zsh(context: Context, install: bool, **kwargs: Any) -> None:
    """ Setup shell completions for zsh """
    setup_completion('zsh', install, context)


@completion.command(name='fish')
@pass_context
@option(
    '--install', '-i', 'install', is_flag=True,
    help="Persistently store the script to '~/.config/fish/completions/tmt.fish'.")
def completion_fish(context: Context, install: bool, **kwargs: Any) -> None:
    """ Setup shell completions for fish """
    setup_completion('fish', install, context)


@main.command(name='link')
@pass_context
@click.argument('names', nargs=-1, metavar='[TEST|PLAN|STORY]...')
@option(
    '--link', 'links', metavar='[RELATION:]TARGET', multiple=True,
    help="""
        Issue to which tests, plans or stories should be linked.
        Can be provided multiple times.
        """)
@option(
    '--separate', is_flag=True,
    help="Create linking separately for multiple passed objects.")
def link(context: Context,
         names: list[str],
         links: list[str],
         separate: bool,
         ) -> None:
    """
    Create a link to tmt web service in an issue tracking software.

    Using the specified target, a link will be generated and added
    to an issue. Link is generated from names of tmt objects
    passed in arguments and configuration file.
    """

    tmt_objects = (
        context.obj.tree.tests(names=list(names)) +
        context.obj.tree.plans(names=list(names)) +
        context.obj.tree.stories(names=list(names)))

    if not tmt_objects:
        raise tmt.utils.GeneralError("No test, plan or story found for linking.")

    if not links:
        raise tmt.utils.GeneralError("Provide at least one link using the '--link' option.")

    for link in links:
        tmt.utils.jira.link(
            tmt_objects=tmt_objects,
            links=tmt.base.Links(data=link),
            separate=separate,
            logger=context.obj.logger)
