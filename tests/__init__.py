from collections.abc import Mapping
from typing import IO, Any, Optional, Protocol, Union

import click.core
import click.testing

import tmt.__main__
import tmt.cli._root


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

    from tmt.base.core import Core, Plan, Run, Story, Test, Tree
    from tmt.utils import Common, MultiInvokableCommon

    for klass in (Core, Run, Tree, Test, Plan, Story, Common, MultiInvokableCommon):
        klass.cli_invocation = None


class RunTmt(Protocol):
    """
    A type representing :py:meth:`CliRunner.invoke`.

    Defined as a protocol because the method is available as a test
    fixture, and it needs to have a type annotation.
    """

    def __call__(
        self,
        *args: str,
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
        super().__init__(charset='utf-8', echo_stdin=False)

    def invoke(  # type: ignore[override]
        self,
        *args: str,
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
            args=args,
            input=input,
            env=env,
            catch_exceptions=catch_exceptions,
            color=color,
            **kwargs,
        )
