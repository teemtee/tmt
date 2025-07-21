from typing import Optional

import tmt
import tmt.log
import tmt.steps
import tmt.steps.cleanup
import tmt.utils
from tmt.container import container, field
from tmt.steps.provision import Guest


@container
class CleanupInternalData(tmt.steps.cleanup.CleanupStepData):
    guest: bool = field(
        default=True,
        option=('--guest/--no-guest'),
        is_flag=True,
        help="Whether guests should be stopped and removed during the cleanup.",
    )


@tmt.steps.provides_method('tmt')
class CleanupInternal(tmt.steps.cleanup.CleanupPlugin[CleanupInternalData]):
    """
    Clean up guests, prune the workdir

    TODO The internal cleanup plugin...
    """

    _data_class = CleanupInternalData
    data: CleanupInternalData

    def go(
        self,
        *,
        guest: 'Guest',
        environment: Optional[tmt.utils.Environment] = None,
        logger: tmt.log.Logger,
    ) -> tmt.steps.PluginOutcome:
        """
        Stop and remove guest
        """

        outcome = super().go(guest=guest, environment=environment, logger=logger)

        # Nothing to do in dry mode
        if self.is_dry_run:
            return outcome

        # Fetch the latest logs
        if guest.is_ready:
            logger.debug(f"Fetch logs from guest '{guest.name}'.")
            guest.fetch_logs(logger=self._logger)

        # Stop the guest and remove it
        if self.data.guest:
            logger.debug(f"Stop and remove guest '{guest.name}'.")
            guest.stop()
            guest.remove()

        # Keep guest if requested by the user
        else:
            logger.verbose(f"Keeping guest '{guest.name}' running as requested.")

        return outcome
