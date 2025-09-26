"""
Koji Artifact Provider
"""

import os
import types
from collections.abc import Iterator
from shlex import quote
from typing import Any, Optional

import tmt.log
import tmt.utils
import tmt.utils.hints
from tmt.container import container
from tmt.steps.prepare.artifact.providers import (
    ArtifactInfo,
    ArtifactProvider,
    ArtifactProviderId,
    DownloadError,
    provides_artifact_provider,
)
from tmt.steps.provision import Guest

koji: Optional[types.ModuleType] = None

# To silence mypy
ClientSession: Any


def import_koji(logger: tmt.log.Logger) -> None:
    """Import koji module with error handling."""
    global ClientSession, koji
    try:
        import koji
        from koji import ClientSession
    except ImportError as error:
        from tmt.utils.hints import print_hints

        print_hints('artifact-provider/koji/koji', logger=logger)

        raise tmt.utils.GeneralError("Could not import koji package.") from error


@container
class RpmArtifactInfo(ArtifactInfo):
    """
    Represents a single RPM package.
    """

    BASE_URL = os.getenv("RPM_BASE_URL", "https://kojipkgs.fedoraproject.org/packages").rstrip(
        "/"
    )  # For actual package downloads
    _raw_artifact: dict[str, str]

    @property
    def id(self) -> str:
        """A koji rpm identifier"""
        return f"{self._raw_artifact['nvr']}.{self._raw_artifact['arch']}.rpm"

    @property
    def location(self) -> str:
        """Get the download URL for the given RPM metadata."""
        return (
            f"{self.BASE_URL}/{self._raw_artifact['name']}/"
            f"{self._raw_artifact['version']}/"
            f"{self._raw_artifact['release']}/"
            f"{self._raw_artifact['arch']}/"
            f"{self.id}"
        )


# ignore[type-arg]: TypeVar in provider registry annotations is
# puzzling for type checkers. And not a good idea in general, probably.
@provides_artifact_provider(  # type: ignore[arg-type]
    'koji',
    hints={
        'koji': """
        The ``koji`` Python package is required by tmt for Koji integration.

        To quickly test Koji presence, you can try running:

            python -c 'import koji'

        * Users who installed tmt from PyPI should install the ``koji`` package
          via ``pip install koji``. On Fedora/RHEL systems, ``python3-gssapi``
          must be installed first to allow ``pip`` to build and use the required
          GSSAPI bindings.
    """,
    },
)
class KojiArtifactProvider(ArtifactProvider[RpmArtifactInfo]):
    """
    Provider for downloading artifacts from Koji builds.

    .. note::

        Only RPMs are supported currently.

    .. code-block:: python

        provider = KojiArtifactProvider(logger, "koji.build:123456")
        artifacts = provider.download_artifacts(guest, Path("/tmp"), [])
    """

    API_URL = os.getenv("KOJI_API_URL", "https://koji.fedoraproject.org/kojihub")  # For metadata

    def __init__(self, raw_provider_id: str, logger: tmt.log.Logger):
        super().__init__(raw_provider_id, logger)
        self._session = self._initialize_session()
        self._rpm_list = self._fetch_rpms()

    def _fetch_rpms(self) -> list[dict[str, Any]]:
        """
        Fetch and cache the list of RPMs for the given artifact ID.
        """
        return self._call_api('listBuildRPMs', int(self.id)) or []

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

    @classmethod
    def _extract_provider_id(cls, raw_provider_id: str) -> ArtifactProviderId:
        # Eg: 'koji.build:123456'
        prefix = "koji.build:"
        if not raw_provider_id.startswith(prefix):
            raise ValueError(f"Invalid Koji identifier: '{raw_provider_id}'.")

        parsed = raw_provider_id[len(prefix) :]
        if not parsed.isdigit():
            raise ValueError(f"Invalid Koji identifier: '{raw_provider_id}'.")
        return parsed

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
