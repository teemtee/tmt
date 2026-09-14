import contextlib
import functools
import importlib.metadata
import os
from collections.abc import Generator, Iterator, Mapping, Sequence
from typing import IO, Any, Callable, Optional, Protocol, TypeVar, Union

import _pytest.monkeypatch
import click.core
import click.testing
import pytest

import tmt.__main__
import tmt.cli._root
from tmt._compat.typing import ParamSpec
from tmt._compat.typing import TypeAlias as TypeAlias
from tmt.log import Logger as Logger
from tmt.utils import Command, Path, RawCommandElement

_CLICK_VERSION = tuple(int(_s) for _s in importlib.metadata.version('click').split('.'))

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

    from tmt.base.core import Core, Story, Test, Tree
    from tmt.base.plan import Plan
    from tmt.base.run import Run
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

    original_cwd = Path.cwd()

    os.chdir(path)

    try:
        yield path

    finally:
        os.chdir(original_cwd)


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


def with_fmf_root(path: Path) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """
    Decorated test will run its ``tmt`` commands in the given fmf root.

    A mere redress of the actual :py:meth:`pytest.mark.parametrize` decorator
    with the right parameters, parametrizing the :py:func:`fixture_fmf_root`
    fixture with the path. The fixture then delivers the path to the
    :py:func:`fixture_run_tmt` fixture to be included by default in all
    ``tmt`` calls.

    It is possible to combine this decorator with parametrization of
    other test inputs - just use both decorators:

    .. code-block:: python

        @with_fmf_root(...)
        @pytest.mark.parametrize(['foo', 'bar'], ...)
        def test_baz(foo, bar, fmf_root):
            ...
    """

    def _with_fmf_root(fn: Callable[P, T]) -> Callable[P, T]:
        return pytest.mark.parametrize('fmf_root', [path], indirect=['fmf_root'])(fn)

    return _with_fmf_root


@contextlib.contextmanager
def not_feeling_safe(monkeypatch: _pytest.monkeypatch.MonkeyPatch) -> Generator[None]:
    """
    A context manager that disables the "feeling safe" mode.

    Use in a test that needs to verify interaction with the "feeling
    safe" mode. For convenience, the mode might be enabled globally for
    all tests, which may mess with expectations of a particular test.
    """

    with monkeypatch.context():
        monkeypatch.delenv('TMT_FEELING_SAFE', raising=False)
        monkeypatch.delenv('TMT_ALLOW_UNSAFE_BEHAVIOR', raising=False)

        yield


class RunTmt(Protocol):
    """
    A type representing :py:meth:`CliRunner.invoke`.

    Defined as a protocol because the method is available as a test
    fixture, and it needs to have a type annotation.
    """

    def __call__(
        self,
        *args: RawCommandElement,
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
        *args: RawCommandElement,
        command: Optional[click.BaseCommand] = None,
        extra_tmt_options: Optional[Sequence[RawCommandElement]] = None,
        input: Optional[Union[str, bytes, IO[Any]]] = None,
        env: Optional[Mapping[str, Optional[str]]] = None,
        catch_exceptions: bool = True,
        color: bool = False,
        **kwargs: Any,
    ) -> click.testing.Result:
        reset_common()

        tmt.__main__.import_cli_commands()

        command = command or tmt.cli._root.main
        options = Command(*(*(extra_tmt_options or []), *args))

        return super().invoke(
            command,
            args=options.to_popen(),
            input=input,
            env=env,
            catch_exceptions=catch_exceptions,
            color=color,
            **kwargs,
        )
