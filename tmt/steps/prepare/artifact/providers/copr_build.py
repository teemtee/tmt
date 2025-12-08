"""
Copr Build Artifact Provider
"""

import types
from collections.abc import Sequence
from functools import cached_property
from shlex import quote
from typing import TYPE_CHECKING, Any, Optional
from urllib.parse import urljoin

import tmt.log
import tmt.utils
import tmt.utils.hints
from tmt.steps.prepare.artifact import RpmArtifactInfo
from tmt.steps.prepare.artifact.providers import (
    ArtifactInfo,
    ArtifactProvider,
    ArtifactProviderId,
    DownloadError,
    provides_artifact_provider,
)
from tmt.steps.provision import Guest

if TYPE_CHECKING:
    from munch import Munch

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


@provides_artifact_provider("copr.build")  # type: ignore[arg-type]
class CoprBuildArtifactProvider(ArtifactProvider[RpmArtifactInfo]):
    """
    Provider for downloading artifacts from Copr builds.

    Identifier format: build-id:chroot-name

    Example usage:

    .. code-block:: yaml

        prepare:
          - summary: copr build artifacts
            how: artifact
            stage: prepare
            provide:
              - copr.build:1784470:fedora-32-x86_64
    """

    def __init__(self, raw_provider_id: str, logger: tmt.log.Logger):
        super().__init__(raw_provider_id, logger)
        self._session = self._initialize_session()
        try:
            build_id_str, chroot = self.id.split(":", 1)
            self.build_id = int(build_id_str)
            self.chroot = chroot
        except (ValueError, IndexError) as error:
            raise ValueError(f"Invalid provider id '{self.id}'.") from error

    @cached_property
    def build_info(self) -> Optional["Munch"]:
        """
        Fetch and return the build metadata.

        :returns: the build metadata, or ``None`` if not found.
        """
        return self._session.build_proxy.get(self.build_id)

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
    def _extract_provider_id(cls, raw_provider_id: str) -> ArtifactProviderId:
        try:
            _, value = raw_provider_id.split(":", maxsplit=1)
        except Exception as error:
            raise AssertionError(
                f"Provider id '{raw_provider_id}' is invalid, how did we get here?"
            ) from error
        return value

    def _download_artifact(
        self, artifact: ArtifactInfo, guest: Guest, destination: tmt.utils.Path
    ) -> None:
        try:
            # Destination directory is guaranteed to exist, download the artifact
            guest.execute(
                tmt.utils.ShellScript(
                    f"curl -L --fail -o {quote(str(destination))} {quote(artifact.location)}"
                ),
                silent=True,
            )
        except Exception as error:
            raise DownloadError(f"Failed to download '{artifact}'.") from error

    @cached_property
    def result_url(self) -> str:
        """
        Fetch and return the result URL for the build chroot.
        """
        build_chroot = self._session.build_chroot_proxy.get(self.build_id, self.chroot)
        if not build_chroot:
            raise tmt.utils.GeneralError(
                f"Build chroot '{self.chroot}' not found for build '{self.build_id}'."
            )

        if not build_chroot.result_url:
            raise tmt.utils.GeneralError(
                f"No result URL found for build '{self.build_id}' and chroot '{self.chroot}'."
            )

        result_url = build_chroot.result_url
        assert isinstance(result_url, str)
        return result_url

    @cached_property
    def build_packages(self) -> Sequence["Munch"]:
        built_packages = self._session.build_proxy.get_built_packages(self.build_id)
        if self.chroot not in built_packages:
            raise tmt.utils.GeneralError(
                f"Chroot '{self.chroot}' not found in build '{self.build_id}'."
            )
        packages = built_packages[self.chroot]["packages"]
        assert isinstance(packages, list)
        return packages

    def make_rpm_artifact(self, rpm_meta: dict[str, str]) -> RpmArtifactInfo:
        name = rpm_meta["name"]
        version = rpm_meta["version"]
        release = rpm_meta["release"]
        artifact = RpmArtifactInfo(
            _raw_artifact={
                **rpm_meta,
                "nvr": f"{name}-{version}-{release}",
            }
        )
        artifact._raw_artifact["url"] = urljoin(self.result_url + "/", artifact.id)

        return artifact

    @cached_property
    def artifacts(self) -> Sequence[RpmArtifactInfo]:
        self.logger.debug(f"Fetching RPMs for build '{self.build_id}' in chroot '{self.chroot}'.")
        return [self.make_rpm_artifact(rpm_meta) for rpm_meta in self.build_packages]
