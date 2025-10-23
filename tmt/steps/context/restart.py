from typing import TYPE_CHECKING, Callable, Optional

import tmt.log
import tmt.utils
from tmt.container import container
from tmt.steps.provision import Guest
from tmt.utils import Environment, EnvVarValue

if TYPE_CHECKING:
    from tmt.steps.context.reboot import RebootContext


@container
class RestartContext:
    """
    Tracks information about restarts of an action, e.g. a test script.
    """

    #: A label describing the owner of this context, for the logging
    #: purposes.
    owner_label: str

    #: Guest on which the restartable action runs.
    guest: Guest

    #: A callback indicating whether a restart has been requested. It is
    #: called by :py:attr:`requested` property. Accepts no arguments,
    #: and returns a single boolean.
    is_requested_test: Callable[[], bool]

    #: A maximum number of restarts allowed. Once reached, an attempt to
    #: restart once again will raise :py:class:`RestartMaxAttemptsError`.
    restart_limit: int

    #: If set, a hard reboot will be invoked before the restart.
    restart_with_reboot: bool

    #: Used for logging.
    logger: tmt.log.Logger

    #: Number of times the action has been restarted.
    restart_counter: int = 0

    @property
    def requested(self) -> bool:
        """
        Whether a restart has been requested.
        """

        return self.is_requested_test()

    @property
    def environment(self) -> Environment:
        return Environment({'TMT_TEST_RESTART_COUNT': EnvVarValue(str(self.restart_counter))})

    def handle_restart(self, reboot: Optional['RebootContext'] = None) -> bool:
        """
        "Restart" the action when requested.

        .. note::

            The action is not actually restarted, because running the
            action is managed by the owner of this context. Instead, the
            method performs all necessary steps before letting plugin
            know it should run the action once again.

        Check whether an action restart was needed and allowed, and
        update the accounting info before letting the caller know it's
        time to run the action once again.

        If requested, the guest might be rebooted as well.

        :param reboot: if set, it's a tracker of guest reboots to be
            used when :py:attr:`restart_with_reboot` is set. Setting
            the flag without providing the reboot context will raise
            an exception.
        :return: ``True`` when the restart is to take place, ``False``
            otherwise.
        """

        if not self.requested:
            return False

        if self.restart_counter >= self.restart_limit:
            if reboot:
                self.logger.debug(
                    f"Restart denied during {self.owner_label}"
                    f" with reboot count {reboot.reboot_counter}"
                    f" and restart count {self.restart_counter}."
                )

            else:
                self.logger.debug(
                    f"Restart denied during {self.owner_label}"
                    f" with restart count {self.restart_counter}."
                )

            raise tmt.utils.RestartMaxAttemptsError("Maximum restart attempts exceeded.")

        if self.restart_with_reboot:
            if not reboot:
                raise tmt.utils.GeneralError(
                    'A guest reboot before restart is not possible without a reboot context.'
                )

            reboot.hard_requested = True

            if not reboot.handle_reboot(restart=self):
                return False

        else:
            self.restart_counter += 1

            # Even though the reboot was not requested, it might have
            # still happened! Imagine a test configuring autoreboot on
            # kernel panic plus a test restart. The reboot would happen
            # beyond tmt's control, and tmt would try to restart the
            # test, but the guest may be still booting. Make sure it's
            # alive.
            if not self.guest.reconnect():
                raise tmt.utils.ReconnectTimeoutError("Reconnect timed out.")

        if reboot:
            self.logger.debug(
                f"Test restart during {self.owner_label}"
                f" with reboot count {reboot.reboot_counter}"
                f" and restart count {self.restart_counter}."
            )

        else:
            self.logger.debug(
                f"Test restart during {self.owner_label}"
                f" with restart count {self.restart_counter}."
            )

        self.guest.push()

        return True
