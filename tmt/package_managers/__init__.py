import dataclasses
import shlex
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any, Callable, Optional, Union

import tmt
import tmt.log
import tmt.plugins
import tmt.utils
from tmt.utils import Command, CommandOutput, Path

if TYPE_CHECKING:
    from tmt._compat.typing import TypeAlias
    from tmt.steps.provision import Guest

    #: A type of package manager names.
    GuestPackageManager: TypeAlias = str


#
# Installable objects
#
class Package(str):
    """ A package name """

    def __lt__(self, other: Any) -> bool:
        if not isinstance(other, (Package, PackageUrl, FileSystemPath, PackagePath)):
            raise NotImplementedError

        return str(self) < str(other)


class PackageUrl(str):
    """ A URL of a package file """

    def __lt__(self, other: Any) -> bool:
        if not isinstance(other, (Package, PackageUrl, FileSystemPath, PackagePath)):
            raise NotImplementedError

        return str(self) < str(other)


class FileSystemPath(Path):
    """ A filesystem path provided by a package """

    def __lt__(self, other: Any) -> bool:
        if not isinstance(other, (Package, PackageUrl, FileSystemPath, PackagePath)):
            raise NotImplementedError

        return str(self) < str(other)


class PackagePath(Path):
    """ A path to a package file """

    def __lt__(self, other: Any) -> bool:
        if not isinstance(other, (Package, PackageUrl, FileSystemPath, PackagePath)):
            raise NotImplementedError

        return str(self) < str(other)


#: All installable objects.
Installable = Union[Package, FileSystemPath, PackagePath, PackageUrl]


PackageManagerClass = type['PackageManager']


_PACKAGE_MANAGER_PLUGIN_REGISTRY: tmt.plugins.PluginRegistry[PackageManagerClass] = \
    tmt.plugins.PluginRegistry()


def provides_package_manager(
        package_manager: str) -> Callable[[PackageManagerClass], PackageManagerClass]:
    """
    A decorator for registering package managers.

    Decorate a package manager plugin class to register a package manager.
    """

    def _provides_package_manager(package_manager_cls: PackageManagerClass) -> PackageManagerClass:
        _PACKAGE_MANAGER_PLUGIN_REGISTRY.register_plugin(
            plugin_id=package_manager,
            plugin=package_manager_cls,
            logger=tmt.log.Logger.get_bootstrap_logger())

        return package_manager_cls

    return _provides_package_manager


def find_package_manager(name: 'GuestPackageManager') -> 'PackageManagerClass':
    """
    Find a package manager by its name.

    :raises GeneralError: when the plugin does not exist.
    """

    plugin = _PACKAGE_MANAGER_PLUGIN_REGISTRY.get_plugin(name)

    if plugin is None:
        raise tmt.utils.GeneralError(
            f"Package manager '{name}' was not found in package manager registry.")

    return plugin


def escape_installables(*installables: Installable) -> Iterator[str]:
    for installable in installables:
        yield shlex.quote(str(installable))


# TODO: find a better name, "options" is soooo overloaded...
@dataclasses.dataclass(frozen=True)
class Options:
    #: A list of packages to exclude from installation.
    excluded_packages: list[Package] = dataclasses.field(default_factory=list)

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


class PackageManager(tmt.utils.Common):
    """ A base class for package manager plugins """

    NAME: str

    #: A command to run to check whether the package manager is available on
    #: a guest.
    probe_command: Command

    #: Package managers with higher value would be preferred when more
    #: one package manager is detected on guest. For most of the time,
    #: the default is sufficient, but some families of package managers
    #: (looking at you, ``yum``, ``dnf``, ``dnf5``, ``rpm-ostree``!)
    #: may be installed togethers, and therefore a priority is needed.
    probe_priority: int = 0

    command: Command
    options: Command

    def __init__(self, *, guest: 'Guest', logger: tmt.log.Logger) -> None:
        super().__init__(logger=logger)

        self.guest = guest
        self.command, self.options = self.prepare_command()

    def prepare_command(self) -> tuple[Command, Command]:
        """ Prepare installation command and subcommand options """
        raise NotImplementedError

    def check_presence(self, *installables: Installable) -> dict[Installable, bool]:
        """ Return a presence status for each given installable """
        raise NotImplementedError

    def install(
            self,
            *installables: Installable,
            options: Optional[Options] = None) -> CommandOutput:
        raise NotImplementedError

    def reinstall(
            self,
            *installables: Installable,
            options: Optional[Options] = None) -> CommandOutput:
        raise NotImplementedError

    def install_debuginfo(
            self,
            *installables: Installable,
            options: Optional[Options] = None) -> CommandOutput:
        raise NotImplementedError

    def refresh_metadata(self) -> CommandOutput:
        raise NotImplementedError
