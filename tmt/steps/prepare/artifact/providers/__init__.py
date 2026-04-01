"""
Abstract base class for artifact providers.
"""

import re
from abc import ABC, abstractmethod
from collections.abc import Iterator, Sequence
from functools import cached_property
from re import Pattern
from shlex import quote
from typing import Any, Optional

import tmt.log
import tmt.utils
from tmt._compat.typing import TypeAlias
from tmt.container import container, simple_field
from tmt.guest import Guest
from tmt.package_managers import Repository, Version
from tmt.plugins import PluginRegistry
from tmt.utils import Path, ShellScript

NEVRA_PATTERN = re.compile(
    r'^(?P<name>.+)-(?:(?P<epoch>\d+):)?(?P<version>.+)-(?P<release>.+)\.(?P<arch>.+)$'
)


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


@container
class ArtifactProvider(ABC):
    """
    Base class for artifact providers.

    Two provider patterns exist:

    * **Download providers** (e.g. ``koji.build``): override :py:attr:`artifacts`
      as a ``@cached_property``, implement :py:meth:`_download_artifact` and
      :py:meth:`contribute_to_shared_repo`. Do not use :py:attr:`_artifacts`.

    * **Repository providers** (e.g. ``copr.repository``): implement
      :py:meth:`get_repositories`. After installation, :py:meth:`enumerate_artifacts`
      queries the package manager and populates :py:attr:`_artifacts`.
    """

    #: Original full provider id given
    raw_id: str

    #: Repository priority for providers that create repositories.
    #: Lower values have higher priority in package managers.
    repository_priority: int

    logger: tmt.log.Logger

    #: Identifier of this artifact provider. It is valid and unique
    #: in the domain of this provider. ``koji.build:12345``. URL for a
    #: repository, and so on.
    id: ArtifactProviderId = simple_field(init=False)

    #: All artifacts known to this provider. Populated by
    #: :py:meth:`_download_artifact` and/or :py:meth:`enumerate_artifacts`.
    _artifacts: list[ArtifactInfo] = simple_field(init=False, default_factory=list)

    def __post_init__(self) -> None:
        self.id = self._extract_provider_id(self.raw_id)

    @cached_property
    def sanitized_id(self) -> str:
        """
        Sanitized provider ID to use as a directory name
        """
        return tmt.utils.sanitize_name(self.raw_id, allow_slash=False)

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

    @property
    def artifacts(self) -> Sequence[ArtifactInfo]:
        """
        Collect all artifacts available from this provider.

        :returns: a list of provided artifacts.
        """

        return self._artifacts

    def _download_artifact(
        self, artifact: ArtifactInfo, guest: Guest, destination: tmt.utils.Path
    ) -> None:
        """
        Download a single artifact to the specified destination on a given guest.

        :param artifact: the artifact to download.
        :param guest: the guest on which the artifact should be downloaded.
        :param destination: path into which the artifact should be downloaded.
        :raises DownloadError: if the download fails.
        """

        try:
            guest.download(artifact.location, destination)
        except tmt.utils.GeneralError as error:
            raise DownloadError(f"Failed to download '{artifact}'.") from error

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

    def enumerate_artifacts(self, guest: Guest) -> None:
        """
        Enumerate artifacts from repositories returned by :py:meth:`get_repositories`
        and populate :py:attr:`_artifacts`. Call this after repositories are installed.

        For repository providers only. Does not include artifacts contributed to
        the shared repository — those are handled by :py:meth:`contribute_to_shared_repo`.
        """
        for repository in self.get_repositories():
            try:
                packages = guest.package_manager.list_packages(repository)
            except tmt.utils.RunError as error:
                tmt.utils.show_exception_as_warning(
                    exception=error,
                    message=f"Failed to enumerate packages from repository '{repository.name}'.",
                    logger=self.logger,
                )
                continue
            for rpm_version in packages:
                self._artifacts.append(
                    ArtifactInfo(
                        version=rpm_version,
                        provider=self,
                        location=repository.name,
                    )
                )
            self.logger.debug(
                f"Enumerated {len(packages)} packages from repository '{repository.name}'."
            )

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
