import re
import shutil
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, Optional, Union, cast

import fmf

import tmt
import tmt.base
import tmt.log
import tmt.utils
from tmt.base import DependencyFmfId, DependencySimple
from tmt.convert import write
from tmt.steps.discover import Discover
from tmt.utils import Command, Path

from . import Library, LibraryError

if TYPE_CHECKING:
    from tmt.base import _RawDependency

# Regular expressions for beakerlib libraries
LIBRARY_REGEXP = re.compile(r'^library\(([^/]+)(/[^)]+)\)$')

# Default beakerlib libraries location and destination directory
DEFAULT_REPOSITORY_TEMPLATE = 'https://github.com/beakerlib/{repository}'
DEFAULT_DESTINATION = 'libs'

# List of git forges for which the .git suffix should be stripped
STRIP_SUFFIX_FORGES = [
    'https://github.com',
    'https://gitlab.com',
    'https://pagure.io',
    ]


class CommonWithLibraryCache(tmt.utils.Common):
    _library_cache: dict[str, 'BeakerLib']
    _nonexistent_url: set[str]


class BeakerLib(Library):
    """
    A beakerlib library

    Takes care of fetching beakerlib libraries from remote repositories
    based on provided library identifier described in detail here:
    https://tmt.readthedocs.io/en/latest/spec/tests.html#require

    Optional 'parent' object inheriting from tmt.utils.Common can be
    provided in order to share the cache of already fetched libraries.

    The following attributes are available in the object:

    repo ........ library prefix (git repository name or nick if provided)
    name ........ library suffix (folder containing the library code)

    url ......... full git repository url
    ref ......... git revision (branch, tag or commit)
    dest ........ target folder into which the library repo is cloned

    tree ........ fmf tree holding library metadata
    require ..... list of required packages
    recommend ... list of recommended packages

    Libraries are fetched into the 'libs' directory under parent's
    workdir or into 'destination' if provided in the identifier.
    """

    def __init__(
            self,
            *,
            identifier: Union[DependencySimple, DependencyFmfId],
            parent: Optional[tmt.utils.Common] = None,
            logger: tmt.log.Logger) -> None:

        super().__init__(parent=parent, logger=logger)

        # Default branch is detected from the origin after cloning
        self.default_branch: Optional[str] = None

        # The 'library(repo/lib)' format
        if isinstance(identifier, DependencySimple):
            identifier = DependencySimple(identifier.strip())
            self.identifier = identifier
            matched = LIBRARY_REGEXP.search(identifier)
            if not matched:
                raise LibraryError
            self.parent.debug(
                f"Detected library '{identifier.to_minimal_spec()}'.", level=3)
            self.format = 'rpm'
            self.repo = Path(matched.groups()[0])
            self.name = matched.groups()[1]
            self.url: Optional[str] = DEFAULT_REPOSITORY_TEMPLATE.format(repository=self.repo)
            self.path: Optional[Path] = None
            self.ref: Optional[str] = None
            self.dest: Path = Path(DEFAULT_DESTINATION)

        # The fmf identifier
        #
        # ignore[reportUnnecessaryIsInstance]: pyright is correct, the test is not
        # needed given the fact `identifier` is a union of two types, and one was
        # ruled out above. But we would like to check possible violations in runtime,
        # therefore an `else` with an exception.
        # ignore[unused-ignore]: silencing mypy's complaint about silencing
        # pyright's warning :)
        elif isinstance(
                identifier,
                DependencyFmfId):  # type: ignore[reportUnnecessaryIsInstance,unused-ignore]
            self.identifier = identifier
            self.parent.debug(
                f"Detected library '{identifier.to_minimal_spec()}'.", level=3)
            self.format = 'fmf'
            self.url = identifier.url
            self.path = identifier.path
            if not self.url and not self.path:
                raise tmt.utils.SpecificationError(
                    "Need 'url' or 'path' to fetch a beakerlib library.")
            # Strip the '.git' suffix from url for known forges
            if self.url:
                for forge in STRIP_SUFFIX_FORGES:
                    if self.url.startswith(forge) and self.url.endswith('.git'):
                        self.url = self.url.rstrip('.git')
            self.ref = identifier.ref
            self.dest = identifier.destination or Path(DEFAULT_DESTINATION.lstrip('/'))
            self.name = identifier.name or '/'
            if not self.name.startswith('/'):
                raise tmt.utils.SpecificationError(
                    f"Library name '{self.name}' does not start with a '/'.")

            # Use provided repository nick name or parse it from the url/path
            repo = identifier.nick
            if not repo:
                if self.url:
                    repo_search = re.search(r'/([^/]+?)(/|\.git)?$', self.url)
                    if not repo_search:
                        raise tmt.utils.GeneralError(
                            f"Unable to parse repository name from '{self.url}'.")
                    repo = repo_search.group(1)
                else:
                    # Either url or path must be defined
                    assert self.path is not None
                    try:
                        repo = self.path.name
                        if not repo:
                            raise TypeError
                    except TypeError:
                        raise tmt.utils.GeneralError(
                            f"Unable to parse repository name from '{self.path}'.")
            self.repo = Path(repo)

        # Something weird
        else:
            raise LibraryError

        # Set default source directory, used for files required by a library
        self.source_directory: Path = self.path or self.fmf_node_path

    @property
    def hostname(self) -> str:
        """ Get hostname from url or default to local """
        if self.url:
            matched = re.match(r'(?:git|http|https|ssh)(?:@|://)(.*?)[/:]', self.url)
            if matched:
                return matched.group(1)
        return super().hostname

    @property
    def fmf_node_path(self) -> Path:
        """ Path to fmf node """
        if self.path:
            return self.path / self.name.strip('/')
        return super().fmf_node_path

    def __str__(self) -> str:
        """ Use repo/name for string representation """
        return f"{self.repo}{self.name[self.name.rindex('/'):]}"

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
        """ Merge all inherited metadata into one metadata file """
        for f in local_library_path.glob(r'*\.fmf'):
            f.unlink()
        write(
            path=local_library_path / 'main.fmf',
            data=tmt.utils.get_full_metadata(library_path, self.name),
            quiet=True)

    def fetch(self) -> None:
        """ Fetch the library (unless already fetched) """
        # Check if the library was already fetched
        try:
            library = self._library_cache[str(self)]
            # Check in case "tmt try retest" deleted the libs
            assert self.parent.workdir
            if not (self.parent.workdir / self.dest / self.repo).exists():
                raise FileNotFoundError
            # The url must be identical
            if library.url != self.url:
                # tmt guessed url so try if repo exists
                if self.format == 'rpm':
                    if self.url in self._nonexistent_url:
                        self.parent.debug(f"Already know that '{self.url}' does not exist.")
                        raise LibraryError
                    with TemporaryDirectory() as tmp:
                        assert self.url is not None  # narrow type
                        try:
                            tmt.utils.git_clone(
                                url=self.url,
                                destination=Path(tmp),
                                shallow=True,
                                env={"GIT_ASKPASS": "echo"},
                                logger=self._logger)
                        except (tmt.utils.RunError, tmt.utils.RetryError):
                            self.parent.debug(f"Repository '{self.url}' not found.")
                            self._nonexistent_url.add(self.url)
                            raise LibraryError
                # If repo does exist we really have unsolvable url conflict
                raise tmt.utils.GeneralError(
                    f"Library '{self}' with url '{self.url}' conflicts "
                    f"with already fetched library from '{library.url}'.")
            # Use the default branch if no ref provided
            if self.ref is None:
                self.ref = library.default_branch
            # The same ref has to be used
            if library.ref != self.ref:
                raise tmt.utils.GeneralError(
                    f"Library '{self}' using ref '{self.ref}' conflicts "
                    f"with already fetched library '{library}' "
                    f"using ref '{library.ref}'.")
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
                if self.url:
                    if self.url in self._nonexistent_url:
                        raise tmt.utils.GitUrlError(
                            f"Already know that '{self.url}' does not exist.")
                    clone_dir = self.parent.clone_dirpath / self.hostname / self.repo
                    self.source_directory = clone_dir
                    # Shallow clone to speed up testing and
                    # minimize data transfers if ref is not provided
                    if not clone_dir.exists():
                        tmt.utils.git_clone(
                            url=self.url,
                            destination=clone_dir,
                            shallow=self.ref is None,
                            env={"GIT_ASKPASS": "echo"},
                            logger=self._logger)

                    # Detect the default branch from the origin
                    try:
                        self.default_branch = tmt.utils.default_branch(
                            repository=clone_dir, logger=self._logger)
                    except OSError:
                        raise tmt.utils.GeneralError(
                            f"Unable to detect default branch for '{clone_dir}'. "
                            f"Is the git repository '{self.url}' empty?")
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
                            workdir=clone_dir,
                            ref=self.ref,
                            plan=plan,
                            logger=self._logger)
                    except tmt.utils.FileError as error:
                        raise tmt.utils.DiscoverError(
                            f"Failed to resolve dynamic ref of '{self.ref}'.") from error
                    # Check out the requested branch
                    try:
                        if dynamic_ref is not None:
                            # We won't change self.ref directly since we want to preserve a check
                            # for not fetching two distinct 'ref's. Simply put, only the same
                            # @dynamic_ref filepath can be used by other tests.
                            self.parent.run(
                                Command('git', 'checkout', dynamic_ref), cwd=clone_dir)
                    except tmt.utils.RunError:
                        # Fallback to install during the prepare step if in rpm format
                        if self.format == 'rpm':
                            self.parent.debug(f"Invalid reference '{self.ref}'.")
                            raise LibraryError
                        self.parent.fail(
                            f"Reference '{self.ref}' for library '{self}' not found.")
                        raise

                    # Copy only the required library
                    library_path: Path = clone_dir / str(self.fmf_node_path).strip('/')
                    local_library_path: Path = directory / str(self.fmf_node_path).strip('/')
                    if not library_path.exists():
                        self.parent.debug(f"Failed to find library {self} at {self.url}")
                        raise LibraryError
                    self.parent.debug(f"Library {self} is copied into {directory}")
                    shutil.copytree(library_path, local_library_path, dirs_exist_ok=True)

                    # Remove metadata file(s) and create one with full data
                    self._merge_metadata(library_path, local_library_path)

                    # Copy fmf metadata
                    shutil.copytree(clone_dir / '.fmf', directory / '.fmf', dirs_exist_ok=True)
                    if self.path:
                        shutil.copytree(
                            clone_dir / self.path.unrooted() / '.fmf',
                            directory / self.path.unrooted() / '.fmf',
                            dirs_exist_ok=True)
                else:
                    # Either url or path must be defined
                    assert self.path is not None
                    library_path = self.fmf_node_path
                    local_library_path = directory / self.name.strip('/')
                    if not library_path.exists():
                        self.parent.debug(f"Failed to find library {self} at {self.path}")
                        raise LibraryError

                    self.parent.debug(
                        f"Copy local library '{self.fmf_node_path}' to '{directory}'.", level=3)
                    # Copy only the required library
                    shutil.copytree(
                        library_path, local_library_path, symlinks=True, dirs_exist_ok=True)
                    # Remove metadata file(s) and create one with full data
                    self._merge_metadata(library_path, local_library_path)
                    # Copy fmf metadata
                    shutil.copytree(self.path / '.fmf', directory / '.fmf', dirs_exist_ok=True)
            except (tmt.utils.RunError, tmt.utils.RetryError, tmt.utils.GitUrlError) as error:
                assert self.url is not None
                # Fallback to install during the prepare step if in rpm format
                if self.format == 'rpm':
                    # Print this message only for the first attempt
                    if not isinstance(error, tmt.utils.GitUrlError):
                        self.parent.debug(f"Repository '{self.url}' not found.")
                        self._nonexistent_url.add(self.url)
                    raise LibraryError
                # Mark self.url as known to be missing
                self._nonexistent_url.add(self.url)
                self.parent.fail(
                    f"Failed to fetch library '{self}' from '{self.url}'.")
                raise
            # Initialize metadata tree, add self into the library index
            tree_path = str(directory / self.path.unrooted()) if (
                self.url and self.path) else str(directory)
            self.tree = fmf.Tree(tree_path)
            self._library_cache[str(self)] = self

        # Get the library node, check require and recommend
        library_node = cast(Optional[fmf.Tree], self.tree.find(self.name))
        if not library_node:
            # Fallback to install during the prepare step if in rpm format
            if self.format == 'rpm':
                self.parent.debug(
                    f"Library '{self.name.lstrip('/')}' not found "
                    f"in the '{self.url}' repo.")
                raise LibraryError
            raise tmt.utils.GeneralError(
                f"Library '{self.name}' not found in '{self.repo}'.")
        self.require = tmt.base.normalize_require(
            f'{self.name}:require',
            cast(Optional['_RawDependency'], library_node.get('require', [])),
            self.parent._logger)
        self.recommend = tmt.base.normalize_require(
            f'{self.name}:recommend',
            cast(Optional['_RawDependency'], library_node.get('recommend', [])),
            self.parent._logger)
