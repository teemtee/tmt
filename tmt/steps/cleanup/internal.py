from typing import Optional

import tmt
import tmt.log
import tmt.steps
import tmt.steps.cleanup
import tmt.utils
from tmt._compat.pathlib import Path
from tmt.container import container
from tmt.steps.prepare.artifact.providers.repository import create_repository
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

        # POC: Test repository creation and package listing
        logger.info("=== Starting Repository Creation POC ===")

        # Step 1: Create artifact directory
        logger.info("Step 1: Creating artifact directory /tmp/vaibhav/")
        guest.execute(tmt.utils.Command("mkdir", "-p", "/tmp/vaibhav/"))  # noqa: S108

        # Step 2: Download RPMs into the directory
        logger.info("Step 2: Downloading nginx and dependencies")
        guest.execute(tmt.utils.ShellScript('cd /tmp/vaibhav/ && dnf download --resolve nginx'))

        # Step 3: Create repository from the directory
        logger.info("Step 3: Creating repository from artifacts")
        repo = create_repository(Path('/tmp/vaibhav/'), guest, logger, "vaibhavs-repo")  # noqa: S108
        logger.info(
            f"Repository '{repo.name}' created successfully with {len(repo.repo_ids)} repo ID(s)"
        )

        # Step 4: List packages available in the repository
        logger.info("Step 4: Listing packages in repository")
        packages = guest.package_manager.list_packages(repo)
        logger.info(f"Found {len(packages)} packages in repository:")
        for pkg in packages:
            logger.info(f"  - {pkg}")

        logger.info("=== Repository Creation POC Completed Successfully ===")

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
