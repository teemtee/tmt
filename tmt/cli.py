
""" Command line interface for the Test Management Tool """

import collections
import dataclasses
import enum
import re
import subprocess
import sys
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, Callable, Optional, TypeVar, Union

import click
import fmf
import fmf.utils
from click import echo, style

import tmt
import tmt.base
import tmt.convert
import tmt.export
import tmt.identifier
import tmt.lint
import tmt.log
import tmt.options
import tmt.plugins
import tmt.steps
import tmt.templates
import tmt.trying
import tmt.utils
from tmt.options import Deprecated, create_options_decorator, option
from tmt.utils import Path, cached_property

if TYPE_CHECKING:
    from typing_extensions import Concatenate, ParamSpec

    import tmt.steps.discover
    import tmt.steps.execute
    import tmt.steps.finish
    import tmt.steps.prepare
    import tmt.steps.provision
    import tmt.steps.report

    P = ParamSpec('P')
    R = TypeVar('R')


#: A logger to use before the proper one can be established.
#:
#: .. warning::
#:
#:    This logger should be used with utmost care for logging while tmt
#:    is still starting. Once properly configured logger is spawned,
#:    honoring relevant options, this logger should not be used anymore.
_BOOTSTRAP_LOGGER = tmt.log.Logger.get_bootstrap_logger()


# Explore available plugins (need to detect all supported methods first)
tmt.plugins.explore(_BOOTSTRAP_LOGGER)


class TmtExitCode(enum.IntEnum):
    # Quoting the specification:

    #: At least one test passed, there was no fail, warn or error.
    SUCCESS = 0

    #: There was a fail or warn identified, but no error.
    FAIL = 1

    #: Errors occured during test execution.
    ERROR = 2

    #: No test results found.
    NO_RESULTS_FOUND = 3

    #: Tests were executed, and all reported the ``skip`` result.
    ALL_TESTS_SKIPPED = 4


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#  Click Context Object Container
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~


@dataclasses.dataclass
class ContextObject:
    """
    Click Context Object container.

    In Click terms, this is "an arbitrary object of user data." In this container,
    tmt CLI code stores all structures relevant for the command execution. The
    container itself is then attached to :py:class:`click.Context` object Click
    manages across commands.
    """

    # "Parent" Click context
    cli_context: 'Context'

    logger: tmt.log.Logger
    common: tmt.utils.Common
    fmf_context: tmt.utils.FmfContext
    tree: tmt.Tree
    steps: set[str] = dataclasses.field(default_factory=set)
    clean: Optional[tmt.Clean] = None
    clean_logger: Optional[tmt.log.Logger] = None
    clean_partials: collections.defaultdict[str, list[tmt.base.CleanCallback]] = dataclasses.field(
        default_factory=lambda: collections.defaultdict(list))
    run: Optional[tmt.Run] = None


class Context(click.Context):
    """
    Custom :py:class:`click.Context`-like class for typing purposes.

    Objects of this class are never instantiated, it serves only as a type
    stub in commands below, to simplify handling and static analysis of
    ``context.obj``. There is no added functionality, the only change is
    a much narrower type of ``obj`` attribute.

    This class shall be used instead of the original :py:class:`click.Context`.
    Click is obviously not aware of our type annotations, and ``context``
    objects managed by Click would always be of type :py:class:`click.Context`,
    we would just convince mypy their ``obj`` attribute is no longer ``Any``.
    """

    # In contrast to the original Context, we *know* we do set obj to a valid
    # object, and every time we touch it, it should absolutely be not-None.
    obj: ContextObject

    max_content_width: Optional[int]


def pass_context(fn: 'Callable[Concatenate[Context, P], R]') -> 'Callable[P, R]':
    """
    Custom :py:func:`click.pass_context`-like decorator.

    Complementing the :py:class:`Context`, the goal of this decorator to
    announce the correct type of the ``context`` parameter. The original
    decorator annotates the parameter as ``click.Context``, but that is not
    what our command callables accept. So, on this boundary between tmt code
    and ``click`` API, we trick type checkers by isolating the necessary
    ``type: ignore[arg-type]``.
    """

    return click.pass_context(fn)  # type: ignore[arg-type]


@dataclasses.dataclass
class CliInvocation:
    """
    A single CLI invocation of a tmt subcommand.

    Bundles together the Click context and options derived from it.
    A context alone might be good enough, but sometimes tmt needs to
    modify saved options. For custom command line options injected
    manually 'sources' is used to keep the parameter source.

    Serves as a clear boundary between invocations of classes
    representing various tmt subcommands and groups.
    """

    context: Optional[Context]
    options: dict[str, Any]

    @classmethod
    def from_context(cls, context: Context) -> 'CliInvocation':
        return CliInvocation(context=context, options=context.params)

    @classmethod
    def from_options(cls, options: dict[str, Any]) -> 'CliInvocation':
        """ Inject custom options coming from the command line """
        invocation = CliInvocation(context=None, options=options)

        # ignore[reportGeneralTypeIssues]: pyright has troubles understanding it
        # *is* possible to assign to a cached property. Might an issue of our
        # simplified implementation.
        # ignore[unused-ignore]: silencing mypy's complaint about silencing
        # pyright's warning :)
        invocation.option_sources = {  # type: ignore[reportGeneralTypeIssues,unused-ignore]
            key: click.core.ParameterSource.COMMANDLINE
            for key in options
            }
        return invocation

    @cached_property
    def option_sources(self) -> dict[str, click.core.ParameterSource]:
        if not self.context:
            return {}

        return self.context._parameter_source


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#  Custom Group
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

class CustomGroup(click.Group):
    """ Custom Click Group """

    # ignore[override]: expected, we want to use more specific `Context`
    # type than the one declared in superclass.
    def list_commands(self, context: Context) -> list[str]:  # type: ignore[override]
        """ Prevent alphabetical sorting """
        return list(self.commands.keys())

    # ignore[override]: expected, we want to use more specific `Context`
    # type than the one declared in superclass.
    def get_command(  # type: ignore[override]
            self,
            context: Context,
            cmd_name: str
            ) -> Optional[click.Command]:
        """ Allow command shortening """
        # Backward-compatible 'test convert' (just temporary for now FIXME)
        cmd_name = cmd_name.replace('convert', 'import')
        # Support both story & stories
        cmd_name = cmd_name.replace('story', 'stories')
        found = click.Group.get_command(self, context, cmd_name)
        if found is not None:
            return found
        matches = [command for command in self.list_commands(context)
                   if command.startswith(cmd_name)]
        if not matches:
            return None
        if len(matches) == 1:
            return click.Group.get_command(self, context, matches[0])
        context.fail(f"Did you mean {fmf.utils.listed(sorted(matches), join='or')}?")
        return None


class HelpFormatter(click.HelpFormatter):
    """ Custom help formatter capable of rendering ReST syntax """

    # Override parent implementation
    def write_dl(
            self,
            rows: Sequence[tuple[str, str]],
            col_max: int = 30,
            col_spacing: int = 2) -> None:
        rows = [
            (option, tmt.utils.render_rst(help, _BOOTSTRAP_LOGGER))
            for option, help in rows
            ]

        super().write_dl(rows, col_max=col_max, col_spacing=col_spacing)


click.Context.formatter_class = HelpFormatter


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#  Common Options
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
verbosity_options = create_options_decorator(tmt.options.VERBOSITY_OPTIONS)
dry_options = create_options_decorator(tmt.options.DRY_OPTIONS)
force_dry_options = create_options_decorator(tmt.options.FORCE_DRY_OPTIONS)
again_option = create_options_decorator(tmt.options.AGAIN_OPTION)
fix_options = create_options_decorator(tmt.options.FIX_OPTIONS)
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
@option(
    '--feeling-safe',
    is_flag=True,
    help="""
         WARNING: with this option, tmt would be allowed to make
         potentially dangerous actions. For example, some metadata
         keys may cause scripts being executed on the runner.
         Do not use this option unless you trust metadata consumed
         by tmt, or unless you know what you are doing.
         """)
@verbosity_options
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
def main(
        click_contex: Context,
        root: str,
        context: list[str],
        no_color: bool,
        force_color: bool,
        show_time: bool,
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

    # Save click context and fmf context for future use
    tmt.utils.Common.store_cli_invocation(click_contex)

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
@verbosity_options
@force_dry_options
@again_option
def run(context: Context, id_: Optional[str], **kwargs: Any) -> None:
    """ Run test steps. """
    # Initialize
    logger = context.obj.logger.descend(logger_name='run', extra_shift=0)
    logger.apply_verbosity_options(**kwargs)

    run = tmt.Run(
        id_=Path(id_) if id_ is not None else None,
        tree=context.obj.tree,
        cli_invocation=CliInvocation.from_context(context),
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


def _lint_class(
        context: Context,
        klass: Union[type[tmt.base.Test], type[tmt.base.Plan], type[tmt.base.Story]],
        failed_only: bool,
        enable_checks: list[str],
        disable_checks: list[str],
        enforce_checks: list[str],
        outcomes: list[tmt.lint.LinterOutcome],
        **kwargs: Any) -> int:
    """ Lint a single class of objects """

    # FIXME: Workaround https://github.com/pallets/click/pull/1840 for click 7
    context.params.update(**kwargs)
    klass.store_cli_invocation(context)

    exit_code = 0

    linters = klass.resolve_enabled_linters(
        enable_checks=enable_checks or None,
        disable_checks=disable_checks or None)

    for lintable in klass.from_tree(context.obj.tree):
        valid, rulings = lintable.lint(
            linters=linters,
            enforce_checks=enforce_checks or None)

        # If the object pass the checks, and we're asked to show only the failed
        # ones, display nothing.
        if valid and failed_only:
            continue

        # Find out what rulings were allowed by user. By default, it's all, but
        # user might be interested in "warn" only, for example. Reduce the list
        # of rulings, and if we end up with an empty list *and* user constrained
        # us to just a subset of rulings, display nothing.
        allowed_rulings = list(tmt.lint.filter_allowed_checks(rulings, outcomes=outcomes))

        if not allowed_rulings and outcomes:
            continue

        lintable.ls()

        echo('\n'.join(tmt.lint.format_rulings(allowed_rulings)))

        if not valid:
            exit_code = 1

        echo()

    return exit_code


def do_lint(
        context: Context,
        klasses: list[Union[type[tmt.base.Test], type[tmt.base.Plan], type[tmt.base.Story]]],
        list_checks: bool,
        failed_only: bool,
        enable_checks: list[str],
        disable_checks: list[str],
        enforce_checks: list[str],
        outcomes: list[tmt.lint.LinterOutcome],
        **kwargs: Any) -> int:
    """ Core of all ``lint`` commands """

    if list_checks:
        for klass in klasses:
            klass_label = 'stories' if klass is tmt.base.Story else f'{klass.__name__.lower()}s'
            echo(f'Linters available for {klass_label}')
            echo(klass.format_linters())
            echo()

        return 0

    return max(
        _lint_class(
            context,
            klass,
            failed_only,
            enable_checks,
            disable_checks,
            enforce_checks,
            outcomes,
            **kwargs)
        for klass in klasses
        )


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
    for test in context.obj.tree.tests():
        test.show()
        echo()


# ignore[arg-type]: click code expects click.Context, but we use our own type for better type
# inference. See Context and ContextObjects above.
@tests.command(name='lint')  # type: ignore[arg-type]
@pass_context
@filtering_options
@fmf_source_options
@lint_options
@fix_options
@verbosity_options
def tests_lint(
        context: Context,
        list_checks: bool,
        failed_only: bool,
        enable_checks: list[str],
        disable_checks: list[str],
        enforce_checks: list[str],
        outcome_only: tuple[str, ...],
        **kwargs: Any) -> None:
    """
    Check tests against the L1 metadata specification.

    Regular expression can be used to filter tests for linting.
    Use '.' to select tests under the current working directory.
    """

    exit_code = do_lint(
        context,
        [tmt.base.Test],
        list_checks,
        failed_only,
        enable_checks,
        disable_checks,
        enforce_checks,
        [tmt.lint.LinterOutcome(outcome) for outcome in outcome_only],
        **kwargs)

    raise SystemExit(exit_code)


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
    help='Link to the relevant issues.')
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
        tmt.convert.read_manual(plan, case, disabled, with_script)
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
            purpose, disabled, types, general, dry)
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
    for plan in context.obj.tree.plans():
        plan.show()
        echo()


# ignore[arg-type]: click code expects click.Context, but we use our own type for better type
# inference. See Context and ContextObjects above.
@plans.command(name='lint')  # type: ignore[arg-type]
@pass_context
@filtering_options
@fmf_source_options
@lint_options
@fix_options
@verbosity_options
def plans_lint(
        context: Context,
        list_checks: bool,
        failed_only: bool,
        enable_checks: list[str],
        disable_checks: list[str],
        enforce_checks: list[str],
        outcome_only: tuple[str, ...],
        **kwargs: Any) -> None:
    """
    Check plans against the L2 metadata specification.

    Regular expression can be used to filter plans by name.
    Use '.' to select plans under the current working directory.
    """

    exit_code = do_lint(
        context,
        [tmt.base.Plan],
        list_checks,
        failed_only,
        enable_checks,
        disable_checks,
        enforce_checks,
        [tmt.lint.LinterOutcome(outcome) for outcome in outcome_only],
        **kwargs)

    raise SystemExit(exit_code)


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
    for story in context.obj.tree.stories():
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
@stories.command(name='lint')  # type: ignore[arg-type]
@pass_context
@filtering_options
@fmf_source_options
@lint_options
@fix_options
@verbosity_options
def stories_lint(
        context: Context,
        list_checks: bool,
        failed_only: bool,
        enable_checks: list[str],
        disable_checks: list[str],
        enforce_checks: list[str],
        outcome_only: tuple[str, ...],
        **kwargs: Any) -> None:
    """
    Check stories against the L3 metadata specification.

    Regular expression can be used to filter stories by name.
    Use '.' to select stories under the current working directory.
    """

    exit_code = do_lint(
        context,
        [tmt.base.Story],
        list_checks,
        failed_only,
        enable_checks,
        disable_checks,
        enforce_checks,
        [tmt.lint.LinterOutcome(outcome) for outcome in outcome_only],
        **kwargs)

    raise SystemExit(exit_code)


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
#  Init
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

@main.command()
@pass_context
@click.argument('path', default='.')
@option(
    '-t', '--template', default='empty',
    choices=['empty', *tmt.templates.INIT_TEMPLATES],
    help="Use this template to populate the tree.")
@verbosity_options
@force_dry_options
def init(
        context: Context,
        path: str,
        template: str,
        force: bool,
        **kwargs: Any) -> None:
    """
    Initialize a new tmt tree.

    By default tree is created in the current directory.
    Provide a PATH to create it in a different location.

    \b
    A tree can be optionally populated with example metadata:
    * 'mini' template contains a minimal plan and no tests,
    * 'base' template contains a plan and a beakerlib test,
    * 'full' template contains a 'full' story, an 'full' plan and a shell test.
    """

    tmt.Tree.store_cli_invocation(context)
    tmt.Tree.init(logger=context.obj.logger, path=Path(path), template=template, force=force)


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#  Try
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

@main.command(name="try")
@click.pass_context
@click.argument("image_and_how", nargs=-1, metavar="IMAGE[@HOW]")
@option(
    "-t", "--test", default=[], metavar="REGEXP", multiple=True,
    help="""
        Run tests matching given regular expression.
        By default all tests under the current working directory are executed.
        """)
@option(
    "-p", "--plan", default=[], metavar="REGEXP", multiple=True,
    help="""
        Use provided plan. By default user config is checked for plans
        named as '/user/plan*', default plan is used otherwise.
        """)
@option(
    "-l", "--login", is_flag=True, default=False,
    help="Log into the guest only, do not run any tests.")
@option(
    "-a", "--ask", is_flag=True, default=False,
    help="Just provision the guest and ask what to do next.")
@verbosity_options
@force_dry_options
def try_command(context: Context, image_and_how: str, **kwargs: Any) -> None:
    """
    Try tests or experiment with guests.

    Provide an interactive session to run tests or play with guests.
    Provisions a guest, runs tests from the current working directory
    and provides menu with available options what to do next. If no
    tests are detected logs into the guest to start experimenting.

    In order to specify the guest just use the desired image name:

        tmt try fedora

    It's also possible to select the provision method for each guest:

    \b
        tmt run fedora@container
        tmt run centos-stream-9@virtual
    """

    tmt.trying.Try.store_cli_invocation(context)

    # Inject custom image and provision method to the Provision options
    if image_and_how:

        # TODO: For now just pick the first image-how pair, let's allow
        # specifying multiple images and provision methods as well
        image_and_how = image_and_how[0]

        # We expect the 'image' or 'image@how' syntax
        matched = re.match("([^@]+)@([^@]+)", image_and_how.strip())
        if matched:
            options = {"image": matched.group(1), "how": matched.group(2)}
        else:
            options = {"image": image_and_how}

        tmt.steps.provision.Provision.store_cli_invocation(context=None, options=options)

    # Finally, let's start trying!
    trying = tmt.trying.Try(
        tree=context.obj.tree,
        logger=context.obj.logger)

    trying.go()


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#  Status
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

@main.command()
@pass_context
@workdir_root_options
@option(
    '-i', '--id', metavar="ID",
    help='Run id (name or directory path) to show status of.')
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
        workdir_root: str,
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
    if not Path(workdir_root).exists():
        raise tmt.utils.GeneralError(f"Path '{workdir_root}' doesn't exist.")

    status_obj = tmt.Status(
        logger=context.obj.logger.clone().apply_verbosity_options(**kwargs),
        cli_invocation=CliInvocation.from_context(context))
    status_obj.show()


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#  Clean
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~


# ignore[arg-type]: click code expects click.Context, but we use our own type for better type
# inference. See Context and ContextObjects above.
@main.group(chain=True, invoke_without_command=True, cls=CustomGroup)  # type: ignore[arg-type]
@pass_context
@verbosity_options
@dry_options
def clean(context: Context, **kwargs: Any) -> None:
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

        # Set path to default
        context.params['workdir_root'] = tmt.utils.WORKDIR_ROOT
        # Create another level to the hierarchy so that logging indent is
        # consistent between the command and subcommands
        clean_obj = tmt.Clean(
            logger=context.obj.clean_logger
            .descend(logger_name='clean-images', extra_shift=0)
            .apply_verbosity_options(**kwargs),
            parent=clean_obj,
            cli_invocation=CliInvocation.from_context(context))
        if tmt.utils.WORKDIR_ROOT.exists():
            if not clean_obj.guests():
                exit_code = 1
            if not clean_obj.runs():
                exit_code = 1
        else:
            clean_obj.warn(
                f"Directory '{tmt.utils.WORKDIR_ROOT}' does not exist, "
                f"skipping guest and run cleanup.")
        clean_obj.images()
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
    '-i', '--id', 'id_', metavar="ID",
    help='Run id (name or directory path) to clean workdir of.')
@option(
    '-k', '--keep', type=int, default=None,
    help='The number of latest workdirs to keep, clean the rest.')
@verbosity_options
@dry_options
def clean_runs(
        context: Context,
        workdir_root: str,
        last: bool,
        id_: Optional[str],
        keep: Optional[int],
        **kwargs: Any) -> None:
    """
    Clean workdirs of past runs.

    Remove all runs in '/var/tmp/tmt' by default.
    """
    defined = [last is True, id_ is not None, keep is not None]
    if defined.count(True) > 1:
        raise tmt.utils.GeneralError(
            "Options --last, --id and --keep cannot be used together.")
    if keep is not None and keep < 0:
        raise tmt.utils.GeneralError("--keep must not be a negative number.")
    if not Path(workdir_root).exists():
        raise tmt.utils.GeneralError(f"Path '{workdir_root}' doesn't exist.")

    assert context.obj.clean_logger is not None  # narrow type

    clean_obj = tmt.Clean(
        logger=context.obj.clean_logger
        .descend(logger_name='clean-runs', extra_shift=0)
        .apply_verbosity_options(**kwargs),
        parent=context.obj.clean,
        cli_invocation=CliInvocation.from_context(context))
    context.obj.clean_partials["runs"].append(clean_obj.runs)


@clean.command(name='guests')
@pass_context
@workdir_root_options
@option(
    '-l', '--last', is_flag=True, help='Stop the guest of the last run.')
@option(
    '-i', '--id', 'id_', metavar="ID", default=None,
    help='Run id (name or directory path) to stop the guest of.')
@option(
    '-h', '--how', metavar='METHOD',
    help='Stop guests of the specified provision method.')
@verbosity_options
@dry_options
def clean_guests(
        context: Context,
        workdir_root: str,
        last: bool,
        id_: Optional[int],
        **kwargs: Any) -> None:
    """
    Stop running guests of runs.

    Stop guests of all runs in '/var/tmp/tmt' by default.
    """
    if last and id_ is not None:
        raise tmt.utils.GeneralError(
            "Options --last and --id cannot be used together.")
    if not Path(workdir_root).exists():
        raise tmt.utils.GeneralError(f"Path '{workdir_root}' doesn't exist.")

    assert context.obj.clean_logger is not None  # narrow type

    clean_obj = tmt.Clean(
        logger=context.obj.clean_logger
        .descend(logger_name='clean-guests', extra_shift=0)
        .apply_verbosity_options(**kwargs),
        parent=context.obj.clean,
        cli_invocation=CliInvocation.from_context(context))
    context.obj.clean_partials["guests"].append(clean_obj.guests)


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
#  Lint
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~


# ignore[arg-type]: click code expects click.Context, but we use our own type for better type
# inference. See Context and ContextObjects above.
@main.command(name='lint')  # type: ignore[arg-type]
@pass_context
@filtering_options
@fmf_source_options
@lint_options
@fix_options
@verbosity_options
def lint(
        context: Context,
        list_checks: bool,
        enable_checks: list[str],
        disable_checks: list[str],
        enforce_checks: list[str],
        failed_only: bool,
        outcome_only: tuple[str, ...],
        **kwargs: Any) -> None:
    """
    Check all the present metadata against the specification.

    Combines all the partial linting (tests, plans and stories)
    into one command. Options are applied to all parts of the lint.

    Regular expression can be used to filter metadata by name.
    Use '.' to select tests, plans and stories under the current
    working directory.
    """

    exit_code = do_lint(
        context,
        [tmt.base.Test, tmt.base.Plan, tmt.base.Story],
        list_checks,
        failed_only,
        enable_checks,
        disable_checks,
        enforce_checks,
        [tmt.lint.LinterOutcome(outcome) for outcome in outcome_only],
        **kwargs
        )

    raise SystemExit(exit_code)

# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#  Setup
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~


@main.group(cls=CustomGroup)
def setup(**kwargs: Any) -> None:
    """
    Setup the environment for working with tmt.
    """


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


def setup_completion(shell: str, install: bool) -> None:
    """ Setup completion based on the shell """
    config = tmt.utils.Config()
    # Fish gets installed into its special location where it is automatically
    # loaded.
    if shell == 'fish':
        script = Path('~/.config/fish/completions/tmt.fish').expanduser()
    # Bash and zsh get installed to tmt's config directory.
    else:
        script = Path(config.path) / f'{COMPLETE_SCRIPT}.{shell}'

    # SIM115: Use context handler for opening files. Would not reduce complexity here.
    out = open(script, 'w') if install else sys.stdout  # noqa: SIM115
    subprocess.run(f'{COMPLETE_VARIABLE}={shell}_source tmt',
                   shell=True, stdout=out)

    if install:
        out.close()
        # If requested, modify .bashrc or .zshrc
        if shell != 'fish':
            config_path = Path(f'~/.{shell}rc').expanduser()
            with open(config_path, 'a') as shell_config:
                shell_config.write('\n# Generated by tmt\n')
                shell_config.write(f'source {script}')


@completion.command(name='bash')
@pass_context
@option(
    '--install', '-i', 'install', is_flag=True,
    help="""
         Persistently store the script to tmt's configuration directory and set it up by modifying
         '~/.bashrc'.
         """)
def completion_bash(context: Context, install: bool, **kwargs: Any) -> None:
    """
    Setup shell completions for bash.
    """
    setup_completion('bash', install)


@completion.command(name='zsh')
@pass_context
@option(
    '--install', '-i', 'install', is_flag=True,
    help="""
         Persistently store the script to tmt's configuration directory and set it up by modifying
         '~/.zshrc'.
         """)
def completion_zsh(context: Context, install: bool, **kwargs: Any) -> None:
    """
    Setup shell completions for zsh.
    """
    setup_completion('zsh', install)


@completion.command(name='fish')
@pass_context
@option(
    '--install', '-i', 'install', is_flag=True,
    help="Persistently store the script to '~/.config/fish/completions/tmt.fish'.")
def completion_fish(context: Context, install: bool, **kwargs: Any) -> None:
    """
    Setup shell completions for fish.
    """
    setup_completion('fish', install)
