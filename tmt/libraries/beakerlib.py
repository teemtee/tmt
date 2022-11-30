import os
import re
import shutil
from tempfile import TemporaryDirectory
from typing import Dict, Optional, Set, Union, cast

import fmf

import tmt
import tmt.base
from tmt.base import DependencyFmfId, DependencySimple
from tmt.utils import Command, Path

from . import Library, LibraryError

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
    _library_cache: Dict[str, 'BeakerLib']
    _nonexistent_url: Set[str]


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
        elif isinstance(identifier, DependencyFmfId):
            self.identifier = identifier
            self.parent.debug(
                f"Detected library '{identifier.to_minimal_spec()}'.", level=3)
            self.format = 'fmf'
            self.url = identifier.url
            self.path = identifier.path or identifier.name
            # Strip possible trailing slash from path
            if isinstance(self.path, str):
                self.path = self.path.rstrip('/')
            if not self.url and not self.path:
                raise tmt.utils.SpecificationError(
                    "Need 'url' or 'path' to fetch a beakerlib library.")
            # Strip the '.git' suffix from url for known forges
            if self.url:
                for forge in STRIP_SUFFIX_FORGES:
                    if (self.url.startswith(forge)
                            and self.url.endswith('.git')):
                        self.url = self.url.rstrip('.git')
            self.ref = identifier.ref
            self.dest = identifier.destination or Path(DEFAULT_DESTINATION.lstrip('/'))
            self.name = identifier.name or '/'
            if not self.name.startswith('/'):
                raise tmt.utils.SpecificationError(
                    f"Library name '{self.name}' does not start with a '/'.")

            # Use provided repository nick name or parse it from the url/path
            repo = identifier.nick
            if repo:
                if not isinstance(repo, str):
                    raise tmt.utils.SpecificationError(
                        f"Invalid library nick '{repo}', should be a string.")
            else:
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

    @property
    def hostname(self) -> str:
        """ Get hostname from url or default to local """
        if self.url:
            matched = re.match(r'(?:git|http|https)://(.*?)/', self.url)
            if matched:
                return matched.group(1)
        return super().hostname

    @property
    def fmf_node_path(self) -> Path:
        """ Path to fmf node """
        if self.path:
            return Path(self.path / self.name.strip('/'))
        return super().fmf_node_path

    def __str__(self) -> str:
        """ Use repo/name for string representation """
        assert self.path is not None
        libname = self.path if self.url else self.name
        return f"{self.repo}{libname[libname.rindex('/'):]}"

    @property
    def _library_cache(self) -> Dict[str, 'BeakerLib']:
        # Initialize library cache (indexed by the repository and library name)
        # FIXME: cast() - https://github.com/teemtee/tmt/issues/1372
        if not hasattr(self.parent, '_library_cache'):
            cast(CommonWithLibraryCache, self.parent)._library_cache = {}

        return cast(CommonWithLibraryCache, self.parent)._library_cache

    @property
    def _nonexistent_url(self) -> Set[str]:
        # Set of url we tried to clone but didn't succeed
        if not hasattr(self.parent, '_nonexistent_url'):
            cast(CommonWithLibraryCache, self.parent)._nonexistent_url = set()

        return cast(CommonWithLibraryCache, self.parent)._nonexistent_url

    def fetch(self) -> None:
        """ Fetch the library (unless already fetched) """
        # Check if the library was already fetched
        try:
            library = self._library_cache[str(self)]
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
                            tmt.utils.git_clone(self.url, Path(tmp), self.parent,
                                                env={"GIT_ASKPASS": "echo"}, shallow=True)
                        except tmt.utils.RunError:
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
        except KeyError:
            self.parent.debug(f"Fetch library '{self}'.", level=3)
            # Prepare path, clone the repository, checkout ref
            assert self.parent.workdir
            directory = self.parent.workdir / self.dest / self.repo
            clone_dir = os.path.join(directory, 'clone')
            # Clone repo with disabled prompt to ignore missing/private repos
            try:
                if self.url:
                    if self.url in self._nonexistent_url:
                        raise tmt.utils.GitUrlError(
                            f"Already know that '{self.url}' does not exist.")
                    # Shallow clone to speed up testing and
                    # minimize data transfers if ref is not provided
                    tmt.utils.git_clone(self.url, clone_dir, self.parent,
                                        env={"GIT_ASKPASS": "echo"}, shallow=self.ref is None)

                    # Detect the default branch from the origin
                    try:
                        self.default_branch = tmt.utils.default_branch(clone_dir)
                    except OSError:
                        raise tmt.utils.GeneralError(
                            f"Unable to detect default branch for '{clone_dir}'. "
                            f"Is the git repository '{self.url}' empty?")
                    # Use the default branch if no ref provided
                    if self.ref is None:
                        self.ref = self.default_branch
                        # Check out the requested branch
                        try:
                            if self.ref is not None:
                                self.parent.run(Command('git', 'checkout', self.ref),
                                                cwd=clone_dir)
                        except tmt.utils.RunError:
                            # Fallback to install during the prepare step if in rpm format
                            if self.format == 'rpm':
                                self.parent.debug(f"Invalid reference '{self.ref}'.")
                                raise LibraryError
                            self.parent.fail(
                                f"Reference '{self.ref}' for library '{self}' not found.")
                            raise

                    # Copy only the required library
                    assert self.path is not None
                    library_path: str = os.path.join(clone_dir, self.path.strip('/'))
                    local_library_path: str = os.path.join(directory, os.path.basename(self.path))
                    if not os.path.exists(library_path):
                        self.parent.debug(f"Failed to find library {self} at {self.url}")
                        shutil.rmtree(clone_dir, ignore_errors=True)
                        raise LibraryError

                    tmt.utils.copytree(library_path, local_library_path, dirs_exist_ok=True)
                    # Copy fmf metadata
                    tmt.utils.copytree(
                        os.path.join(clone_dir, '.fmf'), os.path.join(directory, '.fmf'),
                        dirs_exist_ok=True)
                    shutil.rmtree(clone_dir, ignore_errors=True)
                else:
                    # Either url or path must be defined
                    assert self.path is not None
                    assert self.name is not None
                    library_path = os.path.join(self.path, self.name.strip('/'))
                    local_library_path = os.path.join(directory, self.name.strip('/'))
                    if not os.path.exists(library_path):
                        self.parent.debug(f"Failed to find library {self} at {self.path}")
                        raise LibraryError

                    self.parent.debug(
                        f"Copy local library '{self.path}' to '{directory}'.", level=3)
                    # Copy only the required library
                    tmt.utils.copytree(
                        library_path, local_library_path, symlinks=True, dirs_exist_ok=True)
                    # Copy fmf metadata
                    tmt.utils.copytree(
                        self.path / '.fmf', directory / '.fmf', dirs_exist_ok=True)
                # Detect the default branch from the origin
                try:
                    self.default_branch = tmt.utils.default_branch(
                        repository=directory, logger=self._logger)
                except OSError:
                    raise tmt.utils.GeneralError(
                        f"Unable to detect default branch for '{directory}'. "
                        f"Is the git repository '{self.url}' empty?")
                # Use the default branch if no ref provided
                if self.ref is None:
                    self.ref = self.default_branch
            except (tmt.utils.RunError, tmt.utils.GitUrlError) as error:
                assert self.url is not None  # narrow type
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
            self.tree = fmf.Tree(str(directory))
            self._library_cache[str(self)] = self

        # Get the library node, check require and recommend
        library_node = self.tree.find(self.name)
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
            f'{self.name}:require', library_node.get('require', []), self.parent._logger)
        self.recommend = tmt.base.normalize_require(
            f'{self.name}:recommend', library_node.get('recommend', []), self.parent._logger)

        # Create a symlink if the library is deep in the structure
        # FIXME: hot fix for https://github.com/beakerlib/beakerlib/pull/72
        # Covers also cases when library is stored more than 2 levels deep
        if os.path.dirname(self.name).lstrip('/'):
            link = Path(self.name.lstrip('/'))
            path = Path(self.tree.root) / Path(self.name).name
            self.parent.debug(
                f"Create a '{link}' symlink as the library is stored "
                f"deep in the directory structure.")
            try:
                path.symlink_to(link)
            except OSError as error:
                self.parent.warn(
                    f"Unable to create a '{link}' symlink "
                    f"for a deep library ({error}).")
