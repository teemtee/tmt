"""
Copr Build Artifact Provider
"""

import types
from collections.abc import Sequence
from functools import cached_property
from shlex import quote
from typing import TYPE_CHECKING, Any, Optional
from urllib.parse import urljoin

import requests

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
from tmt.utils import ShellScript

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
            provide:
              - copr.build:1784470:fedora-32-x86_64
    """

    def __init__(self, raw_provider_id: str, repository_priority: int, logger: tmt.log.Logger):
        super().__init__(raw_provider_id, repository_priority, logger)
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

    @cached_property
    def is_pulp(self) -> bool:
        """
        Check if the build is stored in Pulp.
        """
        assert self.build_info is not None
        project = self._session.project_proxy.get(
            self.build_info.ownername, self.build_info.projectname
        )
        return project is not None and project.storage == "pulp"

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

    def _fetch_results_json(self) -> list[dict[str, str]]:
        """
        Fetch results.json for Pulp builds.

        :returns: list of package dictionaries containing NEVRA info.
        """
        results_url = urljoin(self.result_url.rstrip("/") + "/", "results.json")
        self.logger.debug(f"Fetching results.json from '{results_url}'.")
        try:
            with tmt.utils.retry_session(logger=self.logger) as session:
                response = session.get(results_url)
                response.raise_for_status()
                data = response.json()
        except Exception:
            # Idea is not to fail the whole process if results.json is missing
            self.logger.warning(f"Failed to download: '{results_url}'.")
            return []
        packages = data.get("packages")
        if not isinstance(packages, list):
            # Again, idea is not to fail the whole process if results.json is invalid
            self.logger.warning(
                f"Invalid results.json format from '{results_url}', expected a list of packages."
            )
            return []
        return packages

    def make_rpm_artifact(self, rpm_meta: dict[str, str]) -> RpmArtifactInfo:
        name = rpm_meta["name"]
        version = rpm_meta["version"]
        release = rpm_meta["release"]
        arch = rpm_meta["arch"]
        nvr = f"{name}-{version}-{release}"
        filename = f"{nvr}.{arch}.rpm"

        artifact = RpmArtifactInfo(
            _raw_artifact={
                **rpm_meta,
                "nvr": nvr,
            }
        )

        if self.is_pulp:
            assert self.build_info is not None
            base_url = f"{self.build_info.repo_url}/{self.chroot}/Packages/{filename[0]}"
        else:
            base_url = self.result_url.rstrip("/")

        artifact._raw_artifact["url"] = f"{base_url}/{filename}"
        return artifact

    @cached_property
    def artifacts(self) -> Sequence[RpmArtifactInfo]:
        self.logger.debug(f"Fetching RPMs for build '{self.build_id}' in chroot '{self.chroot}'.")
        rpm_metas = self._fetch_results_json() if self.is_pulp else self.build_packages

        return [self.make_rpm_artifact(rpm_meta) for rpm_meta in rpm_metas]

    def contribute_to_shared_repo(
        self,
        guest: Guest,
        source_path: tmt.utils.Path,
        shared_repo_dir: tmt.utils.Path,
        exclude_patterns: Optional[list[tmt.utils.Pattern[str]]] = None,
    ) -> None:
        guest.execute(
            ShellScript(f"cp {quote(str(source_path))}/*.rpm {quote(str(shared_repo_dir))}")
        )
        self.logger.info(f"Contributed artifacts from '{source_path}' to '{shared_repo_dir}'.")
