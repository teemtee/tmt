"""
Artifact provider for discovering RPMs from repository files.
"""

from collections.abc import Sequence
from re import Pattern
from typing import Optional
from urllib.parse import unquote, urlparse

import tmt.log
from tmt.steps.prepare.artifact.providers import (
    ArtifactProvider,
    ArtifactProviderId,
    Repository,
    provides_artifact_provider,
)
from tmt.steps.prepare.artifact.providers.koji import RpmArtifactInfo
from tmt.steps.provision import Guest
from tmt.utils import GeneralError, Path


@provides_artifact_provider('repository')
class RepositoryFileProvider(ArtifactProvider[RpmArtifactInfo]):
    """
    Sets up repositories from a .repo file and discovers available RPMs.

    The provider uses a URL to a .repo file, downloads it to the guest's
    ``/etc/yum.repos.d/`` directory, and lists RPMs available in the defined
    repositories without downloading them, acting as a discovery-only provider.

    :param raw_provider_id: URL of the .repo file.
    :param logger: Logger instance for outputting messages.
    :raises GeneralError: If the .repo file URL is invalid.
    """

    def __init__(self, raw_provider_id: str, logger: tmt.log.Logger):
        super().__init__(raw_provider_id, logger)

        # Validate and parse the .repo file URL
        try:
            self._parsed_url = urlparse(self.id)
            if not self._parsed_url.scheme or not self._parsed_url.netloc:
                raise ValueError("URL must have a scheme and network location.")
        except ValueError as exc:
            raise GeneralError(f"Invalid .repo file URL: '{self.id}'.") from exc

        # Cache for RPMs discovered in the repositories
        self._rpm_list: Optional[list[RpmArtifactInfo]] = None

    @property
    def repo_filename(self) -> str:
        """
        Extract a suitable filename from the URL path.

        :returns: Unquoted filename derived from the URL's path component.
        """
        return unquote(Path(self._parsed_url.path).name)

    @classmethod
    def _extract_provider_id(cls, raw_provider_id: str) -> ArtifactProviderId:
        return raw_provider_id

    @property
    def artifacts(self) -> Sequence[RpmArtifactInfo]:
        """
        List all RPMs discovered from the repositories.

        .. note::

            The :py:meth:`fetch_contents` method must be called first to populate
            the artifact list from the guest.
        """
        if self._rpm_list is None:
            raise GeneralError(
                "RPM list not available. Call 'fetch_contents' before accessing artifacts."
            )
        return self._rpm_list

    def _download_artifact(
        self, artifact: RpmArtifactInfo, guest: Guest, destination: Path
    ) -> None:
        """This provider only discovers repos; it does not download individual RPMs."""
        raise NotImplementedError(
            "RepositoryFileProvider does not support downloading individual RPMs."
        )

    def fetch_contents(
        self,
        guest: Guest,
        download_path: Path,
        exclude_patterns: Optional[list[Pattern[str]]] = None,
    ) -> list[Path]:
        """
        Install repositories on the guest and discover available packages.

        Downloads the .repo file to the guest, installs the repositories, and queries
        them to discover available RPMs. No RPMs are downloaded.

        :param guest: Guest system to install the repositories on.
        :param download_path: Unused, as no artifacts are downloaded.
        :param exclude_patterns: Optional regex patterns to exclude specific RPMs (unused).
        :returns: Empty list, as no files are downloaded.
        """
        # Initialize and install the repository on the guest
        repository = Repository(url=self.id, filename=self.repo_filename)
        repository.install(guest=guest, logger=self.logger)

        # Cache the list of discovered RPMs
        self._rpm_list = repository.rpms

        # Return empty list as no artifacts are downloaded
        return []