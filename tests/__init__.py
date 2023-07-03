from typing import IO, Any, Mapping, Optional, Sequence, Union

import click.core
import click.testing


def reset_common() -> None:
    from tmt.base import Core, Plan, Run, Story, Test, Tree
    from tmt.utils import Common, MultiInvokableCommon

    for klass in (
            Core, Run, Tree, Test, Plan, Story,
            Common, MultiInvokableCommon):

        klass.cli_invocation = None


class CLIRunner(click.testing.CliRunner):
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
