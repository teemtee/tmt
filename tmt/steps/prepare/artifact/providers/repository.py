"""
Repository Artifact Provider
"""

from collections.abc import Sequence
from functools import cached_property
from typing import Optional
from urllib.parse import urlparse

import tmt.log
import tmt.utils
from tmt.steps.prepare.artifact.providers import (
    ArtifactProvider,
    ArtifactProviderId,
    DownloadError,
    Repository,
    provides_artifact_provider,
)
from tmt.steps.prepare.artifact.providers.koji import RpmArtifactInfo
from tmt.steps.provision import Guest
from tmt.utils import Path


# ignore[type-arg]: TypeVar in provider registry annotations is
# puzzling for type checkers. And not a good idea in general, probably.
@provides_artifact_provider('repository-url')  # type: ignore[arg-type]
class RepositoryArtifactProvider(ArtifactProvider[RpmArtifactInfo]):
    """
    Provider for making RPM artifacts from a repository discoverable without downloading them.

    The provider identifier should start with 'repository-url:' followed by a URL to a .repo file,
    e.g., "repository-url:https://download.docker.com/linux/centos/docker-ce.repo".

    Artifacts are all available RPM packages listed in the repository
    """

    repo: Repository
    _artifact_list: Sequence[RpmArtifactInfo]

    @classmethod
    def _extract_provider_id(cls, raw_provider_id: str) -> ArtifactProviderId:
        prefix = 'repository-url:'
        if not raw_provider_id.startswith(prefix):
            raise ValueError(f"Invalid repository provider format: '{raw_provider_id}'.")
        value = raw_provider_id[len(prefix) :]
        if not value:
            raise ValueError("Missing repository URL.")
        return value

    def __init__(self, raw_provider_id: str, logger: tmt.log.Logger):
        super().__init__(raw_provider_id, logger)
        self._artifact_list = []

    @cached_property
    def artifacts(self) -> Sequence[RpmArtifactInfo]:
        if not self._artifact_list:
            raise tmt.utils.GeneralError("Call fetch_contents first to discover artifacts.")
        return self._artifact_list

    def _create_repository(self) -> Repository:
        return Repository.from_url(url=self.id)

    def _download_artifact(
        self, artifact: RpmArtifactInfo, guest: Guest, destination: tmt.utils.Path
    ) -> None:
        """
        This provider does not support downloading individual artifacts.
        """
        raise DownloadError(
            "Repository provider does not support downloading individual artifacts."
        )

    def fetch_contents(
        self,
        guest: Guest,
        download_path: tmt.utils.Path,
        exclude_patterns: Optional[list[tmt.utils.Pattern[str]]] = None,
    ) -> list[tmt.utils.Path]:
        """
        Override to install the repository on the guest instead of downloading artifacts.

        :param guest: the guest on which the repository should be installed.
        :param download_path: not used in this provider.
        :param exclude_patterns: not used in this provider.
        :returns: an empty list, as no files are downloaded.
        """
        self.repo = self._create_repository()

        self.logger.info(f"Installing repository '{self.id}' on the guest.")

        # Install the repository using the guest's package manager
        guest.package_manager.install_repository(self.repo)

        # Load the artifacts using list_packages
        package_list = guest.package_manager.list_packages(self.repo)

        artifacts_list: list[RpmArtifactInfo] = []

        for pkg in package_list:
            try:
                # Split into NEVR and arch
                nevr, arch = pkg.rsplit('.', 1)

                # Split NEVR into name, version, release
                parts = nevr.rsplit('-', 2)
                if len(parts) != 3:
                    raise ValueError("Invalid parts")

                name = parts[0]
                ver = parts[1]
                release = parts[2]

                epoch = '0'
                version = ver
                if ':' in ver:
                    epoch, version = ver.split(':', 1)

                nvr = f"{name}-{version}-{release}"

                raw_artifact = {
                    'name': name,
                    'epoch': epoch,
                    'version': version,
                    'release': release,
                    'arch': arch,
                    'nvr': nvr,
                    'url': self.id,
                }
                artifacts_list.append(RpmArtifactInfo(_raw_artifact=raw_artifact))

            except Exception as error:
                self.logger.warning(f"Failed to parse package '{pkg}': {error}")
                continue

        self._artifact_list = artifacts_list

        self.logger.info(f"Successfully discovered '{len(artifacts_list)}' artifacts.")

        return []
