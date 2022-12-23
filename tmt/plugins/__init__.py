# coding: utf-8

""" Handle Plugins """

import importlib
import os
import pkgutil
import sys
from types import ModuleType
from typing import (Any, Generator, Generic, Optional, Tuple, Type, TypeVar,
                    cast)

if sys.version_info < (3, 9):
    from importlib_metadata import entry_points
else:
    from importlib.metadata import entry_points

import fmf

import tmt
import tmt.utils
from tmt.steps import STEPS

log = fmf.utils.Logging('tmt').logger

# Two possibilities to load additional plugins:
# entry_points (setup_tools)
ENTRY_POINT_NAME = 'tmt.plugin'
# Directories with module in environment variable
ENVIRONMENT_NAME = 'TMT_PLUGINS'


def explore() -> None:
    """ Explore all available plugins """

    # Check all tmt steps for native plugins
    root = os.path.dirname(os.path.realpath(tmt.__file__))
    for step in STEPS:
        for module in discover(os.path.join(root, 'steps', step)):
            import_module(f'tmt.steps.{step}.{module}')
    # Check for possible plugins in the 'plugins' directory
    for module in discover(os.path.join(root, 'plugins')):
        import_module(f'tmt.plugins.{module}')

    # Check environment variable for user plugins
    try:
        paths = [
            os.path.realpath(os.path.expandvars(os.path.expanduser(path)))
            for path in os.environ[ENVIRONMENT_NAME].split(os.pathsep)]
    except KeyError:
        log.debug(f'No custom plugin locations detected in {ENVIRONMENT_NAME}.')
        paths = []
    for path in paths:
        for module in discover(path):
            if path not in sys.path:
                sys.path.insert(0, path)
            import_module(module, path=path)

    # Import by entry_points
    try:
        for found in entry_points()[ENTRY_POINT_NAME]:
            log.debug(f'Loading plugin "{found.name}" ({found.value}).')
            found.load()
    except KeyError:
        log.debug(f'No custom plugins detected for "{ENTRY_POINT_NAME}".')


ModuleT = TypeVar('ModuleT', bound=ModuleType)


# ignore[type-var,misc]: the actual type if provided by caller - the return value would be
# assigned a name, with a narrower module type. This type would be propagated into this type var.
def _import(module: str) -> ModuleT:  # type: ignore[type-var,misc]
    """
    Import a module.

    :param module: name of a module to import. It may represent a submodule as well,
        using common dot notation (``foo.bar.baz``).
    :returns: imported module.
    :raises tmt.utils.GenericError: when import fails.
    """

    try:
        imported = cast(ModuleT, importlib.import_module(module))

    except ImportError as exc:
        raise tmt.utils.GeneralError("Failed to import the '{module}' module.") from exc

    # setup.py when executed during import raises SystemExit
    except SystemExit as exc:
        raise tmt.utils.GeneralError("Failed to import the '{module}' module.") from exc

    if module not in sys.modules:
        raise tmt.utils.GeneralError(f"Module '{module}' imported but not accessible.")

    log.debug(f"Successfully imported the '{module}' module.")

    return imported


# ignore[type-var,misc]: the actual type if provided by caller - the return value would be
# assigned a name, with a narrower module type. This type would be propagated into this type var.
def _import_or_raise(
        module: str,
        exc_class: Type[BaseException],
        exc_message: str) -> ModuleT:  # type: ignore[type-var,misc]
    """
    Import a module, or raise an exception.

    :param module: name of a module to import. It may represent a submodule as well,
        using common dot notation (``foo.bar.baz``).
    :param exc_class: an exception class to raise on failure.
    :param exc_message: an exception message.
    :returns: imported module.
    """

    try:
        return _import(module)

    except tmt.utils.GeneralError as exc:
        raise exc_class(exc_message) from exc


# ignore[type-var,misc]: the actual type if provided by caller - the return value would be
# assigned a name, with a narrower module type. This type would be propagated into this type var.
def import_module(module: str, path: str = '.') -> ModuleT:  # type: ignore[type-var,misc]
    """
    Import a module.

    :param module: name of a module to import. It may represent a submodule as well,
        using common dot notation (``foo.bar.baz``).
    :param path: if specified, it would be incorporated in exception message.
    :returns: imported module.
    :raises SystemExit: when import fails.
    """

    return _import_or_raise(
        module,
        SystemExit,
        f"Failed to import the '{module}' module from '{path}'."
        )


class LazyModuleImporter(Generic[ModuleT]):
    def __init__(
            self,
            module: str,
            exc_class: Type[Exception],
            exc_message: str
            ) -> None:
        self._module_name = module
        self._exc_class = exc_class
        self._exc_message = exc_message

        self._module: Optional[ModuleT] = None

    def __call__(self) -> ModuleT:
        if self._module is None:
            self._module = _import_or_raise(self._module_name, self._exc_class, self._exc_message)

        assert self._module  # narrow type
        return self._module


def import_member(module_name: str, member_name: str) -> Tuple[ModuleT, Any]:
    """ Import member from given module, handle errors nicely """

    module: ModuleT = import_module(module_name)

    # Get the member and return it
    if not hasattr(module, member_name):
        raise tmt.utils.GeneralError(f"No such member '{member_name}' in module '{module_name}'.")

    return (module, getattr(module, member_name))


def discover(path: str) -> Generator[str, None, None]:
    """ Discover available plugins for given paths """
    for _, name, package in pkgutil.iter_modules([path]):
        if not package:
            yield name
