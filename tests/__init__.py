import contextlib
import functools
import os
from collections.abc import Iterable, Iterator, Mapping
from typing import IO, Any, Callable, Optional, Protocol, TypeVar, Union, cast

import click.core
import click.testing
import jq as _jq

import tmt.__main__
import tmt._compat.importlib.metadata
import tmt.cli._root
from tmt._compat.typing import ParamSpec
from tmt.utils import Path

_CLICK_VERSION = tuple(
    int(_s) for _s in tmt._compat.importlib.metadata.version('click').split('.')
)

T = TypeVar('T')
P = ParamSpec('P')


def reset_common() -> None:
    """
    Reset CLI invocation storage of classes derived from :py:class:`tmt.utils.Common`

    As CLI invocations are stored in class-level attributes, before each
    invocation of CLI in a test, we must reset these attributes to pretend the
    CLI is invoked for the very first time. Without this, after the very first
    invocation, subsequent CLI invocations would "inherit" options from the
    previous ones.

    A helper function to clear invocations of the "usual suspects". Classes that
    accept CLI options are reset.
    """

    from tmt.base.core import Core, Run, Story, Test, Tree
    from tmt.base.plan import Plan
    from tmt.utils import Common, MultiInvokableCommon

    for klass in (Core, Run, Tree, Test, Plan, Story, Common, MultiInvokableCommon):
        klass.cli_invocation = None


@contextlib.contextmanager
def cwd(path: Path) -> Iterator[Path]:
    """
    A context manager switching the current working directory to a given path.

    .. warning::

        Changing the current working directory can have unexpected
        consequences in a multithreaded environment.
    """

    cwd = Path.cwd()

    os.chdir(path)

    try:
        yield path

    finally:
        os.chdir(cwd)


def with_cwd(path: Path) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """
    Decorate a test to have it run in the given path as its CWD.
    """

    def _with_cwd(fn: Callable[P, T]) -> Callable[P, T]:
        @functools.wraps(fn)
        def __with_cwd(*args: P.args, **kwargs: P.kwargs) -> T:
            with cwd(path):
                return fn(*args, **kwargs)

        return __with_cwd

    return _with_cwd


def jq_all(data: Any, query: str) -> Iterable[Any]:
    """
    Apply a jq filter on given data, and return the product.
    """

    return cast(Iterable[Any], _jq.compile(query).input(data).all())


class RunTmt(Protocol):
    """
    A type representing :py:meth:`CliRunner.invoke`.

    Defined as a protocol because the method is available as a test
    fixture, and it needs to have a type annotation.
    """

    def __call__(
        self,
        *args: Union[str, Path],
        command: Optional[click.BaseCommand] = None,
        input: Optional[Union[str, bytes, IO[Any]]] = None,
        env: Optional[Mapping[str, Optional[str]]] = None,
        catch_exceptions: bool = True,
        color: bool = False,
        **kwargs: Any,
    ) -> click.testing.Result:
        pass


class CliRunner(click.testing.CliRunner):
    def __init__(self) -> None:
        if _CLICK_VERSION >= (8, 2, 0):
            super().__init__(charset='utf-8', echo_stdin=False)

        else:
            super().__init__(charset='utf-8', echo_stdin=False, mix_stderr=False)

    def invoke(  # type: ignore[override]
        self,
        *args: Union[str, Path],
        command: Optional[click.BaseCommand] = None,
        input: Optional[Union[str, bytes, IO[Any]]] = None,
        env: Optional[Mapping[str, Optional[str]]] = None,
        catch_exceptions: bool = True,
        color: bool = False,
        **kwargs: Any,
    ) -> click.testing.Result:
        reset_common()

        tmt.__main__.import_cli_commands()

        command = command or tmt.cli._root.main

        return super().invoke(
            command,
            args=[str(arg) for arg in args],
            input=input,
            env=env,
            catch_exceptions=catch_exceptions,
            color=color,
            **kwargs,
        )
