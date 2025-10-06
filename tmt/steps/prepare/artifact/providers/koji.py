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

    @property
    def is_draft(self) -> bool:
        """
        Whether this RPM is a draft/scratch artifact.
        """
        return bool(self._raw_artifact.get('draft', False))


@container
class KojiScratchRpmArtifactInfo(RpmArtifactInfo):
    """
    Represents a single RPM url from Koji scratch builds.
    """

    @property
    def id(self) -> str:
        return f"{self._raw_artifact['filename']}"


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

    SUPPORTED_PREFIXES = ("koji.build:", "koji.task:", "koji.nvr:")

    def __new__(cls, raw_provider_id: str, logger: tmt.log.Logger) -> 'KojiArtifactProvider':
        """
        Create a specific Koji provider based on the ``raw_provider_id`` prefix.

        The supported provides are:
        :py:class:`KojiBuild`,
        :py:class:`KojiTask`,
        :py:class:`KojiNvr`.

        :raises ValueError: If the prefix is not supported
        """
        if raw_provider_id.startswith("koji.build:"):
            return super().__new__(KojiBuild)
        if raw_provider_id.startswith("koji.task:"):
            return super().__new__(KojiTask)
        if raw_provider_id.startswith("koji.nvr:"):
            return super().__new__(KojiNvr)
        # If we get here, the prefix is not supported
        raise ValueError(
            f"Unsupported artifact ID format: '{raw_provider_id}'. "
            f"Supported formats are: 'koji.build:', 'koji.task:', 'koji.nvr:'"
        )

    def __init__(self, raw_provider_id: str, logger: tmt.log.Logger):
        super().__init__(raw_provider_id, logger)
        self._session = self._initialize_session()
        self._build_provider: Optional[KojiBuild] = None

    @cached_property
    def build_id(self) -> Optional[int]:
        """
        Resolve and return the build ID.

        - If provided directly, return it.
        - If provided via NVR, resolve using getBuild.
        - If provided via task_id, resolve using listBuilds.

        :return: The resolved build ID, or None if not found for task_id
        :raises GeneralError: If the build cannot be found
        """
        raise NotImplementedError

    @cached_property
    def rpm_list(self) -> list[RpmArtifactInfo]:
        """Return all RPM artifacts for the given identifier."""
        raise NotImplementedError

    def _initialize_session(self) -> 'ClientSession':
        """
        A koji session initialized via the koji.ClientSession function.
        Also sets self._topurl and self._api_url being the base URL for the koji instance
        """
        import_koji(self.logger)

        try:
            config = koji.read_config("koji")  # type: ignore[union-attr]
            self._api_url = config.get("server")
            self._topurl = config.get("topurl")
            return ClientSession(self._api_url)
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

    def _get_build_provider(self, build_id: int) -> 'KojiBuild':
        """
        Cache a KojiBuild instance to avoid redundant API calls
        """
        if not self._build_provider:
            self._build_provider = KojiBuild(f"koji.build:{build_id}", self.logger)
        return self._build_provider

    @classmethod
    def _extract_provider_id(cls, raw_provider_id: str) -> ArtifactProviderId:
        for prefix in cls.SUPPORTED_PREFIXES:
            if raw_provider_id.startswith(prefix):
                value = raw_provider_id[len(prefix) :]
                if not value:
                    raise ValueError(f"Missing value in '{raw_provider_id}'.")
                return value
        raise ValueError(f"Unsupported artifact ID format: '{raw_provider_id}'.")

    def list_artifacts(self) -> Iterator[RpmArtifactInfo]:
        """
        List all RPM artifacts for the given build.
        """
        yield from self.rpm_list

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

    def make_rpm_artifact(self, rpm_meta: dict[str, str]) -> RpmArtifactInfo:
        """
        Create a normal build RPM artifact from metadata returned by listBuildRPMs.
        """
        name = rpm_meta["name"]
        version = rpm_meta["version"]
        release = rpm_meta["release"]
        arch = rpm_meta["arch"]

        # Construct the full URL for this RPM
        url = (
            f"{self._topurl}/packages/{name}/"
            f"{version}/{release}/{arch}/"
            f"{name}-{version}-{release}.{arch}.rpm"
        )

        return RpmArtifactInfo(_raw_artifact={**rpm_meta, "url": url})

    def make_scratch_artifact(self, task_id: int, filename: str) -> KojiScratchRpmArtifactInfo:
        """
        Create a scratch RPM artifact from a task output filename.
        """
        pathinfo = koji.PathInfo(  # type: ignore[union-attr]
            topdir=self._topurl
        )
        work_path = pathinfo.work("DEFAULT")
        task_path = pathinfo.taskrelpath(task_id)
        url = f"{work_path}/{task_path}/{filename}"

        raw_artifact = {
            "filename": filename,
            "url": url,
        }
        return KojiScratchRpmArtifactInfo(_raw_artifact=raw_artifact)


@provides_artifact_provider("koji.task")  # type: ignore[arg-type]
class KojiTask(KojiArtifactProvider):
    @cached_property
    def build_id(self) -> Optional[int]:
        task_id = int(self.id)
        builds = self._call_api("listBuilds", taskID=task_id)
        if builds:
            build_id = builds[0]["build_id"]  # Assume the task produced a single build
            assert isinstance(build_id, int)
            return build_id
        return None

    def _get_task_children(self, task_id: int) -> list[int]:
        """
        Recursively fetch all child tasks of the given task ID.

        :param task_id: The parent task ID
        :return: List of all child task IDs
        """
        child_tasks: list[int] = [task_id]  # Include the parent task itself
        direct_children = self._call_api("getTaskChildren", task_id)
        for child in direct_children:
            child_id = child["id"]
            assert isinstance(child_id, int)
            child_tasks.append(child_id)
            # Recursively fetch grandchildren
            child_tasks.extend(self._get_task_children(child_id))
        return child_tasks

    @cached_property
    def rpm_list(self) -> list[RpmArtifactInfo]:
        self.logger.debug(f"Fetching RPMs for task '{self.id}'.")
        # If task produced a build, reuse build path
        if self.build_id is not None:
            self.logger.debug(
                f"Task '{self.id}' produced build '{self.build_id}', fetching RPMs from the build."
            )
            return self._get_build_provider(self.build_id).rpm_list

        # Otherwise, list the task output files for scratch builds
        self.logger.debug(f"Task '{self.id}' did not produce a build, fetching scratch RPMs.")
        rpms: list[RpmArtifactInfo] = []
        seen_ids = set()  # Multiple tasks may produce the same RPM
        for child_task in self._get_task_children(int(self.id)):
            for filename in self._call_api("listTaskOutput", child_task):
                if not filename.endswith(".rpm"):
                    self.logger.warning(f"Skipping '{filename}': not an RPM")
                    continue
                rpm = self.make_scratch_artifact(child_task, filename)
                if rpm.id not in seen_ids:
                    rpms.append(rpm)
                    seen_ids.add(rpm.id)
                else:
                    self.logger.debug(
                        f"Skipping redundant RPM '{rpm.id}' from task '{child_task}'"
                    )
        return rpms


@provides_artifact_provider('koji.build')  # type: ignore[arg-type]
class KojiBuild(KojiArtifactProvider):
    @cached_property
    def build_id(self) -> int:
        return int(self.id)

    @cached_property
    def rpm_list(self) -> list[RpmArtifactInfo]:
        """
        Resolve and return the list of RPMs for the given build ID or NVR.

        :return: List of RpmArtifactInfo objects
        """
        self.logger.debug(f"Fetching RPMs for build '{self.build_id}'.")
        rpm_dicts = self._call_api("listBuildRPMs", self.build_id)
        return [self.make_rpm_artifact(rpm) for rpm in rpm_dicts]


@provides_artifact_provider("koji.nvr")  # type: ignore[arg-type]
class KojiNvr(KojiArtifactProvider):
    @cached_property
    def build_id(self) -> int:
        nvr = self.id
        build = self._call_api("getBuild", nvr)
        if not build:
            raise tmt.utils.GeneralError(f"No build found for NVR '{nvr}'.")
        build_id = build["id"]
        assert isinstance(build_id, int)
        return build_id

    @cached_property
    def rpm_list(self) -> list[RpmArtifactInfo]:
        self.logger.debug(f"Fetching RPMs for NVR '{self.id}'.")
        return self._get_build_provider(self.build_id).rpm_list
