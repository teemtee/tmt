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

    The artifact ID is a URL to a .repo file. This provider's main purpose
    is to download this file to '/etc/yum.repos.d/' on the guest.

    It then lists all RPMs made available by all repositories defined in
    the .repo file but does not download them, serving as a "discovery-only"
    provider.
    """

    def __init__(self, raw_provider_id: str, logger: tmt.log.Logger):
        """
        Initializes the provider and validates the .repo file URL.

        :param raw_provider_id: The URL of the .repo file.
        :param logger: The logger for outputting messages.
        :raises GeneralError: If the URL format is invalid.
        """
        super().__init__(raw_provider_id, logger)

        try:
            self._parsed_url = urlparse(self.id)
            if not self._parsed_url.scheme or not self._parsed_url.netloc:
                raise ValueError("URL must have a scheme and network location.")
        except ValueError as exc:
            raise GeneralError(f"Invalid URL format for .repo file: '{self.id}'.") from exc

        # Cache for the list of RPMs discovered in the repositories.
        # It's populated by fetch_contents().
        self._rpm_list: Optional[list[RpmArtifactInfo]] = None

    @property
    def repo_filename(self) -> str:
        """A suitable filename extracted from the URL path."""
        return unquote(Path(self._parsed_url.path).name)

    @classmethod
    def _extract_provider_id(cls, raw_provider_id: str) -> ArtifactProviderId:
        """The provider ID is the raw URL."""
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
                "RPM list not available. The 'fetch_contents' method must be "
                "called before accessing the artifacts property."
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
        Install the repositories on the guest and discover their packages.

        This method installs all repositories defined in the .repo file by
        downloading it and queries them to discover available packages.
        It does not download any RPMs itself and will return an empty list.
        """
        # 1. Create and install the repositories on the guest.
        repo = Repository(url=self.id, filename=self.repo_filename)
        repo.install(guest=guest, logger=self.logger)

        # 2. Populate the RPM list for discovery purposes by querying the repositories.
        self._rpm_list = repo.rpms

        # This provider does not download any artifacts, so return an empty list.
        return []
