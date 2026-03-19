"""
Copr Repository Artifact Provider
"""

import re
from collections.abc import Sequence
from functools import cached_property
from re import Pattern
from typing import Optional

import tmt.log
import tmt.utils
from tmt.container import container
from tmt.guest import Guest
from tmt.steps.prepare.artifact.providers import (
    ArtifactInfo,
    ArtifactProvider,
    ArtifactProviderId,
    Repository,
    UnsupportedOperationError,
    provides_artifact_provider,
)
from tmt.utils import Path

COPR_REPO_PATTERN = re.compile(r'^(?P<group>@)?(?P<name>[^/]+)/(?P<project>[^/]+)$')
COPR_REPOSITORY_PATTERN = re.compile(r'^(?:@[^/]+/[^/]+|[^@/]+/[^/]+)$')


@container(frozen=True)
class CoprRepo:
    is_group: bool
    name: str
    project: str


def parse_copr_repo(copr_repo: str) -> CoprRepo:
    """
    Parse a COPR repository identifier into its components.
    """
    matched = COPR_REPO_PATTERN.match(copr_repo)
    if not matched:
        raise tmt.utils.PrepareError(f"Invalid copr repository '{copr_repo}'.")
    return CoprRepo(
        is_group=bool(matched.group('group')),
        name=matched.group('name'),
        project=matched.group('project'),
    )


@provides_artifact_provider('copr.repository')
class CoprRepositoryProvider(ArtifactProvider):
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
    repository: Optional[Repository]

    def __init__(self, raw_id: str, repository_priority: int, logger: tmt.log.Logger):
        super().__init__(raw_id, repository_priority, logger)
        self.copr_repo = self.id
        self.repository = None

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

    def fetch_contents(
        self,
        guest: Guest,
        download_path: Path,
        exclude_patterns: Optional[list[Pattern[str]]] = None,
    ) -> list[Path]:
        """
        Enable the Copr repository on the guest and retrieve the resulting
        ``.repo`` file content.
        """
        guest.package_manager.enable_copr(self.copr_repo)

        repo = parse_copr_repo(self.copr_repo)
        owner = f'group_{repo.name}' if repo.is_group else repo.name
        repo_filename = f"_copr:copr.fedorainfracloud.org:{owner}:{repo.project}.repo"

        # pull from guest to build Repository object with populated repo_ids
        guest.pull(
            source=Path(f"/etc/yum.repos.d/{repo_filename}"),
            destination=download_path,
        )

        self.repository = Repository.from_file_path(
            download_path / repo_filename, self.logger, name=self.copr_repo
        )
        return []
