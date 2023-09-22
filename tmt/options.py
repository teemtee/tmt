""" Common options and the MethodCommand class """

import contextlib
import dataclasses
import re
import textwrap
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Sequence, Type, Union

import click

import tmt.lint
import tmt.log
import tmt.utils

# When dealing with older Click packages (I'm looking at you, Python 3.6),
# we need to define FC on our own.
try:
    from click.decorators import FC

except ImportError:
    from typing import TypeVar

    FC = TypeVar('FC', bound=Union[Callable[..., Any], click.Command])  # type: ignore[misc]


if TYPE_CHECKING:
    import tmt.cli
    import tmt.utils


@dataclasses.dataclass(frozen=True)
class Deprecated:
    """ Version information and hint for obsolete options """
    since: str
    hint: Optional[str] = None

    @property
    def rendered(self) -> str:
        message = f"The option is deprecated since {self.since}"

        if self.hint:
            message = f'{message}, {self.hint}'

        return f'{message}.'


MethodDictType = Dict[str, click.core.Command]

# Originating in click.decorators, an opaque type describing "decorator" functions
# produced by click.option() calls: not options, but decorators, functions that attach
# options to a given command.
# Since click.decorators does not have a dedicated type for this purpose, we need
# to construct it on our own, but we can re-use a typevar click.decorators has.
_ClickOptionDecoratorType = Callable[[FC], FC]
# The type above is a generic type, `FC` being a typevar, so we have two options:
# * each place using the type would need to fill the variable, i.e. add [foo]`, or
# * we could do that right here, because right now, we don't care too much about
# what this `foo` type actually is - what's important is the identity, return type
# matches the type of the argument.
ClickOptionDecoratorType = _ClickOptionDecoratorType[Any]


def option(
        *param_decls: str,
        # Following parameters are inherited from click.option()/Option/Parameter.
        # May allow stricter types than the original, because tmt code base does not
        # care for every Click use case.
        show_default: bool = False,
        is_flag: bool = False,
        multiple: bool = False,
        count: bool = False,
        type: Optional[Union[click.Choice, Any]] = None,
        help: Optional[str] = None,
        required: bool = False,
        default: Optional[Any] = None,
        nargs: Optional[int] = None,
        metavar: Optional[str] = None,
        prompt: Optional[str] = None,
        envvar: Optional[str] = None,
        # Following parameters are our additions.
        choices: Optional[Sequence[str]] = None,
        deprecated: Optional[Deprecated] = None) -> ClickOptionDecoratorType:
    """
    Attaches an option to the command.

    This is a wrapper for :py:func:`click.option`, its parameters have the same
    meaning as those of ``click.option()``, and are passed to ``click.option()``,
    with the exception of ``deprecated`` parameter.

    :param choices: if set, it sets ``type`` of the option to
        :py:class:`click.Choices`, and limits option values to those
        listed in ``choices``.
    :param deprecated: if set, it is rendered and appended to ``help``. This
        parameter is **not** passed to :py:func:`click.option`.
    """

    if help:
        help = textwrap.dedent(help)

    # Add a deprecation warning for obsoleted options
    if deprecated:
        if help:
            help += ' ' + deprecated.rendered

        else:
            help = deprecated.rendered

    if choices is not None:
        type = click.Choice(choices)

    # Add a metavar listing choices unless an explicit metavar has been provided
    if isinstance(type, click.Choice) and metavar is None:
        metavar = '|'.join(type.choices)

    # Instead of repeating all keyword parameters, use locals(), they are all there
    # already, and it's a dictionary - just don't forget to remove names that are
    # not accepted by click and the positional parameter.
    kwargs = locals().copy()
    kwargs.pop('param_decls')
    kwargs.pop('choices')
    kwargs.pop('deprecated')

    return click.option(*param_decls, **kwargs)


# Verbose, debug and quiet output
VERBOSITY_OPTIONS: List[ClickOptionDecoratorType] = [
    option(
        '-v', '--verbose', count=True, default=0,
        help='Show more details. Use multiple times to raise verbosity.'),
    option(
        '-d', '--debug', count=True, default=0,
        help='Provide debugging information. Repeat to see more details.'),
    option(
        '-q', '--quiet', is_flag=True,
        help='Be quiet. Exit code is just enough for me.'),
    option(
        '--log-topic',
        choices=[topic.value for topic in tmt.log.Topic],
        multiple=True,
        help='If specified, --debug and --verbose would emit logs also for these topics.')
    ]

# Force and dry actions
DRY_OPTIONS: List[ClickOptionDecoratorType] = [
    option(
        '-n', '--dry', is_flag=True,
        help='Run in dry mode. No changes, please.'),
    ]

FORCE_DRY_OPTIONS: List[ClickOptionDecoratorType] = [
    option(
        '-f', '--force', is_flag=True,
        help='Overwrite existing files and step data.'),
    *DRY_OPTIONS]


# Fix action
FIX_OPTIONS: List[ClickOptionDecoratorType] = [
    option('-F', '--fix', is_flag=True, help='Attempt to fix all discovered issues.')
    ]

WORKDIR_ROOT_OPTIONS: List[ClickOptionDecoratorType] = [
    option(
        '--workdir-root', metavar='PATH', envvar='TMT_WORKDIR_ROOT',
        default=tmt.utils.WORKDIR_ROOT,
        help=f"""
             Path to root directory containing run workdirs.
             Defaults to '{tmt.utils.WORKDIR_ROOT}'.
             """)
    ]


FILTER_OPTIONS: List[ClickOptionDecoratorType] = [
    click.argument(
        'names', nargs=-1, metavar='[REGEXP|.]'),
    option(
        '-f', '--filter', 'filters', metavar='FILTER', multiple=True,
        help="Apply advanced filter (see 'pydoc fmf.filter')."),
    option(
        '-c', '--condition', 'conditions', metavar="EXPR", multiple=True,
        help="Use arbitrary Python expression for filtering."),
    option(
        '--enabled', is_flag=True,
        help="Show only enabled tests, plans or stories."),
    option(
        '--disabled', is_flag=True,
        help="Show only disabled tests, plans or stories."),
    option(
        '--link', 'links', metavar="RELATION:TARGET", multiple=True,
        help="""
             Filter by linked objects (regular expressions are supported for both relation and
             target).
             """),
    option(
        '-x', '--exclude', 'exclude', metavar='[REGEXP]', multiple=True,
        help="Exclude a regular expression from search result."),
    ]


FILTER_OPTIONS_LONG: List[ClickOptionDecoratorType] = [
    click.argument(
        'names', nargs=-1, metavar='[REGEXP|.]'),
    option(
        '--filter', 'filters', metavar='FILTER', multiple=True,
        help="Apply advanced filter (see 'pydoc fmf.filter')."),
    option(
        '--condition', 'conditions', metavar="EXPR", multiple=True,
        help="Use arbitrary Python expression for filtering."),
    option(
        '--enabled', is_flag=True,
        help="Show only enabled tests, plans or stories."),
    option(
        '--disabled', is_flag=True,
        help="Show only disabled tests, plans or stories."),
    option(
        '--link', 'links', metavar="RELATION:TARGET", multiple=True,
        help="""
             Filter by linked objects (regular expressions are supported for both relation and
             target).
             """),
    option(
        '--exclude', 'exclude', metavar='[REGEXP]', multiple=True,
        help="Exclude a regular expression from search result."),
    ]


STORY_FLAGS_FILTER_OPTIONS: List[ClickOptionDecoratorType] = [
    option(
        '--implemented', is_flag=True,
        help='Implemented stories only.'),
    option(
        '--unimplemented', is_flag=True,
        help='Unimplemented stories only.'),
    option(
        '--verified', is_flag=True,
        help='Stories verified by tests.'),
    option(
        '--unverified', is_flag=True,
        help='Stories not verified by tests.'),
    option(
        '--documented', is_flag=True,
        help='Documented stories only.'),
    option(
        '--undocumented', is_flag=True,
        help='Undocumented stories only.'),
    option(
        '--covered', is_flag=True,
        help='Covered stories only.'),
    option(
        '--uncovered', is_flag=True,
        help='Uncovered stories only.'),
    ]

FMF_SOURCE_OPTIONS: List[ClickOptionDecoratorType] = [
    option(
        '--source', is_flag=True, help="Select by fmf source file names instead of object names."
        )
    ]

REMOTE_PLAN_OPTIONS: List[ClickOptionDecoratorType] = [
    option('-s', '--shallow', is_flag=True, help='Do not clone remote plan.')
    ]


_lint_outcomes = [member.value for member in tmt.lint.LinterOutcome.__members__.values()]

LINT_OPTIONS: List[ClickOptionDecoratorType] = [
    option(
        '--list-checks',
        is_flag=True,
        help='List all available checks.'),
    option(
        '--enable-check',
        'enable_checks',
        metavar='CHECK-ID',
        multiple=True,
        type=str,
        help='Run only checks mentioned by this option.'),
    option(
        '--disable-check',
        'disable_checks',
        metavar='CHECK-ID',
        multiple=True,
        type=str,
        help='Do not run checks mentioned by this option.'),
    option(
        '--enforce-check',
        'enforce_checks',
        metavar='CHECK-ID',
        multiple=True,
        type=str,
        help='Consider linting as failed if any of the mentioned checks is not a pass.'),
    option(
        '--failed-only',
        is_flag=True,
        help='Display only tests/plans/stories that fail a check.'),
    option(
        '--outcome-only',
        multiple=True,
        choices=_lint_outcomes,
        help='Display only checks with the given outcome.')
    ]


ENVIRONMENT_OPTIONS: List[ClickOptionDecoratorType] = [
    option(
        '-e', '--environment',
        metavar='KEY=VALUE|@FILE',
        multiple=True,
        help="""
             Set environment variable. Can be specified multiple times. The "@" prefix marks a file
             to load (yaml or dotenv formats supported).
             """),
    option(
        '--environment-file',
        metavar='FILE|URL',
        multiple=True,
        help="""
             Set environment variables from file or url (yaml or dotenv formats are supported). Can
             be specified multiple times.
             """)
    ]


def create_options_decorator(options: List[ClickOptionDecoratorType]) -> Callable[[FC], FC]:
    def common_decorator(fn: FC) -> FC:
        for option in reversed(options):
            fn = option(fn)

        return fn

    return common_decorator


def show_step_method_hints(
        step_name: str,
        how: str,
        logger: tmt.log.Logger) -> None:
    """
    Show hints about available step methods' installation

    The logger will be used to output the hints to the terminal, hence
    it must be an instance of a subclass of tmt.utils.Common (info method
    must be available).
    """
    if step_name == 'provision':
        if how == 'virtual':
            logger.info(
                'hint', "Install 'tmt+provision-virtual' "
                        "to run tests in a virtual machine.", color='blue')
        if how == 'container':
            logger.info(
                'hint', "Install 'tmt+provision-container' "
                        "to run tests in a container.", color='blue')
        if how == 'minute':
            logger.info(
                'hint', "Install 'tmt-redhat-provision-minute' "
                        "to run tests in 1minutetip OpenStack backend. "
                        "(Available only from the internal COPR repository.)",
                        color='blue')
        logger.info(
            'hint', "Use the 'local' method to execute tests "
                    "directly on your localhost.", color='blue')
        logger.info(
            'hint', "See 'tmt run provision --help' for all "
                    "available provision options.", color='blue')
    elif step_name == 'report':
        if how == 'junit':
            logger.info(
                'hint', "Install 'tmt+report-junit' to write results "
                        "in JUnit format.", color='blue')
        logger.info(
            'hint', "Use the 'display' method to show test results "
                    "on the terminal.", color='blue')
        logger.info(
            'hint', "See 'tmt run report --help' for all "
                    "available report options.", color='blue')


def create_method_class(methods: MethodDictType) -> Type[click.Command]:
    """
    Create special class to handle different options for each method

    Accepts dictionary with method names and corresponding commands:
    For example: {'fmf', <click.core.Command object at 0x7f3fe04fded0>}
    Methods should be already sorted according to their priority.
    """

    def is_likely_subcommand(arg: str, subcommands: List[str]) -> bool:
        """ Return true if arg is the beginning characters of a subcommand """
        return any(subcommand.startswith(arg) for subcommand in subcommands)

    class MethodCommand(click.Command):
        _method: Optional[click.Command] = None

        def _check_method(self, context: 'tmt.cli.Context', args: List[str]) -> None:
            """ Manually parse the --how option """
            how = None
            subcommands = (
                tmt.steps.STEPS + tmt.steps.ACTIONS + ['tests', 'plans'])

            def _find_option_by_arg(arg: str) -> Optional[click.Parameter]:
                for option in self.params:
                    if arg in option.opts or arg in option.secondary_opts:
                        return option
                return None

            def _find_how(args: List[str]) -> Optional[str]:
                while args:
                    arg = args.pop(0)

                    # Handle '--how method' or '-h method'
                    if arg in ['--how', '-h']:
                        # Found `-h/--how foo`, next argument is how'
                        return args.pop(0)

                    # Handle '--how=method'
                    if arg.startswith('--how='):
                        return re.sub('^--how=', '', arg)

                    # Handle '-hmethod'
                    if arg.startswith('-h'):
                        return re.sub('^-h ?', '', arg)

                    # Handle anything that looks like an option
                    if arg.startswith('-'):
                        # Is it a --foo or --foo=bar?
                        match = re.match(r'(--[a-z\-]+)(=.*)?', arg)
                        if match:
                            if match.group(2):
                                # Found option like '--foo=bar'
                                continue
                        else:
                            # Or is it a -f?
                            match = re.match(r'(-[a-z])', arg)
                            if match is None:
                                # Found unexpected option format
                                return None
                        option_name: str = match.group(1)
                        option = _find_option_by_arg(option_name)
                        if option is None:
                            # Unknown option? Probably remain silent, Click should report it in.
                            return None

                        # Options, unlike arguments, may not consume any additional arguments
                        if isinstance(option, click.core.Option):
                            if option.is_flag:
                                # Found a flag
                                continue
                            if option.count:
                                # Found options like '-ddddd'
                                continue

                        # Consume all remaining arguments. Think `ls /foo /bar ...`, it's not
                        # possible to tell which of these is an actual argument or misspelled
                        # subcommand name.
                        if option.nargs == -1:
                            # Found option consuming all arguments
                            return None
                        if option.nargs == 0:
                            # Found option with no arguments
                            continue

                        # Consume the given number of arguments
                        for _ in range(option.nargs):
                            args.pop(0)

                        continue

                    if is_likely_subcommand(arg, subcommands):
                        # Found a subcommand
                        return None

                    # We're left with a string that does not start with `-`, and which has not
                    # been claimed by an option. It is highly likely this is a misspelled
                    # subcommand name.
                    raise tmt.utils.SpecificationError(
                        f"Invalid subcommand of 'run' found: '{arg}'.")

                return None

            with contextlib.suppress(IndexError):
                how = _find_how(args[:])

            # Find method with the first matching prefix
            if how is not None:
                for method in methods:
                    if method.startswith(how):
                        self._method = methods[method]
                        break

            if how and self._method is None:
                # Use run for logging, steps may not be initialized yet
                assert context.obj.run is not None  # narrow type
                assert self.name is not None  # narrow type
                show_step_method_hints(self.name, how, context.obj.run._logger)
                raise tmt.utils.SpecificationError(
                    f"Unsupported {self.name} method '{how}'.")

        def parse_args(  # type: ignore[override]
                self,
                context: 'tmt.cli.Context',
                args: List[str]
                ) -> List[str]:
            self._check_method(context, args)
            if self._method is not None:
                return self._method.parse_args(context, args)
            return super().parse_args(context, args)

        def get_help(self, context: 'tmt.cli.Context') -> str:  # type: ignore[override]
            if self._method is not None:
                return self._method.get_help(context)
            return super().get_help(context)

        def invoke(self, context: 'tmt.cli.Context') -> Any:  # type: ignore[override]
            if self._method:
                return self._method.invoke(context)
            return super().invoke(context)

    return MethodCommand
