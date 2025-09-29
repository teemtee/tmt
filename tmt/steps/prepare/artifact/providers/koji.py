"""
Koji Artifact Provider
"""

import types
from collections.abc import Iterator
from functools import cached_property
from shlex import quote
from typing import Any, Optional

import tmt.log
import tmt.utils
import tmt.utils.hints
from tmt.container import container
from tmt.steps.prepare.artifact.providers import (
    ArtifactInfo,
    ArtifactProvider,
    DownloadError,
)
from tmt.steps.provision import Guest

koji: Optional[types.ModuleType] = None

# To silence mypy
ClientSession: Any


tmt.utils.hints.register_hint(
    'koji',
    """
    The ``koji`` Python package is required by tmt for Koji integration.

    To quickly test Koji presence, you can try running:

        python -c 'import koji'

    * Users who installed tmt from PyPI should install the ``koji`` package
      via ``pip install koji``. On Fedora/RHEL systems, ``python3-gssapi``
      must be installed first to allow ``pip`` to build and use the required
      GSSAPI bindings.
    """,
)


def import_koji(logger: tmt.log.Logger) -> None:
    """Import koji module with error handling."""
    global ClientSession, koji
    try:
        import koji
        from koji import ClientSession
    except ImportError as error:
        from tmt.utils.hints import print_hints

        print_hints('koji', logger=logger)

        raise tmt.utils.GeneralError("Could not import koji package.") from error


@container
class RpmArtifactInfo(ArtifactInfo):
    """
    Represents a single RPM package.
    """

    PKG_URL = "https://kojipkgs.fedoraproject.org/packages/"  # For actual package downloads
    _raw_artifact: dict[str, str]

    @classmethod
    def from_filename(cls, filename: str) -> "RpmArtifactInfo":
        """
        Convert an RPM filename like 'tmt-1.58.0-1.fc41.noarch.rpm' into an RpmArtifactInfo.
        """

        try:
            base, arch, _ = filename.rsplit(".", 2)
            name, version, release = base.rsplit("-", 2)
        except ValueError:
            raise ValueError(f"Invalid RPM filename format: '{filename}'")

        raw_artifact = {
            "name": name,
            "version": version,
            "release": release,
            "arch": arch,
            "nvr": f"{name}-{version}-{release}",
        }
        return cls(_raw_artifact=raw_artifact)

    @property
    def id(self) -> str:
        """A koji rpm identifier"""
        return f"{self._raw_artifact['nvr']}.{self._raw_artifact['arch']}.rpm"

    @property
    def location(self) -> str:
        """Get the download URL for the given RPM metadata."""
        return (
            f"{self.PKG_URL}{self._raw_artifact['name']}/"
            f"{self._raw_artifact['version']}/"
            f"{self._raw_artifact['release']}/"
            f"{self._raw_artifact['arch']}/"
            f"{self.id}"
        )


class KojiArtifactProvider(ArtifactProvider[RpmArtifactInfo]):
    """
    Provider for downloading artifacts from Koji builds.
    Currently only supports RPM artifacts.

    Example:
        provider = KojiArtifactProvider(logger, build_id=123456)
        provider = KojiArtifactProvider(logger, task_id=654321)
        provider = KojiArtifactProvider(logger, nvr="tmt-1.58.0.dev21+gb229884df-main.fc41.noarch")
        artifacts = provider.download_artifacts(guest, Path("/tmp"), [])
    """

    API_URL = "https://koji.fedoraproject.org/kojihub"  # For metadata

    def __init__(
        self,
        logger: tmt.log.Logger,
        *,
        build_id: Optional[int] = None,
        task_id: Optional[int] = None,
        nvr: Optional[str] = None,
    ):
        super().__init__(logger)

        # Validate inputs: exactly one identifier must be provided
        provided = [arg for arg in (build_id, task_id, nvr) if arg is not None]
        if len(provided) != 1:
            raise ValueError("Exactly one of build_id, task_id, or nvr must be provided.")

        self._build_id = build_id
        self.task_id = task_id
        self.nvr = nvr
        self._session = self._initialize_session()
        self._rpm_list = self._fetch_rpms()

    @cached_property
    def build_id(self) -> Optional[int]:
        """
        Resolve and return the build ID.

        :return: Resolved build_id if provided or resolved by nvr, else None if task_id was used
        :raises GeneralError: If the build cannot be found
        """
        if self._build_id is not None:
            return self._build_id
        if self.nvr is not None:
            build = self._call_api("getBuild", self.nvr)
            if not build or "id" not in build:
                raise tmt.utils.GeneralError(f"No build found for NVR '{self.nvr}'.")
            build_id = build["id"]
            assert isinstance(build_id, int)
            return build_id
        return None

    def _fetch_rpms(self) -> list[dict[str, Any]]:
        """
        Fetch and cache the list of RPMs from the given identifier.
        """
        if self.task_id is not None:
            filenames = self._call_api("listTaskOutput", self.task_id) or []
            # Convert filenames into dicts for RpmArtifactInfo.
            # TODO: Check if there's a better way via the API to get metadata directly.
            return [
                RpmArtifactInfo.from_filename(f)._raw_artifact
                for f in filenames
                if f.endswith(".rpm")
            ]
        return self._call_api('listBuildRPMs', self.build_id) or []

    def _initialize_session(self) -> 'ClientSession':
        """
        A koji session initialized via the koji.ClientSession function.
        api_url being the base URL for the koji instance
        """
        import_koji(self.logger)

        try:
            return ClientSession(self.API_URL)
        except Exception as error:
            raise tmt.utils.GeneralError("Failed to initialize API session.") from error

    def _call_api(self, method: str, *args: Any, **kwargs: Any) -> Any:
        """
        Generic API call method with error handling.

        :param method: API method name to call
        :param args: Positional arguments for the API call
        :param kwargs: Keyword arguments for the API call
        :return: API response
        :raises GeneralError: If API call fails
        """
        try:
            method_callable = getattr(self._session, method)
            return method_callable(*args, **kwargs)
        except Exception as error:
            raise tmt.utils.GeneralError(f"API call '{method}' failed.") from error

    def list_artifacts(self) -> Iterator[RpmArtifactInfo]:
        """
        List all RPM artifacts for the given build.
        """
        for rpm in self._rpm_list:
            yield RpmArtifactInfo(_raw_artifact=rpm)

    def _download_artifact(
        self, artifact: RpmArtifactInfo, guest: Guest, destination: tmt.utils.Path
    ) -> None:
        """
        Download the specified artifact to the given destination on the guest.

        :param artifact: The artifact to download
        :param guest: The guest where the artifact should be downloaded
        :param destination: The destination path on the guest
        """
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
