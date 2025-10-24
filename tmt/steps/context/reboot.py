import functools
import json
import os
from contextlib import suppress
from typing import TYPE_CHECKING, Optional

import tmt.log
import tmt.steps.provision
import tmt.steps.scripts
import tmt.utils
from tmt.container import container
from tmt.steps.provision import Guest
from tmt.utils import Environment, EnvVarValue, Path, ShellScript
from tmt.utils.wait import Deadline, Waiting

if TYPE_CHECKING:
    from tmt.steps.context.restart import RestartContext


@container
class RebootContext:
    """
    Tracks information about guest reboots.
    """

    #: A label describing the owner of this context, for the logging
    #: purposes.
    owner_label: str

    #: A guest to reboot when requested.
    guest: Guest

    #: Path in which the reboot request file should be stored.
    path: Path

    #: Used for logging.
    logger: tmt.log.Logger

    #: Number of times the guest has been rebooted.
    reboot_counter: int = 0

    @functools.cached_property
    def request_path(self) -> Path:
        """
        A path to the reboot request file.
        """

        return self.path / tmt.steps.scripts.TMT_REBOOT_SCRIPT.created_file

    @property
    def soft_requested(self) -> bool:
        """
        If set, a soft reboot was requested.
        """

        return self.request_path.exists()

    #: If set, an asynchronous observer requested a hard reboot.
    hard_requested: bool = False

    @property
    def requested(self) -> bool:
        """
        Whether a guest reboot has been requested
        """

        return self.soft_requested or self.hard_requested

    @property
    def environment(self) -> Environment:
        environment = Environment()

        # Set all supported reboot variables
        for reboot_variable in tmt.steps.scripts.TMT_REBOOT_SCRIPT.related_variables:
            environment[reboot_variable] = EnvVarValue(str(self.reboot_counter))

        environment["TMT_REBOOT_REQUEST"] = EnvVarValue(
            self.path / tmt.steps.scripts.TMT_REBOOT_SCRIPT.created_file
        )

        return environment

    def handle_reboot(self, restart: Optional['RestartContext'] = None) -> bool:
        """
        Reboot the guest if requested.

        Orchestrate the reboot if it was requested. Increment
        corresponding counters.

        :param restart: if set, it's a tracker of restart whose accounting
            should be updated as well.
        :return: ``True`` when the reboot has taken place, ``False``
            otherwise.
        """

        if not self.requested:
            return False

        self.reboot_counter += 1

        if restart:
            restart.restart_counter += 1

        if restart:
            self.logger.debug(
                f"{'Hard' if self.hard_requested else 'Soft'} reboot during {self.owner_label}"
                f" with reboot count {self.reboot_counter}"
                f" and test restart count {restart.restart_counter}."
            )

        else:
            self.logger.debug(
                f"{'Hard' if self.hard_requested else 'Soft'} reboot during {self.owner_label}"
                f" with reboot count {self.reboot_counter}."
            )

        rebooted = False

        if self.hard_requested:
            rebooted = self.guest.reboot(hard=True)

        elif self.soft_requested:
            # Extract custom hints from the file, and reset it.
            reboot_data = json.loads(self.request_path.read_text())

            reboot_command: Optional[ShellScript] = None

            if reboot_data.get('command'):
                with suppress(TypeError):
                    reboot_command = ShellScript(reboot_data.get('command'))

            if reboot_data.get('timeout'):
                deadline = Deadline.from_seconds(int(reboot_data.get('timeout')))

            else:
                deadline = Deadline.from_seconds(tmt.steps.provision.REBOOT_TIMEOUT)

            waiting = Waiting(deadline=deadline)

            os.remove(self.request_path)
            self.guest.execute(ShellScript(f'rm -f {self.request_path}'))

            try:
                rebooted = self.guest.reboot(hard=False, command=reboot_command, waiting=waiting)

            except tmt.utils.RunError:
                if reboot_command is not None:
                    self.logger.fail(
                        f"Failed to reboot guest using the custom command '{reboot_command}'."
                    )

                raise

            except tmt.steps.provision.RebootModeNotSupportedError:
                self.logger.warning("Guest does not support soft reboot, trying hard reboot.")

                rebooted = self.guest.reboot(hard=True, waiting=waiting)

        if not rebooted:
            raise tmt.utils.RebootTimeoutError("Reboot timed out.")

        self.hard_requested = False

        return True
