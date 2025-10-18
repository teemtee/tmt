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


# ignore[type-arg]: TypeVar in provider registry annotations is
# puzzling for type checkers. And not a good idea in general, probably.
@provides_artifact_provider('repository')  # type: ignore[arg-type]
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
        :param exclude_patterns: Optional regex patterns to exclude specific RPMs.
        :returns: Empty list, as no files are downloaded.
        """
        # Initialize the repository with the URL and derived filename
        repository = Repository(url=self.id, logger=self.logger)

        # Install the repository and query available RPMs using the guest's package manager
        try:
            guest.package_manager.install_repository(repository)
            rpm_list = guest.package_manager.list_packages(repository)
        except NotImplementedError as exc:
            raise GeneralError(
                rf"Package manager '{guest.package_manager.NAME}'"
                "does not support repository queries."
            ) from exc

        # Convert package strings to RpmArtifactInfo objects
        self._rpm_list = []
        for rpm in rpm_list:
            try:
                name, epoch, version, release, arch = rpm.strip().split()
                nvr = f"{name}-{version}-{release}"
                raw_artifact = {"nvr": nvr, "arch": arch, "url": self.id, "epoch": epoch}
                self._rpm_list.append(RpmArtifactInfo(_raw_artifact=rpm))
            except ValueError:
                self.logger.warning(f"Skipping malformed RPM entry: '{rpm}'")

        # Apply exclude patterns if provided
        if exclude_patterns:
            self._rpm_list = [
                rpm
                for rpm in self._rpm_list
                if not any(pattern.search(rpm.id) for pattern in exclude_patterns)
            ]

        # Return empty list as no artifacts are downloaded
        return []
