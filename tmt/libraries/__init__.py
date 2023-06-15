""" Handle libraries """

from typing import List, Optional, Tuple, Union

import fmf

import tmt
import tmt.base
import tmt.log
import tmt.utils
from tmt.base import Dependency, DependencyFile, DependencyFmfId, DependencySimple
from tmt.utils import Path

# A beakerlib identifier type, can be a string or a fmf id (with extra beakerlib keys)
ImportedIdentifiersType = Optional[List[Dependency]]

# A Library type, can be Beakerlib or File
# undefined references are ignored due to cyclic dependencies of these files,
# only imported in runtime where needed
LibraryType = Union['BeakerLib', 'File']  # type: ignore[name-defined] # noqa: F821

# A type for Beakerlib dependencies
LibraryDependenciesType = Tuple[
    List[Dependency], List[Dependency], List['LibraryType']
    ]


class LibraryError(Exception):
    """ Used when library cannot be parsed from the identifier """


class Library:
    """
    General library class

    Used as parent for specific libraries like beakerlib and file
    """

    def __init__(
            self,
            *,
            parent: Optional[tmt.utils.Common] = None,
            logger: tmt.log.Logger) -> None:
        """ Process the library identifier and fetch the library """
        # Use an empty common class if parent not provided (for logging, cache)
        self.parent = parent or tmt.utils.Common(logger=logger, workdir=True)
        self._logger: tmt.log.Logger = logger

        self.identifier: Dependency
        self.format: str
        self.repo: Path
        self.name: str

    @property
    def hostname(self) -> str:
        """ Get hostname from url or default to local """
        return 'local'

    @property
    def fmf_node_path(self) -> Path:
        """ Path to fmf node """
        return Path(self.name.strip('/'))

    def __str__(self) -> str:
        """ Use repo/name for string representation """
        return f"{self.repo}{self.name}"


def library_factory(
        *,
        identifier: Dependency,
        parent: Optional[tmt.utils.Common] = None,
        logger: tmt.log.Logger,
        source_location: Optional[Path] = None,
        target_location: Optional[Path] = None) -> LibraryType:
    """ Factory function to get correct library instance """
    if isinstance(identifier, (DependencySimple, DependencyFmfId)):
        from .beakerlib import BeakerLib
        library: LibraryType = BeakerLib(identifier=identifier, parent=parent, logger=logger)

    # File import
    elif isinstance(identifier, DependencyFile):
        assert source_location is not None
        assert target_location is not None  # narrow type
        from .file import File
        library = File(
            identifier=identifier, parent=parent, logger=logger,
            source_location=source_location, target_location=target_location)

    # Something weird
    else:
        raise LibraryError

    # Fetch the library
    try:
        library.fetch()
    except fmf.utils.RootError as exc:
        if hasattr(library, 'url'):
            raise tmt.utils.SpecificationError(
                f"Repository '{library.url}' does not contain fmf metadata.") from exc
        raise exc

    return library


def dependencies(
        *,
        original_require: List[Dependency],
        original_recommend: Optional[List[Dependency]] = None,
        parent: Optional[tmt.utils.Common] = None,
        imported_lib_ids: ImportedIdentifiersType = None,
        logger: tmt.log.Logger,
        source_location: Optional[Path] = None,
        target_location: Optional[Path] = None) -> LibraryDependenciesType:
    """
    Check dependencies for possible beakerlib libraries

    Fetch all identified libraries, check their required and recommended
    packages. Return tuple (requires, recommends, libraries) containing
    list of regular rpm package names aggregated from all fetched
    libraries, list of aggregated recommended packages and a list of
    gathered libraries (instances of the Library class).

    Avoid infinite recursion by keeping track of imported library identifiers
    and not trying to fetch those again.
    """
    # Initialize lists, use set for require & recommend
    processed_require = set()
    processed_recommend = set()
    imported_lib_ids = imported_lib_ids or []
    gathered_libraries: List[LibraryType] = []
    original_require = original_require or []
    original_recommend = original_recommend or []

    # Cut circular dependencies to avoid infinite recursion
    def already_fetched(lib: Dependency) -> bool:
        if not imported_lib_ids:
            return True
        return lib not in imported_lib_ids

    to_fetch = original_require + original_recommend
    for dependency in filter(already_fetched, to_fetch):
        # Library require/recommend
        try:
            library = library_factory(
                logger=logger, identifier=dependency, parent=parent,
                source_location=source_location, target_location=target_location)
            gathered_libraries.append(library)
            imported_lib_ids.append(library.identifier)

            from .beakerlib import BeakerLib
            if isinstance(library, BeakerLib):
                # Recursively check for possible dependent libraries
                assert parent is not None  # narrow type
                assert parent.workdir is not None  # narrow type
                requires, recommends, libraries = dependencies(
                    original_require=library.require,
                    original_recommend=library.recommend,
                    parent=parent,
                    imported_lib_ids=imported_lib_ids,
                    logger=logger,
                    source_location=library.source_directory,
                    target_location=Path(library.tree.root))
                processed_require.update(set(requires))
                processed_recommend.update(set(recommends))
                gathered_libraries.extend(libraries)
        # Regular package require/recommend
        except LibraryError:
            if dependency in original_require:
                processed_require.add(dependency)
            if dependency in original_recommend:
                processed_recommend.add(dependency)

    # Convert to list and return the results
    return list(processed_require), list(processed_recommend), gathered_libraries
