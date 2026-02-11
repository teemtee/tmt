"""
Mock Executor for command execution in Mock shell environments.

This module provides the MockExecutor class that handles command
execution inside Mock shell environments for RPM building/testing.
"""

import shlex
from typing import TYPE_CHECKING, Any, Optional, Union

import tmt.log
import tmt.utils
from tmt.utils import Command, CommandOutput, Environment, Path, ShellScript

from . import ExecutionDriver, OnProcessEndCallback, OnProcessStartCallback

if TYPE_CHECKING:
    from tmt.steps.provision.mock import GuestMock


class MockExecutor(ExecutionDriver):
    """
    Execute commands inside a Mock shell environment.

    This executor handles command execution via mock's persistent shell,
    extracting mock-specific execution logic from GuestMock into a
    dedicated component.
    """

    def __init__(
        self,
        *,
        guest: 'GuestMock',
        logger: tmt.log.Logger,
    ) -> None:
        """
        Initialize the mock executor.

        :param guest: the mock guest this executor operates on.
        :param logger: logger to use for logging.
        """
        super().__init__(guest=guest, logger=logger)
        self._mock_guest = guest

    @property
    def mock_shell(self) -> Any:
        """Get the mock shell instance."""
        return self._mock_guest.mock_shell

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
        Execute a command in a running mock shell for increased speed.

        :param command: the command or shell script to execute.
        :param cwd: execute command in this directory inside mock.
        :param env: environment variables to set before running the command.
        :param friendly_command: nice, human-friendly representation of the command.
        :param test_session: if True, this is the actual test being run.
        :param tty: if True, allocate a pseudo-terminal (ignored for mock).
        :param silent: if True, suppress logging of command output.
        :param log: optional logging function for command output.
        :param interactive: if True, run command interactively.
        :param on_process_start: callback when process starts.
        :param on_process_end: callback when process ends.
        :param sourced_files: files to source before running the command.
        :returns: command output.
        """

        sourced_files = sourced_files or []

        if self.mock_shell.mock_shell is None:
            self.mock_shell.enter_shell()

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

        if on_process_start:
            assert self.mock_shell.mock_shell is not None  # narrow type
            # ignore[arg-type]: `on_process_start` expects `Popen[bytes]`,
            # `mock_shell` is `Popen[str]`. Callbacks are not supposed to
            # communicate with the process.
            on_process_start(
                actual_command,
                self.mock_shell.mock_shell,  # type: ignore[arg-type]
                self._logger,
            )

        command_output = CommandOutput(
            *self.mock_shell.execute(
                actual_command,
                cwd=cwd,
                env=env,
                friendly_command=friendly_command or str(command),
                logger=self._logger,
                **kwargs,
            )
        )

        if on_process_end is not None:
            try:
                on_process_end(
                    actual_command,
                    self.mock_shell.mock_shell,  # type: ignore[arg-type]
                    command_output,
                    self._logger,
                )
            except Exception as exc:
                tmt.utils.show_exception_as_warning(
                    exception=exc,
                    message=f'On-process-end callback {on_process_end.__name__} failed.',
                    logger=self._logger,
                )

        return command_output

    @property
    def is_ready(self) -> bool:
        """Check if the mock shell is available."""
        return self.mock_shell is not None
