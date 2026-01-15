"""
Copr Repository Artifact Provider
"""

import re
from collections.abc import Sequence
from functools import cached_property
from re import Pattern
from typing import Optional

import tmt.log
from tmt.steps.prepare import install
from tmt.steps.prepare.artifact import RpmArtifactInfo
from tmt.steps.prepare.artifact.providers import (
    ArtifactProvider,
    ArtifactProviderId,
    UnsupportedOperationError,
    provides_artifact_provider,
)
from tmt.steps.provision import Guest
from tmt.utils import Path

COPR_REPOSITORY_PATTERN = re.compile(r'^(?:@[^/]+/[^/]+|[^@/]+/[^/]+)$')


@provides_artifact_provider('copr.repository')  # type: ignore[arg-type]
class CoprRepositoryProvider(ArtifactProvider[RpmArtifactInfo]):
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

    def __init__(self, raw_provider_id: str, logger: tmt.log.Logger, priority: int):
        super().__init__(raw_provider_id, logger, priority)
        self.copr_repo = self.id

    @classmethod
    def _extract_provider_id(cls, raw_provider_id: str) -> ArtifactProviderId:
        prefix = 'copr.repository:'
        if not raw_provider_id.startswith(prefix):
            raise ValueError(f"Invalid Copr repository provider format: '{raw_provider_id}'.")

        value = raw_provider_id[len(prefix) :]
        if not value:
            raise ValueError("Missing Copr repository name.")

        if not COPR_REPOSITORY_PATTERN.match(value):
            raise ValueError(
                f"Invalid Copr repository format: '{value}'. "
                "Expected format: '@group/project' or 'user/project'."
            )

        return value

    @cached_property
    def artifacts(self) -> Sequence[RpmArtifactInfo]:
        # Copr repository provider does not enumerate individual artifacts.
        # The repository is enabled and packages are available through the package manager.
        return []

    def _download_artifact(
        self, artifact: RpmArtifactInfo, guest: Guest, destination: Path
    ) -> None:
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
        """
        copr = install.Copr(logger=self.logger, guest=guest)
        copr.copr_plugin = "dnf-plugins-core"
        copr.enable_copr([self.copr_repo])
        return []
