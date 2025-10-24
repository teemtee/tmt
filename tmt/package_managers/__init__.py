import abc
import shlex
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any, Callable, Generic, Optional, TypeVar, Union

import tmt
import tmt.log
import tmt.plugins
import tmt.utils
from tmt.container import container, simple_field
from tmt.utils import Command, CommandOutput, GeneralError, Path, ShellScript

if TYPE_CHECKING:
    from tmt._compat.typing import TypeAlias

    # TODO: Move Repository abstraction to tmt.package_manager subpackage
    # This class will be added in a future PR.
    # For now, just type it as Any to satisfy pyright.
    Repository: TypeAlias = Any
    from tmt.steps.provision import Guest

    #: A type of package manager names.
    GuestPackageManager: TypeAlias = str
else:
    Repository: Any = None  # type: ignore[assignment]


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


PackageManagerEngineT = TypeVar('PackageManagerEngineT', bound='PackageManagerEngine')
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
@container(frozen=True)
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


class PackageManager(tmt.utils.Common, Generic[PackageManagerEngineT]):
    """
    A base class for package manager plugins
    """

    NAME: str

    _engine_class: type[PackageManagerEngineT]
    engine: PackageManagerEngineT

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

    def list_packages(self, repository: "Repository") -> list[str]:
        """
        List packages available in the specified repository.

        :param repository: The repository to query.
        :returns: A list of package names available in the repository.
        """
        script = self.engine.list_packages(repository)
        output = self.guest.execute(script)
        stdout = output.stdout

        if stdout is None:
            raise GeneralError("Repository query provided no output")

        return stdout.strip().splitlines()
