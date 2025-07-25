from typing import Optional

import tmt
import tmt.log
import tmt.steps
import tmt.steps.cleanup
import tmt.utils
from tmt.container import container
from tmt.steps.provision import Guest


@container
class CleanupInternalData(tmt.steps.cleanup.CleanupStepData):
    pass


@tmt.steps.provides_method('tmt')
class CleanupInternal(tmt.steps.cleanup.CleanupPlugin[CleanupInternalData]):
    """
    Stop and remove all provisioned guests
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
        logger.debug(f"Stop and remove guest '{guest.name}'.")
        guest.stop()
        guest.remove()

        return outcome
