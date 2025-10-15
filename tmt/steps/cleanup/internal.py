from typing import Optional

import tmt
import tmt.log
import tmt.steps
import tmt.steps.cleanup
import tmt.utils
from tmt.container import container
from tmt.options import Path
from tmt.steps.prepare.artifact.providers import Repository
from tmt.steps.prepare.artifact.providers.repository import RepositoryFileProvider
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

        logger.info(f'I AM ZEREF {guest} {logger}')
        url = 'https://download.docker.com/linux/centos/docker-ce.repo'
        # repo = Repository(url=url, filename='config.repo')
        # repo.install(guest=guest, logger=logger)
        # p = repo.rpms
        # logger.info("", f"{len(p)}")
        dp = Path()
        rp = RepositoryFileProvider(raw_provider_id=url, logger=logger)
        rp.fetch_contents(guest=guest, download_path=dp)
        logger.info('BLAKZEREF ', rp.id)
        logger.info('BLAKZEREF ', rp.repo_filename)
        logger.info('BLAKZEREF ', rp._parsed_url)
        p1 = 0 
        for i in rp.artifacts[:6]:
            p1 = p1 + 1 
            if p1 == 6:
                break
            logger.info('WHITE_ZEREF ', str(i))

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
