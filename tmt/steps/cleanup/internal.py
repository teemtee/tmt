from typing import Optional

import tmt
import tmt.log
import tmt.steps
import tmt.steps.cleanup
import tmt.utils
from tmt._compat.pathlib import Path
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
        from tmt.steps.prepare.artifact.providers import Repository
        from tmt.steps.prepare.artifact.providers.repository import RepositoryFileProvider
        logger.info(f'I AM ZEREF {guest} {logger}')
        url = 'https://download.docker.com/linux/centos/docker-ce.repo'
        # repo = Repository.from_url(url=url)
        # logger.info("repo_ids", f"{repo.repo_ids}", "blue")
        # logger.info("repo_ids", f"{repo.filename}", "blue")
        # guest.package_manager.install_repository(repo)
        # v = guest.execute(tmt.utils.ShellScript(f'cat /etc/yum.repos.d/{repo.filename}'))
        # logger.info('check installed repo', f"{v.stdout}",'blue' )
        # package_list = guest.package_manager.list_packages(repo)
        # logger.info('check available packeages', f"{package_list}",'blue' )

        # for i in package_list:
        #     logger.info('ipackage', f"{i}",'blue' )
        rp = RepositoryFileProvider(logger=logger, raw_provider_id=f'repository-url:{url}')
        dp = Path()
        rp.fetch_contents(guest=guest, download_path=dp)
        afs = rp.artifacts
        for i in afs:
            logger.info('rpmi', i._raw_artifact)

        # rp.artifacts
        outcome = super().go(guest=guest, environment=environment, logger=logger)

        # # repo.install(guest=guest, logger=logger)
        # # p = repo.rpms
        # logger.info("", f"{len(p)}")
        # #
        # # rp = RepositoryFileProvider(raw_provider_id=url, logger=logger)
        # rp.fetch_contents(guest=guest, download_path=dp)
        # logger.info('BLAKZEREF ', rp.id)
        # logger.info('BLAKZEREF ', rp.repo_filename)
        # logger.info('BLAKZEREF ', rp._parsed_url)
        # p1 = 0
        # for i in rp.artifacts[:6]:
        #     p1 = p1 + 1
        #     if p1 == 6:
        #         break
        #     logger.info('WHITE_ZEREF ', str(i))
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
