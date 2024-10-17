""" Basic classes and code for tmt command line interface """

import collections
import dataclasses
import enum
import functools
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, Callable, Optional, TypeVar

import click
import fmf
import fmf.utils

import tmt
import tmt.base
import tmt.log
import tmt.plugins
import tmt.utils
import tmt.utils.rest

if TYPE_CHECKING:
    from tmt._compat.typing import Concatenate, ParamSpec

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

#: A logger to use for exception logging.
#:
#: .. warning::
#:
#:    This logger should be used with utmost care for logging exceptions
#:    only, no other traffic should be allowed. On top of that, the
#:    exception logging is handled by a dedicated function,
#:    :py:func:`tmt.utils.show_exception` - if you find yourself in need
#:    of logging an exception somewhere in the code, and you think about
#:    using this logger or calling ``show_exception()`` explicitly,
#:    it is highly likely you are not on the right track.
EXCEPTION_LOGGER: tmt.log.Logger = _BOOTSTRAP_LOGGER


# Explore available plugins (need to detect all supported methods first)
tmt.plugins.explore(_BOOTSTRAP_LOGGER)


class TmtExitCode(enum.IntEnum):
    # Quoting the specification:

    #: At least one test passed, there was no fail, warn or error.
    SUCCESS = 0

    #: There was a fail or warn identified, but no error.
    FAIL = 1

    #: Errors occurred during test execution.
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

    @functools.cached_property
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
            (option, tmt.utils.rest.render_rst(help, _BOOTSTRAP_LOGGER))
            for option, help in rows
            ]

        super().write_dl(rows, col_max=col_max, col_spacing=col_spacing)


click.Context.formatter_class = HelpFormatter
