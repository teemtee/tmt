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
from tmt.steps.prepare.artifact.providers import (
    ArtifactInfo,
    ArtifactProvider,
    ArtifactProviderId,
    UnsupportedOperationError,
    provides_artifact_provider,
)
from tmt.utils import Path

COPR_REPOSITORY_PATTERN = re.compile(r'^(?:@[^/]+/[^/]+|[^@/]+/[^/]+)$')


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

    def __init__(self, raw_id: str, repository_priority: int, logger: tmt.log.Logger):
        super().__init__(raw_id, repository_priority, logger)
        self.copr_repo = self.id

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
        Enable the Copr repository on the guest.

        :return: Empty list as no files are downloaded.
        :raises tmt.utils.PrepareError: If the package manager does not support
            enabling Copr repositories.
        """
        guest.package_manager.enable_copr(self.copr_repo)
        return []
