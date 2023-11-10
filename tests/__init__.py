from collections.abc import Mapping, Sequence
from typing import IO, Any, Optional, Union

import click.core
import click.testing


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

    from tmt.base import Core, Plan, Run, Story, Test, Tree
    from tmt.utils import Common, MultiInvokableCommon

    for klass in (
            Core, Run, Tree, Test, Plan, Story,
            Common, MultiInvokableCommon):

        klass.cli_invocation = None


class CliRunner(click.testing.CliRunner):
    def invoke(
            self,
            cli: click.core.BaseCommand,
            args: Optional[Union[str, Sequence[str]]] = None,
            input: Optional[Union[str, bytes, IO]] = None,
            env: Optional[Mapping[str, Optional[str]]] = None,
            catch_exceptions: bool = True,
            color: bool = False,
            **extra: Any) -> click.testing.Result:
        reset_common()

        return super().invoke(
            cli,
            args=args,
            input=input,
            env=env,
            catch_exceptions=catch_exceptions,
            color=color,
            **extra)
