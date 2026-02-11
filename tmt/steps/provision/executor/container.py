"""
Container Executor for command execution in Podman containers.

This module provides the ContainerExecutor class that handles command
execution inside Podman containers.
"""

from shlex import quote
from typing import TYPE_CHECKING, Any, Optional, Union

import tmt.log
import tmt.utils
from tmt.utils import Command, CommandOutput, Environment, Path, ShellScript

from . import ExecutionDriver, OnProcessEndCallback, OnProcessStartCallback

if TYPE_CHECKING:
    from tmt.steps.provision.podman import GuestContainer


class ContainerExecutor(ExecutionDriver):
    """
    Execute commands inside a Podman container.

    This executor handles command execution via 'podman exec',
    extracting container-specific execution logic from GuestContainer
    into a dedicated component.
    """

    def __init__(
        self,
        *,
        guest: 'GuestContainer',
        logger: tmt.log.Logger,
    ) -> None:
        """
        Initialize the container executor.

        :param guest: the container guest this executor operates on.
        :param logger: logger to use for logging.
        """
        super().__init__(guest=guest, logger=logger)
        self._container_guest = guest

    @property
    def container(self) -> Optional[str]:
        """Get the container ID/name."""
        return self._container_guest.container

    def _prepare_environment(
        self, env: Optional[Environment] = None
    ) -> Environment:
        """Prepare environment variables for the command."""
        return self._container_guest._prepare_environment(env)

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
        Execute a command inside the container via podman exec.

        :param command: the command or shell script to execute.
        :param cwd: execute command in this directory inside the container.
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

        if not self.container and not self._container_guest.is_dry_run:
            raise tmt.utils.ProvisionError('Could not execute without provisioned container.')

        podman_command = Command('exec')

        # Accumulate all necessary commands - they will form a "shell" script,
        # a single string passed to a shell executed inside the container.
        script = ShellScript.from_scripts(self._prepare_environment(env).to_shell_exports())

        # Change to given directory on guest if cwd provided
        if cwd is not None:
            script += ShellScript(f'cd {quote(str(cwd))}')

        for file in sourced_files:
            script += ShellScript(f'source {quote(str(file))}')

        if isinstance(command, Command):
            script += command.to_script()
        else:
            script += command

        # Run in interactive mode if requested
        if interactive:
            podman_command += ['-it']
        # Run with a `tty` if requested
        elif tty:
            podman_command += ['-t']

        podman_command += [
            self.container or 'dry',
        ]

        podman_command += script.to_shell_command()

        # Note that we MUST run commands via bash, so variables work as expected
        return self._container_guest.podman(
            podman_command,
            log=log if log else self._container_guest._command_verbose_logger,
            friendly_command=friendly_command or str(command),
            silent=silent,
            interactive=interactive,
            on_process_start=on_process_start,
            on_process_end=on_process_end,
            **kwargs,
        )

    @property
    def is_ready(self) -> bool:
        """Check if the container is available."""
        return self.container is not None
