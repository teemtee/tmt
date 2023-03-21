# coding: utf-8

""" Handle Plugins """

import importlib
import os
import pkgutil
import sys
from typing import Any, Generator, List, Optional, Tuple

if sys.version_info < (3, 9):
    from importlib_metadata import entry_points
else:
    from importlib.metadata import entry_points

import tmt
from tmt.log import Logger
from tmt.steps import STEPS
from tmt.utils import Path

# Two possibilities to load additional plugins:
# entry_points (setup_tools)
ENTRY_POINT_NAME = 'tmt.plugin'
# Directories with module in environment variable
ENVIRONMENT_NAME = 'TMT_PLUGINS'

# Make a note when plugins have been already explored
ALREADY_EXPLORED = False

_TMT_ROOT = Path(tmt.__file__).resolve().parent


def discover(path: Path) -> Generator[str, None, None]:
    """ Discover available plugins for given paths """
    for _, name, package in pkgutil.iter_modules([str(path)]):
        if not package:
            yield name


#
# Explore available sources, and load all plugins found. Possible sources are:
#
# * tmt's own packages (_explore_packages)
#    - tmt.steps.*
#    - tmt.export
#    - tmt.plugins
#
# * directories (_explore_directories)
#    - directories listed in TMT_PLUGINS envvar
#
# * packaging entry points (_explore_entry_points)
#    - tmt.plugin
#

# A list of tmt (sub)packages that may contain plugins. For each package, we
# track the package name and its path relative to tmt package sources.
#
# If you think of adding new package with plugins tmt should load on start,
# this is the place.
_DISCOVER_PACKAGES: List[Tuple[str, Path]] = [
    (f'tmt.steps.{step}', Path('steps') / step)
    for step in STEPS
    ] + [
    ('tmt.plugins', Path('plugins')),
    ('tmt.export', Path('export'))
    ]


def _explore_package(package: str, path: Path, logger: Logger) -> None:
    """ Import plugins from a given Python package """

    logger.debug(f"Import plugins from the '{package}' package.")
    logger = logger.descend()

    for module in discover(path):
        import_(module=f'{package}.{module}', logger=logger)


def _explore_directory(path: Path, logger: Logger) -> None:
    """ Import plugins dropped into a directory """

    logger.debug(f"Import plugins from the '{path}' directory.")
    logger = logger.descend()

    _path = str(path)

    for module in discover(path):
        if _path not in sys.path:
            sys.path.insert(0, _path)

        import_(module=module, path=path, logger=logger)


def _explore_custom_directories(logger: Logger) -> None:
    """ Import plugins from directories listed in ``TMT_PLUGINS`` envvar """

    logger.debug('Import plugins from custom directories.')
    logger = logger.descend()

    if not os.environ.get(ENVIRONMENT_NAME):
        logger.debug(
            f"No custom directories found in the '{ENVIRONMENT_NAME}' environment variable.")
        return

    for _path in os.environ[ENVIRONMENT_NAME].split(os.pathsep):
        _explore_directory(
            Path(os.path.expandvars(os.path.expanduser(_path))).resolve(),
            logger)


def _explore_entry_point(entry_point: str, logger: Logger) -> None:
    """ Import all plugins hooked to an entry points """

    logger.debug(f"Import plugins from the '{entry_point}' entry point.")
    logger = logger.descend()

    try:
        for found in entry_points()[entry_point]:
            logger.debug(f"Loading plugin '{found.name}' ({found.value}).")
            found.load()

    except KeyError:
        logger.debug(f"No plugins detected for the '{entry_point}' entry point.")


def _explore_packages(logger: Logger) -> None:
    """ Import all plugins bundled into tmt package """

    logger.debug('Import plugins from tmt packages.')

    for name, path in _DISCOVER_PACKAGES:
        _explore_package(name, _TMT_ROOT / path, logger.descend())


def _explore_directories(logger: Logger) -> None:
    """ Import all plugins from various directories """

    logger.debug('Import plugins from custom directories.')

    _explore_custom_directories(logger.descend())


def _explore_entry_points(logger: Logger) -> None:
    """ Import all plugins hooked to entry points """

    logger.debug('Import plugins from entry points.')

    _explore_entry_point(ENTRY_POINT_NAME, logger.descend())


def explore(logger: Logger, again: bool = False) -> None:
    """
    Explore all available plugin locations

    By default plugins are explored only once to save time. Repeated
    call does not have any effect. Use ``again=True`` to force plugin
    exploration even if it has been already completed before.
    """

    # Nothing to do if already explored
    global ALREADY_EXPLORED
    if ALREADY_EXPLORED and not again:
        return

    _explore_packages(logger)
    _explore_directories(logger)
    _explore_entry_points(logger)

    ALREADY_EXPLORED = True


def import_(*, module: str, path: Optional[Path] = None, logger: Logger) -> None:
    """ Attempt to import requested module """

    if module in sys.modules:
        logger.debug(f"Module '{module}' already imported.")
        return

    try:
        importlib.import_module(module)
        logger.debug(f"Successfully imported the '{module}' module.")
    except (ImportError, SystemExit) as error:
        # setup.py when executed during import raises SystemExit
        raise SystemExit(
            f"Failed to import the '{module}' module" +
            (f" from '{path}'." if path else ".")) from error


def import_member(*, module_name: str, member_name: str, logger: Logger) -> Any:
    """ Import member from given module, handle errors nicely """
    # Make sure the module is imported. It probably is, but really,
    # make sure of it.
    try:
        import_(module=module_name, logger=logger)
    except SystemExit as exc:
        raise tmt.utils.GeneralError(f"Failed to import module '{module_name}'.") from exc

    # Now the module should be available in `sys.modules` like any
    # other, and we can go and grab the class we need from it.
    if module_name not in sys.modules:
        raise tmt.utils.GeneralError(f"Failed to import module '{module_name}'.")
    module = sys.modules[module_name]

    # Get the member and return it
    if not hasattr(module, member_name):
        raise tmt.utils.GeneralError(f"No such member '{member_name}' in module '{module_name}'.")
    return getattr(module, member_name)


# Small helper for one specific package - export plugins are needed when
# generating docs.
def explore_export_package(logger: Logger) -> None:
    """ Import all plugins bundled into tmt.export package """

    _explore_package('tmt.export', _TMT_ROOT / 'export', logger.descend())
