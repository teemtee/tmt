""" Handle libraries """

from typing import TYPE_CHECKING, Optional, Union

import fmf
import fmf.utils

import tmt
import tmt.base
import tmt.log
import tmt.utils
from tmt.base import Dependency, DependencyFile, DependencyFmfId, DependencySimple
from tmt.utils import Path

if TYPE_CHECKING:
    from tmt.libraries.beakerlib import BeakerLib
    from tmt.libraries.file import File

# A beakerlib identifier type, can be a string or a fmf id (with extra beakerlib keys)
ImportedIdentifiersType = Optional[list[Dependency]]

# A Library type, can be Beakerlib or File
LibraryType = Union['BeakerLib', 'File']

# A type for Beakerlib dependencies
LibraryDependenciesType = tuple[
    list[Dependency], list[Dependency], list['LibraryType']
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
    from .beakerlib import BeakerLib
    from .file import File

    if isinstance(identifier, (DependencySimple, DependencyFmfId)):
        library: LibraryType = BeakerLib(identifier=identifier, parent=parent, logger=logger)

    # File import
    #
    # ignore[reportUnnecessaryIsInstance]: pyright is correct, the test is not
    # needed given the fact `Dependency` is a union of three types, and two were
    # ruled out above. But we would like to check possible violations in runtime,
    # therefore an `else` with an exception.
    # ignore[unused-ignore]: silencing mypy's complaint about silencing
    # pyright's warning :)
    elif isinstance(
            identifier,
            DependencyFile):  # type: ignore[reportUnnecessaryIsInstance,unused-ignore]
        assert source_location is not None
        assert target_location is not None  # narrow type
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
        if isinstance(library, BeakerLib):
            raise tmt.utils.SpecificationError(
                f"Repository '{library.url}' does not contain fmf metadata.") from exc
        raise exc

    return library


def dependencies(
        *,
        original_require: list[Dependency],
        original_recommend: Optional[list[Dependency]] = None,
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
    processed_require: set[Dependency] = set()
    processed_recommend: set[Dependency] = set()
    imported_lib_ids = imported_lib_ids or []
    gathered_libraries: list[LibraryType] = []
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
                # TODO: make this one go away once fmf is properly annotated.
                # pyright detects the type might be `Unknown` because of how
                # fmf handles some corner cases, therefore `is not None` is
                # not strong enough.
                assert isinstance(library.tree.root, str)  # narrow type
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
