"""
Local Executor for command execution on localhost.

This module provides the LocalExecutor class that handles command
execution on the local machine.
"""

import shlex
from typing import TYPE_CHECKING, Any, Optional, Union

import tmt.log
import tmt.utils
from tmt.utils import Command, CommandOutput, Environment, Path, ShellScript

from . import ExecutionDriver, OnProcessEndCallback, OnProcessStartCallback

if TYPE_CHECKING:
    from tmt.steps.provision.local import GuestLocal


class LocalExecutor(ExecutionDriver):
    """
    Execute commands on the local machine.

    This executor handles command execution locally, without any
    remote connection. It extracts local execution logic from
    GuestLocal into a dedicated component.
    """

    def __init__(
        self,
        *,
        guest: 'GuestLocal',
        logger: tmt.log.Logger,
    ) -> None:
        """
        Initialize the local executor.

        :param guest: the local guest this executor operates on.
        :param logger: logger to use for logging.
        """
        super().__init__(guest=guest, logger=logger)
        self._local_guest = guest

    def _prepare_environment(
        self, env: Optional[Environment] = None
    ) -> Environment:
        """Prepare environment variables for the command."""
        environment = Environment()
        environment.update(env or {})
        if self._local_guest.parent:
            environment.update(self._local_guest.parent.plan.environment)
        return environment

    def _run_guest_command(
        self,
        command: Command,
        **kwargs: Any,
    ) -> CommandOutput:
        """Run a command through the guest's command runner."""
        return self._local_guest._run_guest_command(command, **kwargs)

    def execute(
        self,
        command: Union[Command, ShellScript],
        *,
        cwd: Optional[Path] = None,
        env: Optional[Environment] = None,
        friendly_command: Optional[str] = None,
        test_session: bool = False,
        tty: bool = False,
        silent: bool = False,
        log: Optional[tmt.log.LoggingFunction] = None,
        interactive: bool = False,
        on_process_start: Optional[OnProcessStartCallback] = None,
        on_process_end: Optional[OnProcessEndCallback] = None,
        sourced_files: Optional[list[Path]] = None,
        **kwargs: Any,
    ) -> CommandOutput:
        """
        Execute a command on localhost.

        :param command: the command or shell script to execute.
        :param cwd: execute command in this directory.
        :param env: environment variables to set before running the command.
        :param friendly_command: nice, human-friendly representation of the command.
        :param test_session: if True, this is the actual test being run.
        :param tty: if True, allocate a pseudo-terminal (ignored for local).
        :param silent: if True, suppress logging of command output.
        :param log: optional logging function for command output.
        :param interactive: if True, run command interactively.
        :param on_process_start: callback when process starts.
        :param on_process_end: callback when process ends.
        :param sourced_files: files to source before running the command.
        :returns: command output.
        """

        sourced_files = sourced_files or []

        # Prepare the environment (plan/cli variables override)
        environment = self._prepare_environment(env)

        if tty:
            self._logger.warn(
                "Ignoring requested tty, not supported by the 'local' provision plugin."
            )

        # Prepend source commands
        for file in reversed(sourced_files):
            if isinstance(command, Command):
                command = (
                    ShellScript(f'source {shlex.quote(str(file))}').to_shell_command()
                    + Command("&&")
                    + command
                )
            else:
                command = ShellScript(f'source {shlex.quote(str(file))}') + command

        actual_command = command if isinstance(command, Command) else command.to_shell_command()

        # Run the command under the prepared environment
        return self._run_guest_command(
            actual_command,
            env=environment,
            log=log,
            friendly_command=friendly_command or str(command),
            silent=silent,
            cwd=cwd,
            interactive=interactive,
            on_process_start=on_process_start,
            on_process_end=on_process_end,
            **kwargs,
        )

    @property
    def is_ready(self) -> bool:
        """Local executor is always ready."""
        return True
