"""
Copr Build Artifact Provider
"""

import types
from collections.abc import Sequence
from functools import cached_property
from typing import Any, Optional

import tmt.log
import tmt.utils
import tmt.utils.hints
from tmt.container import container, simple_field
from tmt.package_managers._rpm import RpmVersion
from tmt.steps.prepare.artifact.providers import (
    ArtifactInfo,
    ArtifactProvider,
    ArtifactProviderId,
    provides_artifact_provider,
)

copr: Optional[types.ModuleType] = None

# To silence mypy
Client: Any

tmt.utils.hints.register_hint(
    'artifact-provider/copr',
    """
The ``copr`` Python package is required by tmt for Copr integration.

To quickly test Copr presence, you can try running:

    python -c 'import copr'

* Users who installed tmt from PyPI should install the ``copr`` package
  via ``pip install copr``.
""",
)


def import_copr(logger: tmt.log.Logger) -> None:
    """Import copr module with error handling."""
    global copr, Client
    try:
        import copr
        from copr.v3 import Client
    except ImportError as error:
        from tmt.utils.hints import print_hints

        print_hints('artifact-provider/copr', logger=logger)

        raise tmt.utils.GeneralError("Could not import copr package.") from error


@provides_artifact_provider("copr.build")
@container
class CoprBuildArtifactProvider(ArtifactProvider):
    """
    Provider for downloading artifacts from Copr builds.

    Identifier format: build-id:chroot-name

    Example usage:

    .. code-block:: yaml

        prepare:
          - summary: copr build artifacts
            how: artifact
            provide:
              - copr.build:1784470:fedora-32-x86_64
    """

    _session: 'Client' = simple_field(init=False)
    build_id: int = simple_field(init=False)
    chroot: str = simple_field(init=False)

    def __post_init__(self) -> None:
        super().__post_init__()
        self._session = self._initialize_session()
        try:
            build_id_str, chroot = self.id.split(":", 1)
            self.build_id = int(build_id_str)
            self.chroot = chroot
        except (ValueError, IndexError) as error:
            raise ValueError(f"Invalid provider id '{self.id}'.") from error

    def _initialize_session(self) -> 'Client':
        """
        Initialize copr client session.
        """
        import_copr(self.logger)

        try:
            config = {"copr_url": "https://copr.fedorainfracloud.org"}
            return Client(config)
        except Exception as error:
            raise tmt.utils.GeneralError("Failed to initialize Copr client session.") from error

    @classmethod
    def _extract_provider_id(cls, raw_id: str) -> ArtifactProviderId:
        try:
            _, value = raw_id.split(":", maxsplit=1)
        except Exception as error:
            raise AssertionError(
                f"Provider id '{raw_id}' is invalid, how did we get here?"
            ) from error
        return value

    def make_rpm_artifact(self, url: str) -> ArtifactInfo:
        filename = url.rstrip("/").rsplit("/", 1)[1]
        version_info = RpmVersion.from_filename(filename)
        return ArtifactInfo(
            version=version_info,
            location=url,
            provider=self,
            repo_id=self.parent.data.repository_name,
        )

    @cached_property
    def artifacts(self) -> Sequence[ArtifactInfo]:
        self.logger.debug(f"Fetching RPMs for build '{self.build_id}' in chroot '{self.chroot}'.")
        return [
            self.make_rpm_artifact(url)
            for url in self._session.build_chroot_proxy.get_results_urls(
                self.build_id, self.chroot
            )
        ]
