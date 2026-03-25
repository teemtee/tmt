"""
Abstract base class for artifact providers.
"""

from abc import ABC, abstractmethod
from collections.abc import Iterator, Sequence
from functools import cached_property
from re import Pattern
from shlex import quote
from typing import Any, Optional

import tmt.log
import tmt.utils
from tmt._compat.typing import TypeAlias
from tmt.container import container
from tmt.guest import Guest
from tmt.package_managers import Repository, Version
from tmt.plugins import PluginRegistry
from tmt.utils import GeneralError as GeneralError
from tmt.utils import Path, ShellScript


class DownloadError(tmt.utils.GeneralError):
    """
    Raised when download fails.
    """


class UnsupportedOperationError(RuntimeError):
    """
    Raised when an operation is intentionally unsupported by a provider.
    """


@container
class ArtifactInfo:
    """
    Information about a single artifact, e.g. a package.
    """

    version: Version
    location: str
    provider: "ArtifactProvider"

    @property
    def id(self) -> str:
        """
        A unique identifier of the artifact.

        TODO: Transient for now, modify based on the decision made here: https://github.com/teemtee/tmt/issues/4546
        """
        return self.version.nvra

    @property
    def name(self) -> str:
        return self.version.name

    @property
    def filename(self) -> str:
        """
        This is the filename of the artifact.
        """
        return f"{self.id}.rpm"

    def __str__(self) -> str:
        return f"{self.version} ({self.provider.id})"


#: A type of an artifact provider identifier.
ArtifactProviderId: TypeAlias = str


class ArtifactProvider(ABC):
    """
    Base class for artifact providers.

    Each provider must implement:

    * parsing and validating the artifact ID,
    * listing available artifacts,
    * downloading a single given artifact.
    """

    #: Identifier of this artifact provider. It is valid and unique
    #: in the domain of this provider. ``koji.build:12345``. URL for a
    #: repository, and so on.
    id: ArtifactProviderId

    #: Repository priority for providers that create repositories.
    #: Lower values have higher priority in package managers.
    repository_priority: int

    def __init__(self, raw_id: str, repository_priority: int, logger: tmt.log.Logger):
        self.repository_priority = repository_priority
        self.logger = logger
        self.raw_id = raw_id
        # Sanitize the provider ID to use as a directory name
        self.sanitized_id = tmt.utils.sanitize_name(raw_id, allow_slash=False)

        self.id = self._extract_provider_id(raw_id)

    @classmethod
    @abstractmethod
    def _extract_provider_id(cls, raw_id: str) -> ArtifactProviderId:
        """
        Parse and validate the artifact provider identifier.

        :param raw_id: artifact provider identifier to parse and validate.
        :returns: parsed identifier specific to this provider class.
        :raises ValueError: when the artifact provider identifier is invalid.
        """

        raise NotImplementedError

    @cached_property
    @abstractmethod
    def artifacts(self) -> Sequence[ArtifactInfo]:
        """
        Collect all artifacts available from this provider.

        The method is left for derived classes to implement with respect
        to the actual artifact provider they implement. The list of
        artifacts will be cached, and is treated as read-only.

        :returns: a list of provided artifacts.
        """

        raise NotImplementedError

    @abstractmethod
    def _download_artifact(
        self, artifact: ArtifactInfo, guest: Guest, destination: tmt.utils.Path
    ) -> None:
        """
        Download a single artifact to the specified destination on a given guest.

        :param guest: the guest on which the artifact should be downloaded.
        :param destination: path into which the artifact should be downloaded.
        """

        raise NotImplementedError

    def fetch_contents(
        self,
        guest: Guest,
        download_path: tmt.utils.Path,
        exclude_patterns: Optional[list[Pattern[str]]] = None,
    ) -> list[tmt.utils.Path]:
        """
        Fetch all artifacts to the specified destination.

        :param guest: the guest on which the artifact should be
            downloaded.
        :param download_path: path into which the artifact should be
            downloaded.
        :param exclude_patterns: if set, artifacts whose names match any
            of the given regular expressions would not be downloaded.
        :returns: a list of paths to the downloaded artifacts.
        :raises GeneralError: Unexpected errors outside the download process.
        :note: Errors during individual artifact downloads are
            caught, logged as warnings, and ignored.
        """

        self.logger.info(f"Downloading artifacts to '{download_path!s}'.")

        exclude_patterns = exclude_patterns or []

        # Ensure download directory exists on guest (create only if missing)
        guest.execute(
            ShellScript(
                f"[ -d {quote(str(download_path))} ] || "
                f"{guest.facts.sudo_prefix} mkdir -p {quote(str(download_path))}"
            ),
            silent=True,
        )

        downloaded_paths: list[tmt.utils.Path] = []

        for artifact in self._filter_artifacts(exclude_patterns):
            local_path = download_path / artifact.filename
            self.logger.debug(f"Downloading '{artifact}' to '{local_path}'.")

            try:
                self._download_artifact(artifact, guest, local_path)
                downloaded_paths.append(local_path)
                self.logger.info(f"Downloaded '{artifact}' to '{local_path}'.")

            except DownloadError as error:
                # Warn about the failed download and move on
                tmt.utils.show_exception_as_warning(
                    exception=error,
                    message=f"Failed to download '{artifact}'.",
                    include_logfiles=True,
                    logger=self.logger,
                )

            except Exception as error:
                raise tmt.utils.GeneralError(
                    f"Unexpected error downloading '{artifact}'."
                ) from error

        self.logger.info(f"Successfully downloaded '{len(downloaded_paths)}' artifacts.")
        return downloaded_paths

    def _filter_artifacts(self, exclude_patterns: list[Pattern[str]]) -> Iterator[ArtifactInfo]:
        """
        Filter artifacts based on exclude patterns.

        :param exclude_patterns: artifact whose name matches any of
            these patterns would be skipped.
        :yields: artifacts that satisfy the filtering.
        """

        for artifact in self.artifacts:
            if not any(pattern.search(artifact.id) for pattern in exclude_patterns):
                yield artifact

    def get_repositories(self) -> list['Repository']:
        """
        Return a list of :py:class:`Repository` that this provider manages.
        """
        return []

    # B027: "... is an empty method in an abstract base class, but has
    # no abstract decorator" - expected, it's a default implementation
    # provided for subclasses. It is acceptable to do nothing.
    def contribute_to_shared_repo(  # noqa: B027
        self,
        guest: Guest,
        source_path: Path,
        shared_repo_dir: Path,
        exclude_patterns: Optional[list[Pattern[str]]] = None,
    ) -> None:
        """
        Contribute artifacts to the shared repository.

        This is the main interface for providers to contribute their artifacts
        to the shared repository. Providers should override this method to
        implement their specific contribution logic.

        :param guest: the guest to run the commands on.
        :param source_path: path where the artifacts are located (source for contribution).
        :param shared_repo_dir: path to the shared repository directory where
            artifacts should be contributed.
        :param exclude_patterns: if set, artifacts whose names match any
            of the given regular expressions would not be contributed.
        """
        pass

    @property
    def artifact_metadata(self) -> list[dict[str, Any]]:
        """
        Get metadata for the artifacts provided by this provider.

        :returns: List of artifact metadata dictionaries.
        """
        return [
            {
                'version': vars(artifact.version),
                'nvra': artifact.version.nvra,
                'location': artifact.location,
            }
            for artifact in self.artifacts
        ]


_PROVIDER_REGISTRY: PluginRegistry[type[ArtifactProvider]] = PluginRegistry(
    'prepare.artifact.providers'
)


def _register_hints(
    plugin_id: str,
    plugin_class: type[ArtifactProvider],
    hints: Optional[dict[str, str]] = None,
) -> None:
    for hint_id, hint in (hints or {}).items():
        tmt.utils.hints.register_hint(f'artifact-provider/{plugin_id}/{hint_id}', hint)


provides_artifact_provider = _PROVIDER_REGISTRY.create_decorator(on_register=_register_hints)
