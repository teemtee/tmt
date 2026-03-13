"""
Copr Repository Artifact Provider
"""

import re
from collections.abc import Sequence
from functools import cached_property
from re import Pattern
from typing import Optional

import tmt.log
from tmt.guest import Guest
from tmt.package_managers.dnf import build_copr_repo_url, parse_copr_repo
from tmt.steps.prepare.artifact.providers import (
    ArtifactInfo,
    ArtifactProviderId,
    Repository,
    UnsupportedOperationError,
    provides_artifact_provider,
)
from tmt.steps.prepare.artifact.providers._copr import CoprArtifactProvider
from tmt.utils import GeneralError, Path

COPR_REPOSITORY_PATTERN = re.compile(r'^(?:@[^/]+/[^/]+|[^@/]+/[^/]+)$')


@provides_artifact_provider('copr.repository')
class CoprRepositoryProvider(CoprArtifactProvider):
    """
    Provider for enabling Copr repositories and making their packages available.

    Identifier format: @group/project or user/project

    Example usage:

    .. code-block:: yaml

        prepare:
          - summary: enable copr repository
            how: artifact
            provide:
              - copr.repository:@teemtee/stable
    """

    copr_repo: str  # Parsed Copr repository name (e.g. 'packit/packit-dev')
    repository: Repository

    def __init__(self, raw_id: str, repository_priority: int, logger: tmt.log.Logger):
        super().__init__(raw_id, repository_priority, logger)
        self.copr_repo = self.id
        self._is_group, self._name, self._project = parse_copr_repo(self.copr_repo)

    @property
    def _copr_owner(self) -> str:
        return f'@{self._name}' if self._is_group else self._name

    @property
    def _copr_project(self) -> str:
        return self._project

    @classmethod
    def _extract_provider_id(cls, raw_id: str) -> ArtifactProviderId:
        prefix = 'copr.repository:'
        if not raw_id.startswith(prefix):
            raise ValueError(f"Invalid Copr repository provider format: '{raw_id}'.")

        value = raw_id[len(prefix) :]
        if not value:
            raise ValueError("Missing Copr repository name.")

        if not COPR_REPOSITORY_PATTERN.match(value):
            raise ValueError(
                f"Invalid Copr repository format: '{value}'. "
                "Expected format: '@group/project' or 'user/project'."
            )

        return value

    @cached_property
    def artifacts(self) -> Sequence[ArtifactInfo]:
        # Copr repository provider does not enumerate individual artifacts.
        # The repository is enabled and packages are available through the package manager.
        return []

    def _download_artifact(self, artifact: ArtifactInfo, guest: Guest, destination: Path) -> None:
        """This provider only enables repositories; it does not download individual RPMs."""
        raise UnsupportedOperationError(
            "CoprRepositoryProvider does not support downloading individual RPMs."
        )

    def get_repositories(self) -> list[Repository]:
        self.logger.info(f"Providing repository '{self.repository.name}' for installation")
        return [self.repository]

    def fetch_contents(
        self,
        guest: Guest,
        download_path: Path,
        exclude_patterns: Optional[list[Pattern[str]]] = None,
    ) -> list[Path]:
        """
        Resolve the Copr repository ``.repo`` file for this guest.
        """
        chroot_repos = self.project_info.chroot_repos
        os_release = guest.facts.os_release_content
        chroot = (
            f"{os_release.get('ID', '')}-{os_release.get('VERSION_ID', '')}"
            f"-{guest.facts.arch or ''}"
        )

        if chroot not in chroot_repos:
            raise GeneralError(
                f"COPR repository '{self.copr_repo}' has no chroot '{chroot}'. "
                f"Available chroots: {', '.join(sorted(chroot_repos))}"
            )

        url = build_copr_repo_url(self.copr_repo, chroot)
        self.logger.debug(f"Fetching COPR repository '{self.copr_repo}' from '{url}'.")
        self.repository = Repository.from_url(url, self.logger)

        return []
