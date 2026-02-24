import abc
import re
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, Literal, Optional, cast

import fmf

import tmt.base
import tmt.log
import tmt.utils
import tmt.utils.filesystem
import tmt.utils.git
from tmt.base import Dependency, DependencyFmfId, DependencySimple
from tmt.container import container, simple_field
from tmt.convert import write
from tmt.steps.discover import Discover
from tmt.utils import Command, Environment, EnvVarValue, Path

from . import Library, LibraryError

if TYPE_CHECKING:
    from tmt.base import _RawDependency

# Regular expressions for beakerlib libraries
LIBRARY_REGEXP = re.compile(r'^library\(([^/]+)(/[^)]+)\)$')

# Default beakerlib libraries location and destination directory
DEFAULT_REPOSITORY_TEMPLATE = 'https://github.com/beakerlib/{repository}'
DEFAULT_DESTINATION = 'libs'

# TODO: This can probably be dropped? Why do we strip the .git only for some?
# List of git forges for which the .git suffix should be stripped
STRIP_SUFFIX_FORGES = [
    'https://github.com',
    'https://gitlab.com',
    'https://pagure.io',
]


class CommonWithLibraryCache(tmt.utils.Common):
    _library_cache: dict[str, 'BeakerLib']
    _nonexistent_url: set[str]


@container
class BeakerLib(Library):
    """
    A beakerlib library

    Takes care of fetching beakerlib libraries from remote repositories
    based on provided library identifier described in detail here:
    https://tmt.readthedocs.io/en/latest/spec/tests.html#require

    Libraries are fetched into the 'libs' directory under parent's
    workdir or into 'destination' if provided in the identifier.
    """

    identifier: DependencyFmfId  # pyright: ignore[reportIncompatibleVariableOverride]

    #: Target folder into which the library repo is cloned
    dest: Path
    path: Optional[Path]

    #: List of required packages
    require: list[Dependency] = simple_field(default_factory=list)  # pyright: ignore[reportUnknownVariableType]
    #: List of recommended packages
    recommend: list[Dependency] = simple_field(default_factory=list)  # pyright: ignore[reportUnknownVariableType]
    #: Fmf tree holding library metadata
    tree: fmf.Tree = simple_field(init=False)

    #: Source directory where used for files required by the library dependencies
    source_directory: Path = simple_field(init=False)
    default_branch: Optional[str] = None

    def __post_init__(self) -> None:
        # Set default source directory
        self.source_directory: Path = self.path or self.fmf_node_path
        # Sanity checks
        if not self.name.startswith('/'):
            raise tmt.utils.SpecificationError(
                f"Library name '{self.name}' does not start with a '/'."
            )

    @classmethod
    def from_identifier(
        cls,
        *,
        identifier: Dependency,
        parent: Optional[tmt.utils.Common] = None,
        logger: tmt.log.Logger,
        source_location: Optional[Path] = None,
        target_location: Optional[Path] = None,
    ) -> Library:
        assert parent is not None  # narrow type

        if isinstance(identifier, DependencySimple):
            return cls._from_simple(identifier=identifier, parent=parent, logger=logger)

        assert isinstance(identifier, DependencyFmfId)  # narrow type
        if identifier.url:
            return BeakerLibFromUrl.from_identifier(
                identifier=identifier, parent=parent, logger=logger
            )

        if identifier.path:
            return BeakerLibFromPath.from_identifier(
                identifier=identifier, parent=parent, logger=logger
            )

        return cls._from_discover_plugin(identifier=identifier, parent=parent, logger=logger)

    @classmethod
    def _from_simple(
        cls,
        *,
        identifier: DependencySimple,
        parent: tmt.utils.Common,
        logger: tmt.log.Logger,
    ) -> Library:
        """
        Constructor for BeakerLib library defined as ``library(repo/lib)``.
        """
        identifier = DependencySimple(identifier.strip())
        matched = LIBRARY_REGEXP.search(identifier)
        if not matched:
            raise LibraryError
        repo = matched.groups()[0]
        name = matched.groups()[1]
        library = BeakerLibFromUrl.from_identifier(
            identifier=DependencyFmfId(
                url=DEFAULT_REPOSITORY_TEMPLATE.format(repository=str(repo)),
                name=name,
            ),
            parent=parent,
            logger=logger,
        )
        # TODO: Drop support for rpm format handling?
        library.format = "rpm"
        return library

    @classmethod
    def _from_discover_plugin(
        cls,
        *,
        identifier: DependencyFmfId,
        parent: tmt.utils.Common,
        logger: tmt.log.Logger,
    ) -> Library:
        """
        Constructor for Beakerlib library from the current DiscoverPlugin.
        """
        from tmt.steps.discover import (
            DiscoverPlugin,
            DiscoverStepData,
        )
        from tmt.steps.discover.fmf import DiscoverFmfStepData

        assert not identifier.url
        assert not identifier.path

        if not identifier.nick:
            raise tmt.utils.SpecificationError(
                "Need either 'url' to fetch a remote beakerlib library, "
                "or 'path' to use a local filesystem library, "
                "or 'nick' to use the discovered tmt tree as the library."
            )

        assert isinstance(parent, DiscoverPlugin)  # narrow type
        assert isinstance(parent.data, DiscoverStepData)  # narrow type

        fmf_path = "."
        # When using `path` with `url`, it behaves differently from local `path`
        # TODO: Remove this special handling when DiscoverFmf is more consistent
        if isinstance(parent.data, DiscoverFmfStepData) and parent.data.url and parent.data.path:
            fmf_path = parent.data.path
        path = parent.test_dir / fmf_path
        identifier.path = path
        parent.debug(f"Resolving library '{identifier.nick}' to discovered tests: {path}")

        return BeakerLibFromPath.from_identifier(
            identifier=identifier,
            parent=parent,  # pyright: ignore[reportUnknownArgumentType]
            logger=logger,
        )

    @property
    def fmf_node_path(self) -> Path:
        """
        Path to fmf node
        """

        if self.path:
            return self.path / self.name.strip('/')
        return super().fmf_node_path

    def __str__(self) -> str:
        """
        Use repo/name for string representation
        """

        return f"{self.repo}{self.name[self.name.rindex('/') :]}"

    @property
    def _library_cache(self) -> dict[str, 'BeakerLib']:
        # Initialize library cache (indexed by the repository and library name)
        # FIXME: cast() - https://github.com/teemtee/tmt/issues/1372
        if not hasattr(self.parent, '_library_cache'):
            cast(CommonWithLibraryCache, self.parent)._library_cache = {}

        return cast(CommonWithLibraryCache, self.parent)._library_cache

    @property
    def _nonexistent_url(self) -> set[str]:
        # Set of url we tried to clone but didn't succeed
        if not hasattr(self.parent, '_nonexistent_url'):
            cast(CommonWithLibraryCache, self.parent)._nonexistent_url = set()

        return cast(CommonWithLibraryCache, self.parent)._nonexistent_url

    def _merge_metadata(self, library_path: Path, local_library_path: Path) -> None:
        """
        Merge all inherited metadata into one metadata file
        """

        for f in local_library_path.glob(r'*\.fmf'):
            f.unlink()
        write(
            path=local_library_path / 'main.fmf',
            data=tmt.utils.get_full_metadata(library_path, self.name),
            quiet=True,
        )

    @abc.abstractmethod
    def _do_fetch(self, directory: Path) -> None:
        """
        The actual beakerlib fetch logic.
        """
        # TODO: This can be dropped when addressing #4440

    def fetch(self) -> None:
        # Check if the library was already fetched
        try:
            library = self._library_cache[str(self)]
            # Check in case "tmt try retest" deleted the libs
            assert self.parent.workdir
            if not (self.parent.workdir / self.dest / self.repo).exists():
                raise FileNotFoundError
            if isinstance(self, BeakerLibFromUrl):
                assert isinstance(library, BeakerLibFromUrl)
                # The url must be identical
                if library.url != self.url:
                    # tmt guessed url so try if repo exists
                    if self.format == 'rpm':
                        if self.url in self._nonexistent_url:
                            self.parent.debug(f"Already know that '{self.url}' does not exist.")
                            raise LibraryError
                        with TemporaryDirectory() as tmp:
                            assert self.url is not None  # narrow type
                            destination = Path(tmp)
                            try:
                                tmt.utils.git.git_clone(
                                    url=self.url,
                                    destination=destination,
                                    shallow=True,
                                    env=Environment({"GIT_ASKPASS": EnvVarValue("echo")}),
                                    logger=self._logger,
                                )
                                self.parent.debug(
                                    'hash',
                                    tmt.utils.git.git_hash(
                                        directory=destination, logger=self._logger
                                    ),
                                )
                            except (tmt.utils.RunError, tmt.utils.RetryError) as error:
                                self.parent.debug(f"Repository '{self.url}' not found.")
                                self._nonexistent_url.add(self.url)
                                raise LibraryError from error
                    # If repo does exist we really have unsolvable url conflict
                    raise tmt.utils.GeneralError(
                        f"Library '{self}' with url '{self.url}' conflicts "
                        f"with already fetched library from '{library.url}'."
                    )
                # Use the default branch if no ref provided
                if self.ref is None:
                    self.ref = library.default_branch
                # The same ref has to be used
                if library.ref != self.ref:
                    raise tmt.utils.GeneralError(
                        f"Library '{self}' using ref '{self.ref}' conflicts "
                        f"with already fetched library '{library}' "
                        f"using ref '{library.ref}'."
                    )
            self.parent.debug(f"Library '{self}' already fetched.", level=3)
            # Reuse the existing metadata tree
            self.tree: fmf.Tree = library.tree
        # Fetch the library and add it to the index
        except (KeyError, FileNotFoundError):
            self.parent.debug(f"Fetch library '{self}'.", level=3)
            # Prepare path, clone the repository, checkout ref
            assert self.parent.workdir
            directory = self.parent.workdir / self.dest / self.repo
            # Clone repo with disabled prompt to ignore missing/private repos
            try:
                self._do_fetch(directory)
            except (tmt.utils.RunError, tmt.utils.RetryError, tmt.utils.GitUrlError) as error:
                assert isinstance(self, BeakerLibFromUrl)
                # Fallback to install during the prepare step if in rpm format
                if self.format == 'rpm':
                    # Print this message only for the first attempt
                    if not isinstance(error, tmt.utils.GitUrlError):
                        self.parent.debug(f"Repository '{self.url}' not found.")
                        self._nonexistent_url.add(self.url)
                    raise LibraryError from error
                # Mark self.url as known to be missing
                self._nonexistent_url.add(self.url)
                self.parent.fail(f"Failed to fetch library '{self}' from '{self.url}'.")
                raise
            # Initialize metadata tree, add self into the library index
            tree_path = (
                str(directory / self.path.unrooted())
                if (isinstance(self, BeakerLibFromUrl) and self.path)
                else str(directory)
            )
            self.tree = fmf.Tree(tree_path)
            self._library_cache[str(self)] = self

        # Get the library node, check require and recommend
        library_node = cast(Optional[fmf.Tree], self.tree.find(self.name))
        if not library_node:
            # Fallback to install during the prepare step if in rpm format
            if self.format == 'rpm':
                self.parent.debug(
                    f"Library '{self.name.lstrip('/')}' not found in the '{self.identifier}' repo."
                )
                raise LibraryError
            raise tmt.utils.GeneralError(f"Library '{self.name}' not found in '{self.repo}'.")
        self.require = tmt.base.normalize_require(
            f'{self.name}:require',
            cast(Optional['_RawDependency'], library_node.get('require', [])),
            self.parent._logger,
        )
        self.recommend = tmt.base.normalize_require(
            f'{self.name}:recommend',
            cast(Optional['_RawDependency'], library_node.get('recommend', [])),
            self.parent._logger,
        )


@container
class BeakerLibFromUrl(BeakerLib):
    """
    An external beakerlib library fetched from a git url.
    """

    format: Literal['rpm', 'fmf']  # pyright: ignore[reportIncompatibleVariableOverride]

    # TODO: url is actually a required field, but we cannot use kw_only yet.
    #: Full git repository url
    url: str = ""
    #: Git revision (branch, tag or commit)
    ref: Optional[str] = None
    #: Path under the git repository pointing to the fmf root
    path: Optional[Path] = None

    @property
    def hostname(self) -> str:
        """
        Get hostname from url or default to local
        """

        if self.url:
            matched = re.match(r'(?:git|http|https|ssh)(?:@|://)(.*?)[/:]', self.url)
            if matched:
                return matched.group(1)
        return super().hostname

    @classmethod
    def from_identifier(
        cls,
        *,
        identifier: Dependency,
        parent: Optional[tmt.utils.Common] = None,
        logger: tmt.log.Logger,
        source_location: Optional[Path] = None,
        target_location: Optional[Path] = None,
    ) -> Library:
        assert parent is not None  # narrow type
        assert isinstance(identifier, DependencyFmfId)  # narrow type
        assert identifier.url  # narrow type
        parent.debug(f"Detected library '{identifier.to_minimal_spec()}'.", level=3)

        # Strip the '.git' suffix from url for known forges
        url = identifier.url
        for forge in STRIP_SUFFIX_FORGES:
            if url.startswith(forge):
                url = url.removesuffix('.git')
        repo = identifier.nick
        if not repo:
            repo_search = re.search(r'/([^/]+?)(/|\.git)?$', url)
            if not repo_search:
                raise tmt.utils.GeneralError(f"Unable to parse repository name from '{url}'.")
            repo = repo_search.group(1)
        return BeakerLibFromUrl(
            parent=parent,
            _logger=logger,
            identifier=identifier,
            format="fmf",
            repo=Path(repo),
            name=identifier.name or '/',
            url=url,
            ref=identifier.ref,
            path=identifier.path,
            dest=identifier.destination or Path(DEFAULT_DESTINATION),
        )

    def _do_fetch(self, directory: Path) -> None:
        if self.url in self._nonexistent_url:
            raise tmt.utils.GitUrlError(f"Already know that '{self.url}' does not exist.")
        clone_dir = self.parent.clone_dirpath / self.hostname / self.repo
        self.source_directory = clone_dir
        # Shallow clone to speed up testing and
        # minimize data transfers if ref is not provided
        if not clone_dir.exists():
            tmt.utils.git.git_clone(
                url=self.url,
                destination=clone_dir,
                shallow=self.ref is None,
                env=Environment({"GIT_ASKPASS": EnvVarValue("echo")}),
                logger=self._logger,
            )

        # Detect the default branch from the origin
        try:
            self.default_branch = tmt.utils.git.default_branch(
                repository=clone_dir, logger=self._logger
            )
        except OSError as error:
            raise tmt.utils.GeneralError(
                f"Unable to detect default branch for '{clone_dir}'. "
                f"Is the git repository '{self.url}' empty?"
            ) from error
        # Use the default branch if no ref provided
        if self.ref is None:
            self.ref = self.default_branch
        # Apply the dynamic reference if provided
        try:
            if hasattr(self.parent.parent, 'plan'):
                plan = cast(Discover, self.parent.parent).plan
            else:
                plan = None
            dynamic_ref = tmt.base.resolve_dynamic_ref(
                workdir=clone_dir, ref=self.ref, plan=plan, logger=self._logger
            )
        except tmt.utils.FileError as error:
            raise tmt.utils.DiscoverError(
                f"Failed to resolve dynamic ref of '{self.ref}'."
            ) from error
        # Check out the requested branch
        try:
            if dynamic_ref is not None:
                # We won't change self.ref directly since we want to preserve a check
                # for not fetching two distinct 'ref's. Simply put, only the same
                # @dynamic_ref filepath can be used by other tests.
                self.parent.run(Command('git', 'checkout', dynamic_ref), cwd=clone_dir)
        except tmt.utils.RunError as error:
            # Fallback to install during the prepare step if in rpm format
            if self.format == 'rpm':
                self.parent.debug(f"Invalid reference '{self.ref}'.")
                raise LibraryError from error
            self.parent.fail(f"Reference '{self.ref}' for library '{self}' not found.")
            raise

        # Log what HEAD really is
        self.parent.verbose(
            'commit-hash',
            tmt.utils.git.git_hash(directory=clone_dir, logger=self._logger),
            'green',
        )

        # Copy only the required library
        library_path: Path = clone_dir / str(self.fmf_node_path).strip('/')
        local_library_path: Path = directory / str(self.fmf_node_path).strip('/')
        if not library_path.exists():
            self.parent.debug(f"Failed to find library {self} at {self.url}")
            raise LibraryError
        self.parent.debug(f"Library {self} is copied into {directory}")
        tmt.utils.filesystem.copy_tree(library_path, local_library_path, self._logger)

        self.parent.verbose(
            'using remote git library',
            cast(dict[str, str], self.identifier.to_minimal_dict()),
            'green',
            level=3,
        )

        # Remove metadata file(s) and create one with full data
        # Node with library might not exist, provide usable error message
        try:
            self._merge_metadata(library_path, local_library_path)
        except tmt.utils.MetadataError as error:
            fmf_id = ', '.join(
                [
                    s
                    for s in [
                        f'name: {self.name}' if self.name else None,
                        f'url: {self.url}' if self.url else None,
                        f'ref: {self.ref}' if self.ref else None,
                        f'path: {self.path}' if self.path else None,
                    ]
                    if s is not None
                ]
            )
            raise LibraryError(f"Library with {fmf_id=} doesn't exist.") from error

        # Copy fmf metadata
        tmt.utils.filesystem.copy_tree(
            clone_dir / '.fmf',
            directory / '.fmf',
            self._logger,
        )
        if self.path:
            tmt.utils.filesystem.copy_tree(
                clone_dir / self.path.unrooted() / '.fmf',
                directory / self.path.unrooted() / '.fmf',
                self._logger,
            )


@container
class BeakerLibFromPath(BeakerLib):
    """
    A beakerlib library on the local filesystem.
    """

    format: Literal['fmf']  # pyright: ignore[reportIncompatibleVariableOverride]

    #: Absolute path on the local filesystem pointing to the library
    path: Path  # pyright: ignore[reportIncompatibleVariableOverride]

    @classmethod
    def from_identifier(
        cls,
        *,
        identifier: Dependency,
        parent: Optional[tmt.utils.Common] = None,
        logger: tmt.log.Logger,
        source_location: Optional[Path] = None,
        target_location: Optional[Path] = None,
    ) -> "BeakerLib":
        assert parent is not None  # narrow type
        assert isinstance(identifier, DependencyFmfId)  # narrow type
        assert identifier.path  # narrow type
        path = identifier.path

        repo = identifier.nick
        if not repo:
            repo = path.name
            if not repo:
                raise tmt.utils.GeneralError(f"Unable to parse repository name from '{path}'.")

        return BeakerLibFromPath(
            parent=parent,
            _logger=logger,
            identifier=identifier,
            format="fmf",
            repo=Path(repo),
            name=identifier.name or '/',
            path=identifier.path,
            dest=identifier.destination or Path(DEFAULT_DESTINATION),
        )

    def _do_fetch(self, directory: Path) -> None:
        library_path = self.fmf_node_path
        local_library_path = directory / self.name.strip('/')
        if not library_path.exists():
            self.parent.debug(f"Failed to find library {self} at {self.path}")
            raise LibraryError

        self.parent.debug(f"Copy local library '{self.fmf_node_path}' to '{directory}'.", level=3)
        # Copy only the required library
        tmt.utils.filesystem.copy_tree(library_path, local_library_path, self._logger)
        # Remove metadata file(s) and create one with full data
        self._merge_metadata(library_path, local_library_path)
        # Copy fmf metadata
        tmt.utils.filesystem.copy_tree(
            self.path / '.fmf',
            directory / '.fmf',
            self._logger,
        )
