"""
Bootc Executor for deferred command execution on image mode guests.

This module provides executors for bootc/image mode guests that support
deferred command execution by collecting commands into a Containerfile.
"""

from shlex import quote
from typing import TYPE_CHECKING, Any, Optional, Union

import tmt.log
import tmt.package_managers.bootc
import tmt.utils
from tmt.utils import Command, CommandOutput, Environment, Path, ShellScript

from . import DeferrableExecutor, ExecutionDriver, OnProcessEndCallback, OnProcessStartCallback

if TYPE_CHECKING:
    from tmt.steps.provision import GuestSsh

from .ssh import SSHExecutor


class BootcContainerfileExecutor(DeferrableExecutor):
    """
    Executor that defers commands by collecting them into a Containerfile.

    When flush() is called, it builds a new container image from the
    collected directives, switches to it via bootc, and reboots the guest.

    This is the core of bootc/image-mode support, allowing prepare/shell
    commands to be batched and applied via container image rebuild.
    """

    def __init__(
        self,
        *,
        guest: 'GuestSsh',
        logger: tmt.log.Logger,
        base_executor: ExecutionDriver,
        package_manager: 'tmt.package_managers.bootc.Bootc',
    ) -> None:
        """
        Initialize the bootc containerfile executor.

        :param guest: the SSH-capable guest this executor operates on.
        :param logger: logger to use for logging.
        :param base_executor: underlying executor for immediate commands.
        :param package_manager: bootc package manager for image operations.
        """
        super().__init__(guest=guest, logger=logger)
        self._base_executor = base_executor
        self._package_manager = package_manager
        self._ssh_guest = guest
        self._containerfile_directives: list[str] = []

    def _prepare_environment(
        self, env: Optional[Environment] = None
    ) -> Environment:
        """Prepare environment variables for the command."""
        return self._ssh_guest._prepare_environment(env)

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
        Execute command immediately using the base executor.

        For deferred execution, use defer() instead.
        """
        return self._base_executor.execute(
            command,
            cwd=cwd,
            env=env,
            friendly_command=friendly_command,
            test_session=test_session,
            tty=tty,
            silent=silent,
            log=log,
            interactive=interactive,
            on_process_start=on_process_start,
            on_process_end=on_process_end,
            sourced_files=sourced_files,
            **kwargs,
        )

    def defer(
        self,
        command: Union[Command, ShellScript],
        *,
        cwd: Optional[Path] = None,
        env: Optional[Environment] = None,
        sourced_files: Optional[list[Path]] = None,
    ) -> None:
        """
        Add command to the Containerfile for later batch execution.

        Builds a RUN directive with environment exports, working directory
        change, and the actual command.
        """
        sourced_files = sourced_files or []

        # Initialize Containerfile if needed
        if not self._containerfile_directives:
            self._containerfile_directives = self._get_base_directives()

        # Build the command script using the same approach as execute()
        # Start with environment exports
        script = ShellScript.from_scripts(
            self._prepare_environment(env).to_shell_exports()
        )

        # Add working directory change
        if cwd:
            script += ShellScript(f'cd {quote(str(cwd))}')

        # Source files
        for file in sourced_files:
            script += ShellScript(f'source {quote(str(file))}')

        # Add the actual command
        if isinstance(command, Command):
            script += command.to_script()
        else:
            script += command

        collected_command = script.to_element()

        # Add RUN directive
        self._containerfile_directives.append(f"RUN {collected_command}")
        self.debug(f"Collected command for Containerfile: {collected_command}")

    def flush(self) -> None:
        """
        Build container image from collected commands and reboot into it.

        Writes collected directives to a Containerfile, builds the image
        with podman, switches to it via bootc, and reboots the guest.
        """
        if not self._containerfile_directives:
            self.debug("No deferred commands to flush.")
            return

        # Transfer directives to the package manager's engine and build
        self._package_manager.engine.containerfile_directives = self._containerfile_directives.copy()
        self.info("building container image from collected commands")
        self._package_manager.build_container()

        # Reset for next batch
        self._containerfile_directives = []

    @property
    def has_pending_commands(self) -> bool:
        """Check if there are deferred commands waiting to be flushed."""
        return bool(self._containerfile_directives)

    @property
    def is_ready(self) -> bool:
        """Check if the base executor is ready."""
        return self._base_executor.is_ready

    def _get_base_directives(self) -> list[str]:
        """
        Get base Containerfile directives with FROM line.

        Gets the current bootc image and generates the appropriate
        FROM directive for the Containerfile.
        """
        return self._package_manager.engine._get_base_containerfile_directives()


class DeferrableSSHExecutor(DeferrableExecutor):
    """
    Composes SSH execution with deferrable behavior for bootc guests.

    This wraps an SSHExecutor and adds deferrable command collection
    via BootcContainerfileExecutor. It provides both immediate and
    deferred execution capabilities on SSH-connected bootc guests.
    """

    def __init__(
        self,
        *,
        guest: 'GuestSsh',
        logger: tmt.log.Logger,
        package_manager: 'tmt.package_managers.bootc.Bootc',
    ) -> None:
        """
        Initialize the deferrable SSH executor.

        :param guest: the SSH-capable guest this executor operates on.
        :param logger: logger to use for logging.
        :param package_manager: bootc package manager for image operations.
        """
        super().__init__(guest=guest, logger=logger)

        # Create the SSH executor for immediate execution
        self._ssh_executor = SSHExecutor(guest=guest, logger=logger)

        # Create the containerfile executor for deferred execution
        self._containerfile_executor = BootcContainerfileExecutor(
            guest=guest,
            logger=logger,
            base_executor=self._ssh_executor,
            package_manager=package_manager,
        )

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
        """Execute immediately via SSH."""
        return self._ssh_executor.execute(
            command,
            cwd=cwd,
            env=env,
            friendly_command=friendly_command,
            test_session=test_session,
            tty=tty,
            silent=silent,
            log=log,
            interactive=interactive,
            on_process_start=on_process_start,
            on_process_end=on_process_end,
            sourced_files=sourced_files,
            **kwargs,
        )

    def defer(
        self,
        command: Union[Command, ShellScript],
        *,
        cwd: Optional[Path] = None,
        env: Optional[Environment] = None,
        sourced_files: Optional[list[Path]] = None,
    ) -> None:
        """Defer command to Containerfile."""
        self._containerfile_executor.defer(
            command,
            cwd=cwd,
            env=env,
            sourced_files=sourced_files,
        )

    def flush(self) -> None:
        """Build and switch to new image."""
        self._containerfile_executor.flush()

    @property
    def has_pending_commands(self) -> bool:
        """Check if there are deferred commands."""
        return self._containerfile_executor.has_pending_commands

    @property
    def is_ready(self) -> bool:
        """Check if the SSH executor is ready."""
        return self._ssh_executor.is_ready
