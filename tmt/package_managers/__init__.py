import abc
import configparser
import enum
import re
import shlex
from collections.abc import Iterable, Iterator, Sequence
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    ClassVar,
    Generic,
    Optional,
    TypedDict,
    TypeVar,
    Union,
)
from urllib.parse import urlparse

import tmt.log
import tmt.plugins
import tmt.utils
from tmt.container import container, simple_field
from tmt.utils import Command, CommandOutput, GeneralError, Path, PrepareError, ShellScript

if TYPE_CHECKING:
    from tmt._compat.typing import TypeAlias
    from tmt.guest import Guest
    from tmt.package_managers._rpm import RpmVersion

    #: A type of package manager names.
    GuestPackageManager: TypeAlias = str

    #: A package origin: either an actual repository name or a :class:`SpecialPackageOrigin`.
    PackageOrigin: TypeAlias = Union[str, 'SpecialPackageOrigin']


#: Directory where DNF/YUM repository files are stored.
YUM_REPOS_DIR = Path("/etc/yum.repos.d")


class _ResolvedEntry(TypedDict):
    """
    Single entry from the YAML output of :py:meth:`PackageManagerEngine.resolve_provides`.
    """

    nevra: str
    repo_id: str


@container(frozen=True)
class Version:
    """
    Version information for artifacts.
    """

    name: str
    version: str
    release: str
    arch: str
    epoch: int = 0

    @property
    def nvra(self) -> str:
        return f"{self.name}-{self.version}-{self.release}.{self.arch}"

    @property
    def nevra(self) -> str:
        return f"{self.name}-{self.epoch}:{self.version}-{self.release}.{self.arch}"

    def __str__(self) -> str:
        return self.nvra


@container
class Repository:
    """
    Thin wrapper/holder for .repo file content
    """

    #: Content of the repository
    content: str
    #: Uniquely identifiable name
    name: str
    #: repository_ids present in the .repo file
    repo_ids: list[str] = simple_field(default_factory=list[str])

    def __post_init__(self) -> None:
        """
        Extract repository IDs from the .repo file content after initialization.

        :raises GeneralError: If the content is malformed or no repository
            sections are found.
        """
        config = configparser.ConfigParser()
        try:
            config.read_string(self.content)
            sections = config.sections()
            if not sections:
                raise GeneralError(
                    f"No repository sections found in the content for '{self.name}'."
                )
            # Store the parsed sections in our private attribute
            self.repo_ids = sections
        except configparser.MissingSectionHeaderError as error:
            raise GeneralError(
                f"No repository sections found in the content for '{self.name}'."
            ) from error
        except configparser.Error as error:
            raise GeneralError(
                f"Failed to parse the content of repository '{self.name}'. "
                "The .repo file may be malformed."
            ) from error

    @classmethod
    def from_url(
        cls, url: str, logger: tmt.log.Logger, name: Optional[str] = None
    ) -> "Repository":
        """
        Create a Repository instance by fetching content from a URL.

        :param url: The URL to fetch the repository content from.
        :param logger: Logger to use for the operation.
        :param name: Optional name for the repository. If not provided,
            derived from the URL.
        :returns: A Repository instance.
        :raises GeneralError: If fetching or parsing fails.
        """
        try:
            with tmt.utils.retry_session(logger=logger) as session:
                response = session.get(url)
                response.raise_for_status()
                content = response.text
        except Exception as error:
            raise GeneralError(f"Failed to fetch repository content from '{url}'.") from error

        if name is None:
            parsed_url = urlparse(url)
            parsed_path = parsed_url.path.rstrip('/').split('/')[-1]
            name = parsed_path.removesuffix('.repo')
            if not name:
                raise GeneralError(f"Could not derive repository name from URL '{url}'.")

        return cls(name=name, content=content)

    @classmethod
    def from_file_path(
        cls, file_path: Path, logger: tmt.log.Logger, name: Optional[str] = None
    ) -> "Repository":
        """
        Create a Repository instance by reading content from a local file path.

        :param file_path: The local path to the repository file.
        :param logger: Logger to use for the operation.
        :param name: Optional name for the repository. If not provided,
            derived from the file path.
        :returns: A Repository instance.
        :raises GeneralError: If reading the file fails.
        """
        try:
            content = file_path.read_text()
        except OSError as error:
            raise GeneralError(f"Failed to read repository file '{file_path}'.") from error

        if name is None:
            name = file_path.stem
            if not name:
                raise GeneralError(
                    f"Could not derive repository name from file path '{file_path}'."
                )

        return cls(name=name, content=content)

    @classmethod
    def from_content(cls, content: str, name: str, logger: tmt.log.Logger) -> "Repository":
        """
        Create a Repository instance directly from provided content string.

        :param content: The string content of the repository.
        :param name: The name for the repository (required when using content).
        :param logger: Logger to use for the operation.
        :returns: A Repository instance.
        :raises GeneralError: If the name is empty.
        """
        if not name:
            raise GeneralError("Repository name cannot be empty.")
        return cls(name=name, content=content)

    @property
    def filename(self) -> str:
        """The name of the .repo file (e.g., 'my-repo.repo')."""
        return f"{tmt.utils.sanitize_name(self.name, allow_slash=False)}.repo"


class SpecialPackageOrigin(str, enum.Enum):
    """
    Sentinel values used in place of an actual repository name to convey
    special package states returned by :py:meth:`PackageManager.get_package_origin`.
    """

    #: Package is not installed on the guest.
    NOT_INSTALLED = '<not-installed>'
    #: Package is installed but its source repository cannot be determined
    #: (e.g. pre-installed in a container image).
    UNKNOWN = '<unknown>'


#
# Installable objects
#
class Package(str):
    """
    A package name
    """

    def __lt__(self, other: Any) -> bool:
        if not isinstance(other, (Package, PackageUrl, FileSystemPath, PackagePath)):
            raise NotImplementedError

        return str(self) < str(other)


class PackageUrl(str):
    """
    A URL of a package file
    """

    def __lt__(self, other: Any) -> bool:
        if not isinstance(other, (Package, PackageUrl, FileSystemPath, PackagePath)):
            raise NotImplementedError

        return str(self) < str(other)


class FileSystemPath(Path):
    """
    A filesystem path provided by a package
    """

    def __lt__(self, other: Any) -> bool:
        if not isinstance(other, (Package, PackageUrl, FileSystemPath, PackagePath)):
            raise NotImplementedError

        return str(self) < str(other)


class PackagePath(Path):
    """
    A path to a package file
    """

    def __lt__(self, other: Any) -> bool:
        if not isinstance(other, (Package, PackageUrl, FileSystemPath, PackagePath)):
            raise NotImplementedError

        return str(self) < str(other)


#: All installable objects.
Installable = Union[Package, FileSystemPath, PackagePath, PackageUrl]


# PLC0105: typevar name does not reflect its covariance, but that's fine.
PackageManagerEngineT = TypeVar(  # noqa: PLC0105
    'PackageManagerEngineT', bound='PackageManagerEngine', covariant=True
)
PackageManagerClass = type['PackageManager[PackageManagerEngineT]']


_PACKAGE_MANAGER_PLUGIN_REGISTRY: tmt.plugins.PluginRegistry[
    'PackageManagerClass[PackageManagerEngine]'
] = tmt.plugins.PluginRegistry('package_managers')

provides_package_manager: Callable[
    [str],
    Callable[
        ['PackageManagerClass[PackageManagerEngine]'], 'PackageManagerClass[PackageManagerEngine]'
    ],
] = _PACKAGE_MANAGER_PLUGIN_REGISTRY.create_decorator()


def find_package_manager(
    name: 'GuestPackageManager',
) -> 'PackageManagerClass[PackageManagerEngine]':
    """
    Find a package manager by its name.

    :raises GeneralError: when the plugin does not exist.
    """

    plugin = _PACKAGE_MANAGER_PLUGIN_REGISTRY.get_plugin(name)

    if plugin is None:
        raise tmt.utils.GeneralError(
            f"Package manager '{name}' was not found in package manager registry."
        )

    return plugin


def escape_installables(*installables: Installable) -> Iterator[str]:
    for installable in installables:
        yield shlex.quote(str(installable))


# TODO: find a better name, "options" is soooo overloaded...
@container
class Options:
    #: A list of packages to exclude from installation.
    excluded_packages: list[Package] = simple_field(default_factory=list[Package])

    #: If set, a failure to install a given package would not cause an error.
    skip_missing: bool = False

    #: If set, check whether the package is already installed, and do not
    #: attempt to install it if it is already present.
    check_first: bool = True

    #: If set, install packages under this path instead of the usual system
    #: root.
    install_root: Optional[Path] = None

    #: If set, instruct package manager to behave as if the distribution release
    #: was ``release_version``.
    release_version: Optional[str] = None

    #: If set, instruct package manager to install from untrusted sources.
    allow_untrusted: bool = False


class PackageManagerEngine(tmt.utils.Common):
    command: Command
    options: Command

    def __init__(self, *, guest: 'Guest', logger: tmt.log.Logger) -> None:
        super().__init__(logger=logger)

        self.guest = guest

        self.command, self.options = self.prepare_command()

    @abc.abstractmethod
    def prepare_command(self) -> tuple[Command, Command]:
        """
        Prepare installation command and subcommand options
        """

        raise NotImplementedError

    @abc.abstractmethod
    def check_presence(self, *installables: Installable) -> ShellScript:
        """
        Return a presence status for each given installable
        """

        raise NotImplementedError

    @abc.abstractmethod
    def install(
        self,
        *installables: Installable,
        options: Optional[Options] = None,
    ) -> ShellScript:
        raise NotImplementedError

    @abc.abstractmethod
    def reinstall(
        self,
        *installables: Installable,
        options: Optional[Options] = None,
    ) -> ShellScript:
        raise NotImplementedError

    @abc.abstractmethod
    def install_debuginfo(
        self,
        *installables: Installable,
        options: Optional[Options] = None,
    ) -> ShellScript:
        raise NotImplementedError

    @abc.abstractmethod
    def refresh_metadata(self) -> ShellScript:
        raise NotImplementedError

    def install_repository(self, repository: "Repository") -> ShellScript:
        """
        Install a repository by placing its configuration in /etc/yum.repos.d/.

        :param repository: The repository to install.
        :returns: A shell script to install the repository.
        """
        raise NotImplementedError

    def list_packages(self, repository: "Repository") -> ShellScript:
        """
        List packages available in the specified repository.

        :param repository: The repository to query.
        :returns: A shell script to list packages in the repository.
        :raises NotImplementedError: If the package manager does not support listing packages.
        """
        raise NotImplementedError

    def get_package_origin(self, packages: Iterable[str]) -> ShellScript:
        """
        List source repositories for each installed package.

        The script must emit one line per package in the format::

            <name> <origin>

        Empty lines are allowed and will be ignored by the caller.  If
        the origin field is omitted the package is treated as having an
        unknown source repository (equivalent to
        :py:attr:`SpecialPackageOrigin.UNKNOWN`).  Packages whose name
        does not appear in the output at all are treated as not installed
        (equivalent to :py:attr:`SpecialPackageOrigin.NOT_INSTALLED`).

        :param packages: Package names to query.
        :returns: A shell script to list source repositories for the given packages.
        :raises NotImplementedError: If the package manager does not support this query.
        """
        raise NotImplementedError

    def resolve_provides(
        self,
        provides: Sequence[str],
        repo_ids: Iterable[str] = (),
    ) -> ShellScript:
        """
        Resolves each provide to the NEVRAs of packages that provide it.

        The script must emit YAML mapping each provide string to a list of
        mappings with ``nevra`` and ``repo_id`` keys, or an empty value when
        nothing provides it, e.g.

        .. code-block:: yaml

            '/usr/bin/cmake':
                - nevra: 'cmake-0:3.31.6-4.fc43.x86_64'
                  repo_id: 'updates'
            '/usr/bin/non-existent-provides':
            'make':
                - nevra: 'make-1:4.4.1-8.fc43.x86_64'
                  repo_id: 'fedora'

        :param provides: Provides to resolve.
        :param repo_ids: Restrict the query to these repository IDs; searches all enabled
            repositories when not provided.
        :returns: A shell script emitting the YAML mapping described above.
        :raises PrepareError: If the package manager does not support this query.
        """
        raise PrepareError("Package manager does not support provides resolution.")

    def create_repository(self, directory: Path) -> ShellScript:
        """
        Create repository metadata for package files in the given directory.

        :param directory: The path to the directory containing packages.
        :returns: A shell script to create repository metadata.
        :raises PrepareError: If this package manager does not support creating repositories.
        """
        raise PrepareError("Package Manager not supported for create_repository")


class PackageManager(tmt.utils.Common, Generic[PackageManagerEngineT]):
    """
    A base class for package manager plugins
    """

    NAME: str

    _engine_class: type[PackageManagerEngineT]
    engine: PackageManagerEngineT

    #: Patterns for extracting failed package names from error output.
    #: Subclasses override this with their own specific patterns.
    _FAILED_PACKAGE_INSTALLATION_PATTERNS: ClassVar[list[re.Pattern[str]]] = []

    #: If set, this package manager can be used for building derived
    #: images under the hood of the ``bootc`` package manager.
    bootc_builder: bool = False

    #: A command to run to check whether the package manager is available on
    #: a guest.
    probe_command: Command

    #: Package managers with higher value would be preferred when more
    #: one package manager is detected on guest. For most of the time,
    #: the default is sufficient, but some families of package managers
    #: (looking at you, ``yum``, ``dnf``, ``dnf5``, ``rpm-ostree``!)
    #: may be installed togethers, and therefore a priority is needed.
    probe_priority: int = 0

    def __init__(self, *, guest: 'Guest', logger: tmt.log.Logger) -> None:
        super().__init__(logger=logger)

        self.engine = self._engine_class(guest=guest, logger=logger)

        self.guest = guest

    @abc.abstractmethod
    def check_presence(self, *installables: Installable) -> dict[Installable, bool]:
        """
        Return a presence status for each given installable
        """

        raise NotImplementedError

    def extract_package_name_from_package_manager_output(self, output: str) -> Iterator[str]:
        """
        Extract failed package names from package manager error output.

        :param output: Error output (stdout or stderr) from the package manager.
        :returns: An iterator of package names that failed to install.
        """
        for pattern in self._FAILED_PACKAGE_INSTALLATION_PATTERNS:
            for match in pattern.finditer(output):
                yield match.group(1)

    def install(
        self,
        *installables: Installable,
        options: Optional[Options] = None,
    ) -> CommandOutput:
        return self.guest.execute(self.engine.install(*installables, options=options))

    def reinstall(
        self,
        *installables: Installable,
        options: Optional[Options] = None,
    ) -> CommandOutput:
        return self.guest.execute(self.engine.reinstall(*installables, options=options))

    def install_debuginfo(
        self,
        *installables: Installable,
        options: Optional[Options] = None,
    ) -> CommandOutput:
        return self.guest.execute(self.engine.install_debuginfo(*installables, options=options))

    def refresh_metadata(self) -> CommandOutput:
        return self.guest.execute(self.engine.refresh_metadata())

    def install_repository(self, repository: "Repository") -> CommandOutput:
        """
        Install a repository by placing its configuration in /etc/yum.repos.d/
        and refresh the package manager cache.

        :param repository: The repository to install.
        :returns: The output of the command execution.
        """
        return self.guest.execute(self.engine.install_repository(repository))

    def list_packages(self, repository: "Repository") -> list[Version]:
        """
        List packages available in the specified repository.

        :param repository: The repository to query.
        :returns: A list of versions available in the repository.
        """
        raise NotImplementedError

    def get_package_origin(self, packages: Iterable[str]) -> 'dict[str, PackageOrigin]':
        """
        Get the repository each package was installed from.

        :param packages: Package names to query.
        :returns: A mapping of package names to source repository names.
            Packages not installed are mapped to
            :py:attr:`SpecialPackageOrigin.NOT_INSTALLED`. Packages whose
            source repository is unknown are mapped to
            :py:attr:`SpecialPackageOrigin.UNKNOWN`.
        """
        result: dict[str, PackageOrigin] = dict.fromkeys(
            packages, SpecialPackageOrigin.NOT_INSTALLED
        )
        script = self.engine.get_package_origin(result.keys())
        output = self.guest.execute(script)
        for line in (output.stdout or '').strip().splitlines():
            # Empty lines are allowed by the engine contract.
            if not line.strip():
                continue
            parts = line.split(maxsplit=1)
            package = parts[0]
            # Omitted origin field → unknown source repository.
            result[package] = parts[1] if len(parts) == 2 else SpecialPackageOrigin.UNKNOWN
        return result

    def resolve_provides(
        self,
        provides: Sequence[str],
        repo_ids: Iterable[str] = (),
    ) -> dict[str, list['RpmVersion']]:
        """
        Map each provide to the :py:class:`RpmVersion` objects of packages that provide it.

        :param provides: Provides to resolve.
        :param repo_ids: Restrict the query to these repository IDs; searches all enabled
            repositories when not provided.
        :returns: Mapping from each provide to a list of :py:class:`RpmVersion` objects,
            each carrying the NEVRA and source repository. Every requested provide appears
            as a key; provides with no match map to an empty list.
        """
        from tmt.package_managers._rpm import RpmVersion

        if not provides:
            return {}
        output = self.guest.execute(self.engine.resolve_provides(provides, repo_ids=repo_ids))

        result: dict[str, list[RpmVersion]] = {provide: [] for provide in provides}

        assert output.stdout is not None  # narrow type
        provides_yaml: dict[str, Optional[list[_ResolvedEntry]]] = tmt.utils.from_yaml(
            output.stdout
        )

        for provide, nevras in provides_yaml.items():
            if nevras is None:
                self.info(f"Nothing provides '{provide}'.")
                continue
            for resolved_provide in nevras:
                try:
                    result[provide].append(
                        RpmVersion.from_nevra(
                            resolved_provide['nevra'], repo_id=resolved_provide['repo_id']
                        )
                    )
                except ValueError as error:
                    raise PrepareError(
                        f"Cannot parse '{resolved_provide}' for provide '{provide}'."
                    ) from error

        return result

    def create_repository(self, directory: Path) -> CommandOutput:
        """
        Wrapper of :py:meth:`PackageManagerEngine.create_repository`.
        """
        return self.guest.execute(self.engine.create_repository(directory))

    def install_from_repository(
        self,
        *installables: Installable,
        options: Optional[Options] = None,
    ) -> CommandOutput:
        """
        Install packages from a repository
        """
        return self.install(*installables, options=options)

    def install_local(
        self,
        *installables: Installable,
        options: Optional[Options] = None,
    ) -> CommandOutput:
        """
        Install packages stored in a local directory
        """
        return self.install(*installables, options=options)

    def install_from_url(
        self,
        *installables: Installable,
        options: Optional[Options] = None,
    ) -> CommandOutput:
        """
        Install packages stored on a remote URL
        """
        return self.install(*installables, options=options)

    def assert_config_manager(self) -> None:
        """
        Make sure the ``config-manager`` plugin for repository management is installed.
        """
        raise PrepareError(f"Package manager '{self.NAME}' does not support config-manager.")

    def enable_copr(self, *repositories: str) -> None:
        """
        Enable requested copr repositories
        """
        if repositories:
            raise PrepareError(
                f"Package manager '{self.NAME}' does not support enabling COPR repositories."
            )

    def finalize_installation(self) -> CommandOutput:
        """
        Perform any post-installation steps.
        """
        return CommandOutput(stdout=None, stderr=None)
