"""
Executor abstraction for command execution on guests.

This module provides the ExecutionDriver abstraction that separates
command execution logic from guest connectivity, enabling cleaner
support for different execution strategies (immediate vs deferred).

Classes:
    ExecutionDriver: Base abstraction for command execution
    DeferrableExecutor: Executor that supports deferred/batched execution
"""

import abc
from typing import TYPE_CHECKING, Any, Optional, Union

import tmt.log
import tmt.utils
from tmt.utils import Command, CommandOutput, Environment, Path, ShellScript

if TYPE_CHECKING:
    from tmt.steps.provision import Guest


OnProcessStartCallback = tmt.utils.OnProcessStartCallback
OnProcessEndCallback = tmt.utils.OnProcessEndCallback


class ExecutionDriver(abc.ABC):
    """
    Base abstraction for command execution on a guest.

    Executors encapsulate HOW commands are executed, separated from
    the Guest which represents WHAT system is being targeted.

    This follows the Strategy pattern - different executors can be
    swapped to change execution behavior without modifying the Guest.
    """

    def __init__(
        self,
        *,
        guest: 'Guest',
        logger: tmt.log.Logger,
    ) -> None:
        """
        Initialize the executor.

        :param guest: the guest this executor operates on.
        :param logger: logger to use for logging.
        """
        self.guest = guest
        self._logger = logger

    def debug(self, message: str, *args: Any, **kwargs: Any) -> None:
        """Log a debug message."""
        self._logger.debug(message, *args, **kwargs)

    def info(self, message: str, *args: Any, **kwargs: Any) -> None:
        """Log an info message."""
        self._logger.info(message, *args, **kwargs)

    @abc.abstractmethod
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
        Execute a command and return the output.

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
        raise NotImplementedError

    @property
    @abc.abstractmethod
    def is_ready(self) -> bool:
        """
        Check if the executor is ready to run commands.

        :returns: True if the executor can accept commands.
        """
        raise NotImplementedError

    def prepare(self) -> None:
        """
        Prepare the executor for command execution.

        Optional hook for executors that need setup before use.
        """
        pass

    def cleanup(self) -> None:
        """
        Cleanup executor resources.

        Optional hook for executors that need cleanup after use.
        """
        pass


class DeferrableExecutor(ExecutionDriver, abc.ABC):
    """
    Executor that supports deferred (batched) command execution.

    Commands marked as deferrable can be collected and executed later
    as a batch, which is more efficient for some backends (e.g., bootc
    image mode where commands are collected into a Containerfile).

    This extends ExecutionDriver with defer() and flush() methods for
    batch execution support.
    """

    @abc.abstractmethod
    def defer(
        self,
        command: Union[Command, ShellScript],
        *,
        cwd: Optional[Path] = None,
        env: Optional[Environment] = None,
        sourced_files: Optional[list[Path]] = None,
    ) -> None:
        """
        Defer a command for later batch execution.

        The command will not run immediately but will be collected
        and executed when flush() is called.

        :param command: the command or shell script to defer.
        :param cwd: working directory for the command.
        :param env: environment variables for the command.
        :param sourced_files: files to source before running the command.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def flush(self) -> None:
        """
        Execute all deferred commands as a batch.

        The specific semantics depend on the implementation. For example,
        BootcContainerfileExecutor will build a container image from
        collected Containerfile directives and reboot into the new image.
        """
        raise NotImplementedError

    @property
    @abc.abstractmethod
    def has_pending_commands(self) -> bool:
        """
        Check if there are deferred commands waiting to be flushed.

        :returns: True if there are pending commands.
        """
        raise NotImplementedError

    def on_step_complete(self, step: 'tmt.steps.Step') -> None:
        """
        Called when a step completes execution on this guest.

        Flushes collected commands if there are any pending.

        :param step: the step that has completed.
        """
        import tmt.steps

        if self.has_pending_commands:
            self.info("Flushing collected commands")
            self.flush()
        else:
            self.debug("No deferred commands to flush.")
