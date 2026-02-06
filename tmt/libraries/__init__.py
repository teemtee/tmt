"""
Handle libraries
"""

import abc
from typing import Optional

import fmf.utils

import tmt.log
import tmt.utils
from tmt.base.core import Dependency, DependencyFile, DependencyFmfId, DependencySimple
from tmt.container import container
from tmt.utils import Path

# A type for Beakerlib dependencies
LibraryDependenciesType = tuple[list[Dependency], list[Dependency]]


class LibraryError(Exception):
    """
    Used when library cannot be parsed from the identifier
    """


@container
class Library(abc.ABC):
    """
    General library class

    Used as parent for specific libraries like beakerlib and file
    """

    # TODO: parent is actually guaranteed to be `DiscoverPlugin`, try to
    #  narrow type it further.
    #: The phase that requested the library as a dependency
    parent: tmt.utils.Common
    _logger: tmt.log.Logger
    #: The original dependency requested
    identifier: Dependency
    # TODO: Should not be needed if Beakerlib rpm format is removed
    #: Format of the library type requested
    format: str
    #: Name of the repository where the library came from
    repo: Path
    #: Fully-qualified name of the library (excluding the ``repo`` part).
    #:
    #: For example the name used in the ``rlImport`` command.
    #: Must start with ``/``.
    name: str

    @classmethod
    def from_identifier(
        cls,
        *,
        identifier: Dependency,
        parent: Optional[tmt.utils.Common] = None,
        logger: tmt.log.Logger,
        source_location: Optional[Path] = None,
        target_location: Optional[Path] = None,
    ) -> "Library":
        """
        Factory function to get correct library instance
        """
        # TODO: Remove the need for `source_location` and `target_location`?

        from .beakerlib import BeakerLib
        from .file import File

        # Use an empty common class if parent not provided (for logging, cache)
        # TODO: This should not be needed because parent is always DiscoverPlugin,
        #  see callers of `dependencies`
        parent = parent or tmt.utils.Common(logger=logger, workdir=True)

        if isinstance(identifier, (DependencySimple, DependencyFmfId)):
            library = BeakerLib.from_identifier(
                identifier=identifier,
                parent=parent,
                logger=logger,
            )

        # File import
        #
        # ignore[reportUnnecessaryIsInstance]: pyright is correct, the test is not
        # needed given the fact `Dependency` is a union of three types, and two were
        # ruled out above. But we would like to check possible violations in runtime,
        # therefore an `else` with an exception.
        # ignore[unused-ignore]: silencing mypy's complaint about silencing
        # pyright's warning :)
        elif isinstance(identifier, DependencyFile):  # type: ignore[reportUnnecessaryIsInstance,unused-ignore]
            assert source_location is not None
            assert target_location is not None  # narrow type
            library = File.from_identifier(
                identifier=identifier,
                parent=parent,
                logger=logger,
                source_location=source_location,
                target_location=target_location,
            )

        # Something weird
        else:
            raise LibraryError

        # Fetch the library
        try:
            library.fetch()
        except fmf.utils.RootError as exc:
            if isinstance(library, BeakerLib):
                raise LibraryError(
                    f"Repository '{library.identifier}' does not contain fmf metadata."
                ) from exc
            raise exc

        return library

    @property
    def fmf_node_path(self) -> Path:
        """
        Path to fmf node
        """

        return Path(self.name.strip('/'))

    def __str__(self) -> str:
        """
        Use repo/name for string representation
        """

        return f"{self.repo}{self.name}"

    @abc.abstractmethod
    def fetch(self) -> None:
        """
        Fetch the library from the source in the identifier.
        """
        raise NotImplementedError


# TODO: Move this under the test or discover interface
def resolve_dependencies(
    *,
    original_require: list[Dependency],
    original_recommend: list[Dependency],
    parent: tmt.utils.Common,
    logger: tmt.log.Logger,
    source_location: Optional[Path] = None,
    target_location: Optional[Path] = None,
) -> LibraryDependenciesType:
    """
    Resolve the ``require`` and ``recommend`` dependencies.

    For each library type encountered do the fetching, recursively resolve the
    library's dependencies as well, and forward all of the package dependencies
    that need to be processed by the ``PrepareInstall`` plugin.

    The libraries are first processed from the ``require`` list and then from
    the ``recommend`` list. Within each dependency list, each library's
    dependencies are expanded first before moving to the next dependency on the
    list.

    When encountering duplicate beakerlib libraries, the first library that was
    resolved takes precedence (this logic is defined in the
    ``Beakerlib._do_fetch`` and the recursion order of this function). For
    example, starting from the test's dependencies, the libraries can be
    resolved as follows:

    .. code-block::

       /test:                          (1)
         ├── library(A/lib)            (2)
         ├── library(B/lib)            (3)
         │   ├── library(A/lib)        (skipped, reuse (2))
         │   └── library(C/lib)        (4)
         └── library(C/lib)            (skipped, reuse (4))

    """
    from .beakerlib import BeakerLib

    # TODO: These should actually be `set[DependencySimple]`
    require_to_install: set[Dependency] = set()
    recommend_to_install: set[Dependency] = set()
    for dependency in (*original_require, *original_recommend):
        try:
            library = Library.from_identifier(
                logger=logger,
                identifier=dependency,
                parent=parent,
                source_location=source_location,
                target_location=target_location,
            )
        except LibraryError:
            # Not a library, just a regular package to be installed
            # TODO: This check is not robust at all, try handling the cases
            #  explicitly outside of the try..except.
            if not isinstance(dependency, DependencySimple):
                logger.warning(f"Library '{dependency}' failed unexpectedly")
                continue
            if dependency in original_require:
                require_to_install.add(dependency)
            if dependency in original_recommend:
                recommend_to_install.add(dependency)
            continue

        if isinstance(library, BeakerLib):
            # Recursively expand the beakerlib library dependencies
            assert isinstance(library.tree.root, str)  # narrow type
            requires, recommends = resolve_dependencies(
                original_require=library.require,
                original_recommend=library.recommend,
                # TODO: we could do some better logging if we keep track of where the dependency
                #  came from (parent here could be library instead)
                parent=parent,
                logger=logger,
                # For any FileLibrary dependency, put them in the appropriate path?
                source_location=library.source_directory,
                target_location=Path(library.tree.root),
            )
            require_to_install.update(requires)
            recommend_to_install.update(recommends)

    return list(require_to_install), list(recommend_to_install)
