"""
SSH Executor for command execution on remote guests via SSH.

This module provides the SSHExecutor class that handles command
execution over SSH connections.
"""

import dataclasses
import os
from shlex import quote
from typing import TYPE_CHECKING, Any, Optional, Union

import tmt.log
import tmt.utils
from tmt.utils import Command, CommandOutput, Environment, Path, ShellScript

from . import ExecutionDriver, OnProcessEndCallback, OnProcessStartCallback

if TYPE_CHECKING:
    from tmt.steps.provision import GuestSsh


class SSHExecutor(ExecutionDriver):
    """
    Execute commands on a remote guest via SSH.

    This executor handles SSH connection management, command building,
    and execution over SSH. It extracts SSH-specific execution logic
    from GuestSsh into a dedicated component.
    """

    def __init__(
        self,
        *,
        guest: 'GuestSsh',
        logger: tmt.log.Logger,
    ) -> None:
        """
        Initialize the SSH executor.

        :param guest: the SSH-capable guest this executor operates on.
        :param logger: logger to use for logging.
        """
        super().__init__(guest=guest, logger=logger)
        # Type-narrowed reference to the SSH guest
        self._ssh_guest_ref = guest

    @property
    def _ssh_command(self) -> Command:
        """Get the base SSH command with multiplexing if enabled."""
        return self._ssh_guest_ref._ssh_command

    @property
    def _ssh_target(self) -> str:
        """Get the SSH target (user@host or just host)."""
        return self._ssh_guest_ref._ssh_guest

    @property
    def primary_address(self) -> Optional[str]:
        """Get the primary address of the guest."""
        return self._ssh_guest_ref.primary_address

    def _prepare_environment(
        self, env: Optional[Environment] = None
    ) -> Environment:
        """Prepare environment variables for the command."""
        return self._ssh_guest_ref._prepare_environment(env)

    def _run_guest_command(
        self,
        command: Command,
        **kwargs: Any,
    ) -> CommandOutput:
        """Run a command through the guest's command runner."""
        return self._ssh_guest_ref._run_guest_command(command, **kwargs)

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
        Execute a command on the guest via SSH.

        :param command: the command or shell script to execute.
        :param cwd: execute command in this directory on the guest.
        :param env: environment variables to set before running the command.
        :param friendly_command: nice, human-friendly representation of the command.
        :param test_session: if True, this is the actual test being run.
        :param tty: if True, allocate a pseudo-terminal.
        :param silent: if True, suppress logging of command output.
        :param log: optional logging function for command output.
        :param interactive: if True, run command interactively.
        :param on_process_start: callback when process starts.
        :param on_process_end: callback when process ends.
        :param sourced_files: files to source before running the command.
        :returns: command output.
        """

        sourced_files = sourced_files or []

        # Abort if guest is unavailable
        if self.primary_address is None and not self._ssh_guest_ref.is_dry_run:
            raise tmt.utils.GeneralError('The guest is not available.')

        ssh_command: Command = self._ssh_command

        # Run in interactive mode if requested
        if interactive:
            ssh_command += Command('-t')

        # Force ssh to allocate pseudo-terminal if requested. Without a pseudo-terminal,
        # remote processes spawned by SSH would keep running after SSH process death.
        if test_session or tty:
            ssh_command += Command('-tt')

        # Accumulate all necessary commands - they will form a "shell" script,
        # a single string passed to SSH to execute on the remote machine.
        remote_commands: ShellScript = ShellScript.from_scripts(
            self._prepare_environment(env).to_shell_exports()
        )

        # Change to given directory on guest if cwd provided
        if cwd:
            remote_commands += ShellScript(f'cd {quote(str(cwd))}')

        for file in sourced_files:
            remote_commands += ShellScript(f'source {quote(str(file))}')

        if isinstance(command, Command):
            remote_commands += command.to_script()
        else:
            remote_commands += command

        remote_command = remote_commands.to_element()

        ssh_command += [self._ssh_target, remote_command]

        self.debug(f"Execute command '{remote_command}' on guest '{self.primary_address}'.")

        output = self._run_guest_command(
            ssh_command,
            log=log,
            friendly_command=friendly_command or str(command),
            silent=silent,
            cwd=cwd,
            interactive=interactive,
            on_process_start=on_process_start,
            on_process_end=on_process_end,
            **kwargs,
        )

        # Drop ssh connection closed messages, #2524
        if test_session and output.stdout:
            # Get last line index
            last_line_index = output.stdout.rfind(os.linesep, 0, -2)
            # Drop the connection closed message line, keep the ending lineseparator
            if (
                'Shared connection to ' in output.stdout[last_line_index:]
                or 'Connection to ' in output.stdout[last_line_index:]
            ):
                output = dataclasses.replace(
                    output, stdout=output.stdout[: last_line_index + len(os.linesep)]
                )

        return output

    @property
    def is_ready(self) -> bool:
        """Check if the SSH connection is available."""
        return self.primary_address is not None
