"""
Koji Artifact Provider
"""

import types
from abc import abstractmethod
from collections.abc import Iterator, Sequence
from functools import cached_property
from shlex import quote
from typing import Any, ClassVar, Optional, TypeVar, Union
from urllib.parse import urljoin

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

    _raw_artifact: dict[str, str]

    @property
    def id(self) -> str:
        """A koji rpm identifier"""
        return f"{self._raw_artifact['nvr']}.{self._raw_artifact['arch']}.rpm"

    @property
    def location(self) -> str:
        return self._raw_artifact['url']


@container
class ScratchRpmArtifactInfo(RpmArtifactInfo):
    """
    Represents a single RPM url from Koji scratch builds.
    """

    @property
    def id(self) -> str:
        return f"{self._raw_artifact['filename']}"


BuildT = TypeVar(
    "BuildT", bound="ArtifactProvider[RpmArtifactInfo]"
)  # Generic type for build provider classes (e.g., KojiBuild, BrewBuild)
ProviderT = TypeVar(
    "ProviderT", bound="KojiArtifactProvider"
)  # Generic type for artifact provider subclasses


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

        provider = KojiArtifactProvider("koji.build:123456", logger)
        artifacts = provider.download_artifacts(guest, Path("/tmp"), [])
    """

    _REGISTRY: ClassVar[dict[str, type['KojiArtifactProvider']]] = {}
    SUPPORTED_PREFIXES: ClassVar[tuple[str, ...]] = ()

    @classmethod
    def _dispatch_subclass(
        cls, raw_provider_id: str, mapping: dict[str, type[ProviderT]]
    ) -> ProviderT:
        for prefix, subclass in mapping.items():
            if raw_provider_id.startswith(prefix):
                return super().__new__(subclass)
        raise ValueError(
            f"Unsupported artifact ID format: '{raw_provider_id}'. "
            f"Supported formats are: {', '.join(cls.SUPPORTED_PREFIXES)}"
        )

    def __new__(cls, raw_provider_id: str, logger: tmt.log.Logger) -> 'KojiArtifactProvider':
        """
        Create a specific Koji provider based on the ``raw_provider_id`` prefix.

        The supported provides are:
        :py:class:`KojiBuild`,
        :py:class:`KojiTask`,
        :py:class:`KojiNvr`.

        :raises ValueError: If the prefix is not supported
        """
        return cls._dispatch_subclass(raw_provider_id, cls._REGISTRY)

    def __init__(self, raw_provider_id: str, logger: tmt.log.Logger):
        super().__init__(raw_provider_id, logger)
        self._session = self._initialize_session()

    @cached_property
    def build_info(self) -> Optional[dict[str, Any]]:
        """
        Fetch and return the build metadata for the resolved build ID.

        :returns: the build metadata, or ``None`` if not found.
        """
        if self.build_id is None:
            return None
        build_info = self._call_api("getBuild", self.build_id)
        assert build_info is None or isinstance(build_info, dict)
        return build_info

    @cached_property
    @abstractmethod
    def build_id(self) -> Optional[int]:
        """
        Resolve and return the build ID.

        There are multiple possible ways of finding a build ID from the artifact provider inputs,
        individual artifact providers must chose the most fitting one.

        :returns: the build ID, or ``None`` if there is no build attached to this provider.
        :raises GeneralError: when the build should exist, but cannot be found in Koji.
        """
        raise NotImplementedError

    def _initialize_session(
        self, api_url: Optional[str] = None, top_url: Optional[str] = None
    ) -> 'ClientSession':
        """
        A koji session initialized via the koji.ClientSession function.

        Also :py:attr:`_top_url` and :py:attr:`_api_url` being the base URL for the Koji instance.
        """
        import_koji(self.logger)

        try:
            config = koji.read_config("koji")  # type: ignore[union-attr]
            self._api_url = api_url or config.get("server")
            self._top_url = top_url or config.get("topurl")
            return ClientSession(self._api_url)
        except Exception as error:
            raise tmt.utils.GeneralError(
                f"Failed to initialize API session from url '{self._api_url}'."
            ) from error

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

    def _make_build_provider(self, build_cls: type[BuildT], prefix: str) -> Optional[BuildT]:
        """Create a build provider instance if build_id is available."""
        if self.build_id is None:
            return None
        return build_cls(f"{prefix}:{self.build_id}", self.logger)

    @cached_property
    def build_provider(self) -> Optional['KojiBuild']:
        return self._make_build_provider(KojiBuild, "koji.build")

    @classmethod
    def _extract_provider_id(cls, raw_provider_id: str) -> ArtifactProviderId:
        for prefix in cls.SUPPORTED_PREFIXES:
            if raw_provider_id.startswith(prefix):
                value = raw_provider_id[len(prefix) + 1 :]
                if not value:
                    raise ValueError(f"Missing value in '{raw_provider_id}'.")
                return value
        raise ValueError(f"Unsupported artifact ID format: '{raw_provider_id}'.")

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

    def _rpm_url(self, rpm_meta: dict[str, str]) -> str:
        """Construct Koji RPM URL."""
        name = rpm_meta["name"]
        version = rpm_meta["version"]
        release = rpm_meta["release"]
        arch = rpm_meta["arch"]
        path = f"packages/{name}/{version}/{release}/{arch}/{name}-{version}-{release}.{arch}.rpm"
        return urljoin(self._top_url, path)

    def make_rpm_artifact(self, rpm_meta: dict[str, str]) -> RpmArtifactInfo:
        """
        Create a normal build RPM artifact from metadata returned by listBuildRPMs.
        """
        return RpmArtifactInfo(_raw_artifact={**rpm_meta, "url": self._rpm_url(rpm_meta)})


@provides_artifact_provider("koji.task")  # type: ignore[arg-type]
class KojiTask(KojiArtifactProvider):
    @cached_property
    def build_id(self) -> Optional[int]:
        task_id = int(self.id)
        if builds := self._call_api("listBuilds", taskID=task_id):
            if len(builds) > 1:
                self.logger.warning(
                    f"Task '{task_id}' produced {len(builds)} builds, using the first one."
                )
            build_id = builds[0]["build_id"]  # Assume the task produced a single build
            assert isinstance(build_id, int)
            return build_id
        return None

    def _get_task_children(self, task_id: int) -> Iterator[int]:
        """
        Fetch all descendant tasks using getTaskDescendents.

        :param task_id: the parent task ID
        :yield: task IDs including parent and all descendants
        """
        descendants_map = self._call_api("getTaskDescendents", task_id)
        for task_id_str in descendants_map:
            yield int(task_id_str)

    # ignore[override]: expected, we do want to return more specific
    # type than the one declared in superclass.
    def make_rpm_artifact(self, task_id: int, filename: str) -> ScratchRpmArtifactInfo:  # type: ignore[override]
        """
        Create a scratch RPM artifact from a task output filename.
        """
        pathinfo = koji.PathInfo(  # type: ignore[union-attr]
            topdir=self._top_url
        )
        work_path = pathinfo.work("DEFAULT")
        task_path = pathinfo.taskrelpath(task_id)
        url = f"{work_path}/{task_path}/{filename}"

        raw_artifact = {
            "filename": filename,
            "url": url,
        }
        return ScratchRpmArtifactInfo(_raw_artifact=raw_artifact)

    @cached_property
    def artifacts(self) -> Sequence[RpmArtifactInfo]:
        self.logger.debug(f"Fetching RPMs for task '{self.id}'.")
        # If task produced a build, reuse build path
        if self.build_id is not None:
            self.logger.debug(
                f"Task '{self.id}' produced build '{self.build_id}', fetching RPMs from the build."
            )
            assert self.build_provider is not None
            return list(self.build_provider.artifacts)

        # Otherwise, list the task output files for scratch builds
        self.logger.debug(f"Task '{self.id}' did not produce a build, fetching scratch RPMs.")

        artifacts: list[RpmArtifactInfo] = []
        seen_ids = set()  # Multiple tasks may produce the same RPM

        for child_task in self._get_task_children(int(self.id)):
            for filename in self._call_api("listTaskOutput", child_task):
                if not filename.endswith(".rpm"):
                    self.logger.warning(f"Skipping '{filename}': not an RPM")
                    continue
                rpm = self.make_rpm_artifact(child_task, filename)
                if rpm.id not in seen_ids:
                    artifacts.append(rpm)
                    seen_ids.add(rpm.id)
                else:
                    self.logger.debug(
                        f"Skipping redundant RPM '{rpm.id}' from task '{child_task}'"
                    )

        return artifacts


@provides_artifact_provider('koji.build')  # type: ignore[arg-type]
class KojiBuild(KojiArtifactProvider):
    @cached_property
    def build_id(self) -> int:
        return int(self.id)

    @cached_property
    def artifacts(self) -> Sequence[RpmArtifactInfo]:
        self.logger.debug(f"Fetching RPMs for build '{self.build_id}'.")

        return [
            self.make_rpm_artifact(rpm_dict)
            for rpm_dict in self._call_api("listBuildRPMs", self.build_id)
        ]


@provides_artifact_provider("koji.nvr")  # type: ignore[arg-type]
class KojiNvr(KojiArtifactProvider):
    @cached_property
    def build_info(self) -> Optional[dict[str, Any]]:
        """
        Fetch and return the build metadata for the nvr.

        :returns: the build metadata, or ``None`` if not found.
        """
        build_info = self._call_api("getBuild", self.id)
        assert build_info is None or isinstance(build_info, dict)
        return build_info

    @cached_property
    def build_id(self) -> int:
        if not self.build_info:
            raise tmt.utils.GeneralError(f"No build found for NVR '{self.id}'.")
        build_id = self.build_info["id"]
        assert isinstance(build_id, int)
        return build_id

    @cached_property
    def artifacts(self) -> Sequence[RpmArtifactInfo]:
        """
        RPM artifacts for the given NVR.
        """
        self.logger.debug(f"Fetching RPMs for NVR '{self.id}'.")
        assert self.build_provider is not None
        return list(self.build_provider.artifacts)


KojiArtifactProvider._REGISTRY = {
    "koji.build": KojiBuild,
    "koji.task": KojiTask,
    "koji.nvr": KojiNvr,
}
KojiArtifactProvider.SUPPORTED_PREFIXES = tuple(KojiArtifactProvider._REGISTRY.keys())
