import contextlib
import dataclasses
import glob
import os
import re
import shutil
import subprocess
from typing import Any, Optional, cast

import fmf

import tmt
import tmt.base
import tmt.libraries
import tmt.log
import tmt.options
import tmt.steps
import tmt.steps.discover
import tmt.utils
import tmt.utils.git
from tmt.base import _RawAdjustRule
from tmt.steps.prepare.distgit import insert_to_prepare_step
from tmt.utils import Command, Environment, EnvVarValue, Path, field


def normalize_ref(
        key_address: str,
        value: Optional[Any],
        logger: tmt.log.Logger) -> Optional[str]:
    if value is None:
        return None

    if isinstance(value, str):
        return value

    raise tmt.utils.NormalizationError(key_address, value, 'unset or a string')


@dataclasses.dataclass
class DiscoverFmfStepData(tmt.steps.discover.DiscoverStepData):
    # Basic options
    url: Optional[str] = field(
        default=cast(Optional[str], None),
        option=('-u', '--url'),
        metavar='REPOSITORY',
        help='URL of the git repository with fmf metadata.')
    ref: Optional[str] = field(
        default=cast(Optional[str], None),
        option=('-r', '--ref'),
        metavar='REVISION',
        help='Branch, tag or commit specifying the git revision.',
        normalize=normalize_ref)
    path: Optional[str] = field(
        default=cast(Optional[str], None),
        option=('-p', '--path'),
        metavar='ROOT',
        help='Path to the metadata tree root.')

    # Selecting tests
    test: list[str] = field(
        default_factory=list,
        option=('-t', '--test'),
        metavar='NAMES',
        multiple=True,
        help='Select tests by name.',
        normalize=tmt.utils.normalize_string_list)
    link: list[str] = field(
        default_factory=list,
        option='--link',
        metavar="RELATION:TARGET",
        multiple=True,
        help="""
             Filter by linked objects (regular expressions are supported for both relation and
             target).
             """)
    filter: list[str] = field(
        default_factory=list,
        option=('-F', '--filter'),
        metavar='FILTERS',
        multiple=True,
        help='Include only tests matching the filter.',
        normalize=tmt.utils.normalize_string_list)
    exclude: list[str] = field(
        default_factory=list,
        option=('-x', '--exclude'),
        metavar='REGEXP',
        multiple=True,
        help="Exclude tests matching given regular expression.",
        normalize=tmt.utils.normalize_string_list)

    # Modified only
    modified_only: bool = field(
        default=False,
        option=('-m', '--modified-only'),
        is_flag=True,
        help='If set, select only tests modified since reference revision.')
    modified_url: Optional[str] = field(
        default=cast(Optional[str], None),
        option='--modified-url',
        metavar='REPOSITORY',
        help='URL of the reference git repository with fmf metadata.')
    modified_ref: Optional[str] = field(
        default=cast(Optional[str], None),
        option='--modified-ref',
        metavar='REVISION',
        help="""
            Branch, tag or commit specifying the reference git revision (if not provided, the
            default branch is used).
            """)

    # Dist git integration
    dist_git_init: bool = field(
        default=False,
        option='--dist-git-init',
        is_flag=True,
        help="""
             Initialize fmf root inside extracted sources (at dist-git-extract or top directory).
             """)
    dist_git_remove_fmf_root: bool = field(
        default=False,
        option='--dist-git-remove-fmf-root',
        is_flag=True,
        help="""
             Remove fmf root from extracted source (top one or selected by copy-path, happens
             before dist-git-extract.
             """)
    dist_git_merge: bool = field(
        default=False,
        option='--dist-git-merge',
        is_flag=True,
        help='Merge copied sources and plan fmf root.')
    dist_git_extract: Optional[str] = field(
        default=cast(Optional[str], None),
        option='--dist-git-extract',
        help="""
             What to copy from extracted sources, globbing is supported. Defaults to the top fmf
             root if it is present, otherwise top directory (shortcut "/").
             """)

    # Special options
    sync_repo: bool = field(
        default=False,
        option='--sync-repo',
        is_flag=True,
        help="""
             Force the sync of the whole git repo. By default, the repo is copied only if the used
             options require it.
             """)
    fmf_id: bool = field(
        default=False,
        option='--fmf-id',
        is_flag=True,
        help='Only print fmf identifiers of discovered tests to the standard output and exit.')
    prune: bool = field(
        default=False,
        option=('--prune / --no-prune'),
        is_flag=True,
        show_default=True,
        help="Copy only immediate directories of executed tests and their required files.")

    # Edit discovered tests
    adjust_tests: Optional[list[_RawAdjustRule]] = field(
        default_factory=list,
        normalize=tmt.utils.normalize_adjust,
        help="""
             Modify metadata of discovered tests from the plan itself. Use the
             same format as for adjust rules.
             """)

    # Upgrade plan path so the plan is not pruned
    upgrade_path: Optional[str] = None

    # Legacy fields
    repository: Optional[str] = None
    revision: Optional[str] = None

    def post_normalization(
            self,
            raw_data: tmt.steps._RawStepData,
            logger: tmt.log.Logger) -> None:
        super().post_normalization(raw_data, logger)

        if self.repository:
            self.url = self.repository

        if self.revision:
            self.ref = self.revision


@tmt.steps.provides_method('fmf')
class DiscoverFmf(tmt.steps.discover.DiscoverPlugin[DiscoverFmfStepData]):
    """
    Discover available tests from fmf metadata.

    By default all available tests from the current repository are used
    so the minimal configuration looks like this:

    .. code-block:: yaml

        discover:
            how: fmf

    Full config example:

    .. code-block:: yaml

        discover:
            how: fmf
            url: https://github.com/teemtee/tmt
            ref: main
            path: /fmf/root
            test: /tests/basic
            filter: 'tier: 1'

    If no ``ref`` is provided, the default branch from the origin is used.

    For DistGit repo one can download sources and use code from them in
    the tests. Sources are extracted into ``$TMT_SOURCE_DIR`` path,
    patches are applied by default. See options to install build
    dependencies or to just download sources without applying patches.
    To apply patches, special ``prepare`` phase with order ``60`` is
    added, and ``prepare`` step has to be enabled for it to run.

    It can be used together with ``ref``, ``path`` and ``url``,
    however ``ref`` is not possible without using ``url``.

    .. code-block:: yaml

        discover:
            how: fmf
            dist-git-source: true

    Related config options (all optional):

    * ``dist-git-merge`` - set to ``true`` if you want to copy in extracted
      sources to the local repo
    * ``dist-git-init`` - set to ``true`` and ``fmf init`` will be called inside
      extracted sources (at ``dist-git-extract`` or top directory)
    * ``dist-git-extract`` - directory (glob supported) to copy from
      extracted sources (defaults to inner fmf root)
    * ``dist-git-remove-fmf-root`` - set to ``true`` to remove fmf root from
      extracted sources

    Selecting tests containing specified link is possible using ``link``
    key accepting ``RELATION:TARGET`` format of values. Regular
    expressions are supported for both relation and target part of the
    value. Relation can be omitted to target match any relation.

    .. code-block:: yaml

        discover:
            how: fmf
            link: verifies:.*issue/850$

    It is also possible to limit tests only to those that have changed
    in git since a given revision. This can be particularly useful when
    testing changes to tests themselves (e.g. in a pull request CI).

    Related config options (all optional):

    * ``modified-only`` - set to ``true`` if you want to filter modified tests
    * ``modified-url`` - fetched as "reference" remote in the test dir
    * ``modified-ref`` - the ref to compare against

    Example to compare local repo against upstream ``main`` branch:

    .. code-block:: yaml

        discover:
            how: fmf
            modified-only: True
            modified-url: https://github.com/teemtee/tmt
            modified-ref: reference/main

    Note that internally the modified tests are appended to the list
    specified via ``test``, so those tests will also be selected even if
    not modified.

    Use the ``adjust-tests`` key to modify the discovered tests'
    metadata directly from the plan. For example, extend the test
    duration for slow hardware or modify the list of required packages
    when you do not have write access to the remote test repository.
    The value should follow the ``adjust`` rules syntax.

    The following example adds an ``avc`` check for each discovered
    test, doubles its duration and replaces each occurrence of the word
    ``python3.11`` in the list of required packages.

    .. code-block:: yaml

        discover:
            how: fmf
            adjust-tests:
              - check+:
                  - how: avc
              - duration+: '*2'
                because: Slow system under test
                when: arch == i286
              - require~:
                  - '/python3.11/python3.12/'
    """

    _data_class = DiscoverFmfStepData

    # Options which require .git to be present for their functionality
    _REQUIRES_GIT = (
        "ref",
        "modified-url",
        "modified-only",
        "fmf-id",
        )

    @property
    def is_in_standalone_mode(self) -> bool:
        """ Enable standalone mode when listing fmf ids """
        if self.opt('fmf_id'):
            return True
        return super().is_in_standalone_mode

    def get_git_root(self, directory: Path) -> Path:
        """ Find git root of the path """
        output = self.run(
            Command("git", "rev-parse", "--show-toplevel"),
            cwd=directory,
            ignore_dry=True)
        assert output.stdout is not None
        return Path(output.stdout.strip("\n"))

    def go(self, *, logger: Optional[tmt.log.Logger] = None) -> None:
        """ Discover available tests """
        super().go(logger=logger)

        # Check url and path, prepare test directory
        url = self.get('url')
        # FIXME: cast() - typeless "dispatcher" method
        path = Path(cast(str, self.get('path'))) if self.get('path') else None
        # Save the test directory so that others can reference it
        ref = self.get('ref')
        assert self.workdir is not None
        self.testdir = self.workdir / 'tests'
        sourcedir = self.workdir / 'source'
        dist_git_source = self.get('dist-git-source', False)
        dist_git_merge = self.get('dist-git-merge', False)

        # No tests are selected in some cases
        self._tests: list[tmt.Test] = []

        # Self checks
        if dist_git_source and not dist_git_merge and (ref or url):
            raise tmt.utils.DiscoverError(
                "Cannot manipulate with dist-git without "
                "the `--dist-git-merge` option.")

        # Raise an exception if --fmf-id uses w/o url and git root
        # doesn't exist for discovered plan
        if self.opt('fmf_id'):
            def assert_git_url(plan_name: Optional[str] = None) -> None:
                try:
                    subprocess.run(
                        'git rev-parse --show-toplevel'.split(),
                        stdout=subprocess.PIPE,
                        stderr=subprocess.DEVNULL,
                        check=True)
                except subprocess.CalledProcessError:
                    raise tmt.utils.DiscoverError(
                        f"`tmt run discover --fmf-id` without `url` option in "
                        f"plan `{plan_name}` can be used only within"
                        f" git repo.")
            # It covers only one case, when there is:
            # 1) no --url on CLI
            # 2) plan w/o url exists in test run
            if not self.opt('url'):
                try:
                    fmf_tree = fmf.Tree(os.getcwd())
                except fmf.utils.RootError:
                    raise tmt.utils.DiscoverError(
                        "No metadata found in the current directory. "
                        "Use 'tmt init' to get started.")
                for attr in fmf_tree.climb():
                    try:
                        plan_url = attr.data.get('discover').get('url')
                        plan_name = attr.name
                        if not plan_url:
                            assert_git_url(plan_name)
                    except AttributeError:
                        pass
            # All other cases are covered by this condition
            if not url:
                assert_git_url(self.step.plan.name)

        self.log_import_plan_details()

        # Clone provided git repository (if url given) with disabled
        # prompt to ignore possibly missing or private repositories
        if url:
            self.info('url', url, 'green')
            self.debug(f"Clone '{url}' to '{self.testdir}'.")
            # Shallow clone to speed up testing and
            # minimize data transfers if ref is not provided
            tmt.utils.git.git_clone(
                url=url,
                destination=self.testdir,
                shallow=ref is None,
                env=Environment({"GIT_ASKPASS": EnvVarValue("echo")}),
                logger=self._logger)
            git_root = self.testdir
        # Copy git repository root to workdir
        else:
            if path is not None:
                fmf_root: Optional[Path] = path
            else:
                fmf_root = Path(self.step.plan.node.root)
            requires_git = self.opt('sync-repo') or any(
                self.get(opt) for opt in self._REQUIRES_GIT)
            # Path for distgit sources cannot be checked until the
            # they are extracted
            if path and not path.is_dir() and not dist_git_source:
                raise tmt.utils.DiscoverError(
                    f"Provided path '{path}' is not a directory.")
            if dist_git_source:
                # Ensure we're in a git repo when extracting dist-git sources
                try:
                    git_root = self.get_git_root(Path(self.step.plan.node.root))
                except tmt.utils.RunError:
                    assert self.step.plan.my_run is not None  # narrow type
                    assert self.step.plan.my_run.tree is not None  # narrow type
                    raise tmt.utils.DiscoverError(
                        f"{self.step.plan.node.root} is not a git repo")
            else:
                if fmf_root is None:
                    raise tmt.utils.DiscoverError(
                        "No metadata found in the current directory.")
                # Check git repository root (use fmf root if not found)
                try:
                    git_root = self.get_git_root(fmf_root)
                except tmt.utils.RunError:
                    self.debug(f"Git root not found, using '{fmf_root}.'")
                    git_root = fmf_root
                # Set path to relative path from the git root to fmf root
                path = fmf_root.resolve().relative_to(
                    git_root.resolve() if requires_git else fmf_root.resolve())

            # And finally copy the git/fmf root directory to testdir
            # (for dist-git case only when merge explicitly requested)
            if requires_git:
                directory: Path = git_root
            else:
                assert fmf_root is not None  # narrow type
                directory = fmf_root
            self.info('directory', directory, 'green')
            if not dist_git_source or dist_git_merge:
                self.debug(f"Copy '{directory}' to '{self.testdir}'.")
                if not self.is_dry_run:
                    shutil.copytree(directory, self.testdir, symlinks=True)

        # Prepare path of the dynamic reference
        try:
            ref = tmt.base.resolve_dynamic_ref(
                logger=self._logger,
                workdir=self.testdir,
                ref=ref,
                plan=self.step.plan)
        except tmt.utils.FileError as error:
            raise tmt.utils.DiscoverError(str(error))

        # Checkout revision if requested
        if ref:
            self.info('ref', ref, 'green')
            self.debug(f"Checkout ref '{ref}'.")
            self.run(Command('git', 'checkout', '-f', ref), cwd=self.testdir)

        # Show current commit hash if inside a git repository
        if self.testdir.is_dir():
            with contextlib.suppress(tmt.utils.RunError, AttributeError):
                self.verbose(
                    'hash',
                    tmt.utils.git.git_hash(directory=self.testdir, logger=self._logger),
                    'green'
                    )

        # Dist-git source processing during discover step
        if dist_git_source:
            try:
                # 'ref' is checked out in self.testdir
                self.download_distgit_source(
                    distgit_dir=self.testdir if ref else git_root,
                    target_dir=sourcedir,
                    handler_name=self.get('dist-git-type'),
                    )
                # Copy rest of files so TMT_SOURCE_DIR has patches, sources and spec file
                # FIXME 'worktree' could be used as sourcedir when 'url' is not set
                shutil.copytree(
                    self.testdir if ref else git_root,
                    sourcedir,
                    symlinks=True,
                    dirs_exist_ok=True)
                # patch & rediscover will happen later in the prepare step
                if not self.get('dist-git-download-only'):
                    # Check if prepare is enabled, warn user if not
                    if not self.step.plan.prepare.enabled:
                        self.warn("Sources will not be extracted, prepare step is not enabled.")
                    insert_to_prepare_step(
                        discover_plugin=self,
                        sourcedir=sourcedir,
                        )
                # merge or not, detect later
                self.step.plan.discover.extract_tests_later = True
                self.info("Tests will be discovered after dist-git patching in prepare.")
                return
            except Exception as error:
                raise tmt.utils.DiscoverError(
                    "Failed to process 'dist-git-source'.") from error
        # Discover tests
        self.do_the_discovery(path)

    def do_the_discovery(self, path: Optional[Path] = None) -> None:
        """ Discover the tests """
        # Original path might adjusted already in go()
        if path is None:
            path = Path(cast(str, self.get('path'))) if self.get('path') else None
        prune = self.get('prune')
        # Adjust path and optionally show
        if path is None or path.resolve() == Path.cwd().resolve():
            path = Path('')
        else:
            self.info('path', path, 'green')

        # Prepare the whole tree path and test path prefix
        tree_path = self.testdir / path.unrooted()
        if not tree_path.is_dir() and not self.is_dry_run:
            raise tmt.utils.DiscoverError(
                f"Metadata tree path '{path}' not found.")
        prefix_path = Path('/tests') / path.unrooted()

        # Show filters and test names if provided
        # Check the 'test --filter' option first, then from discover
        filters = list(tmt.base.Test._opt('filters') or self.get('filter', []))
        for filter_ in filters:
            self.info('filter', filter_, 'green')
        # Names of tests selected by --test option
        names = self.get('test', [])
        if names:
            self.info('tests', fmf.utils.listed(names), 'green')

        # Check the 'test --link' option first, then from discover
        # FIXME: cast() - typeless "dispatcher" method
        raw_link_needles = cast(list[str], tmt.Test._opt('links', []) or self.get('link', []))
        link_needles = [tmt.base.LinkNeedle.from_spec(
            raw_needle) for raw_needle in raw_link_needles]

        for link_needle in link_needles:
            self.info('link', str(link_needle), 'green')

        excludes = list(
            tmt.base.Test._opt('exclude') or self.get('exclude', []))

        # Filter only modified tests if requested
        modified_only = self.get('modified-only')
        modified_url = self.get('modified-url')
        if modified_url:
            previous = modified_url
            modified_url = tmt.utils.git.clonable_git_url(modified_url)
            self.info('modified-url', modified_url, 'green')
            if previous != modified_url:
                self.debug(f"Original url was '{previous}'.")
            self.debug(f"Fetch also '{modified_url}' as 'reference'.")
            self.run(Command('git', 'remote', 'add', 'reference', modified_url),
                     cwd=self.testdir)
            self.run(Command('git', 'fetch', 'reference'), cwd=self.testdir)
        if modified_only:
            modified_ref = self.get(
                'modified-ref',
                tmt.utils.git.default_branch(repository=self.testdir, logger=self._logger))
            self.info('modified-ref', modified_ref, 'green')
            ref_commit = self.run(
                Command('git', 'rev-parse', '--short', str(modified_ref)),
                cwd=self.testdir)
            assert ref_commit.stdout is not None
            self.verbose('modified-ref hash', ref_commit.stdout.strip(), 'green')
            output = self.run(
                Command(
                    'git', 'log', '--format=', '--stat', '--name-only', f"{modified_ref}..HEAD"
                    ), cwd=self.testdir)
            if output.stdout:
                directories = [Path(name).parent for name in output.stdout.split('\n')]
                modified = {f"^/{re.escape(str(directory))}"
                            for directory in directories if directory}
                if not modified:
                    # Nothing was modified, do not select anything
                    return
                self.debug(f"Limit to modified test dirs: {modified}", level=3)
                names.extend(modified)
            else:
                self.debug(f"No modified directories between '{modified_ref}..HEAD' found.")
                # Nothing was modified, do not select anything
                return

        # Initialize the metadata tree, search for available tests
        self.debug(f"Check metadata tree in '{tree_path}'.")
        if self.is_dry_run:
            return
        tree = tmt.Tree(
            logger=self._logger,
            path=tree_path,
            fmf_context=self.step.plan._fmf_context,
            additional_rules=self.data.adjust_tests)
        self._tests = tree.tests(
            filters=filters,
            names=names,
            conditions=["manual is False"],
            unique=False,
            links=link_needles,
            excludes=excludes)

        if prune:
            # Save fmf metadata
            clonedir = self.clone_dirpath / 'tests'
            for path in tmt.utils.filter_paths(tree_path, [r'\.fmf']):
                shutil.copytree(
                    path,
                    clonedir / path.relative_to(tree_path),
                    dirs_exist_ok=True)

            # Save upgrade plan
            upgrade_path = self.get('upgrade_path')
            if upgrade_path:
                upgrade_path = f"{upgrade_path.lstrip('/')}.fmf"
                (clonedir / upgrade_path).parent.mkdir()
                shutil.copyfile(tree_path / upgrade_path, clonedir / upgrade_path)
                shutil.copymode(tree_path / upgrade_path, clonedir / upgrade_path)

        # Prefix tests and handle library requires
        for test in self._tests:
            # Propagate `where` key
            test.where = cast(tmt.steps.discover.DiscoverStepData, self.data).where

            if prune:
                # Save only current test data
                assert test.path is not None  # narrow type
                relative_test_path = test.path.unrooted()
                shutil.copytree(
                    tree_path / relative_test_path,
                    clonedir / relative_test_path,
                    dirs_exist_ok=True)

                # Copy all parent main.fmf files
                parent_dir = relative_test_path
                while parent_dir.resolve() != Path.cwd().resolve():
                    parent_dir = parent_dir.parent
                    if (tree_path / parent_dir / 'main.fmf').exists():
                        shutil.copyfile(
                            tree_path / parent_dir / 'main.fmf',
                            clonedir / parent_dir / 'main.fmf')

            # Prefix test path with 'tests' and possible 'path' prefix
            assert test.path is not None  # narrow type
            test.path = prefix_path / test.path.unrooted()
            # Check for possible required beakerlib libraries
            if test.require or test.recommend:
                test.require, test.recommend, _ = tmt.libraries.dependencies(
                    original_require=test.require,
                    original_recommend=test.recommend,
                    parent=self,
                    logger=self._logger,
                    source_location=self.testdir,
                    target_location=clonedir if prune else self.testdir)

        if prune:
            # Clean self.testdir and copy back only required tests and files from clonedir
            # This is to have correct paths in tests
            shutil.rmtree(self.testdir, ignore_errors=True)
            shutil.copytree(clonedir, self.testdir)

        # Cleanup clone directories
        if self.clone_dirpath.exists():
            shutil.rmtree(self.clone_dirpath, ignore_errors=True)

    def post_dist_git(self, created_content: list[Path]) -> None:
        """ Discover tests after dist-git applied patches """
        # Directory to copy out from sources
        dist_git_extract = self.get('dist-git-extract', None)
        dist_git_init = self.get('dist-git-init', False)
        dist_git_merge = self.get('dist-git-merge', False)
        dist_git_remove_fmf_root = self.get('dist-git-remove-fmf-root', False)

        assert self.workdir is not None  # narrow type
        sourcedir = self.workdir / 'source'

        # '/' means everything which was extracted from the srpm and do not flatten
        # glob otherwise
        if dist_git_extract and dist_git_extract != '/':
            try:

                dist_git_extract = Path(
                    glob.glob(str(sourcedir / dist_git_extract.lstrip('/')))[0])
            except IndexError:
                raise tmt.utils.DiscoverError(
                    f"Couldn't glob '{dist_git_extract}' "
                    f"within extracted sources.")
        if dist_git_init:
            if dist_git_extract == '/' or not dist_git_extract:
                dist_git_extract = '/'
                location = sourcedir
            else:
                location = dist_git_extract
            # User specified location or 'root' of extracted sources
            if not (Path(location) / '.fmf').is_dir() and \
                    not self.is_dry_run:
                fmf.Tree.init(location)
        elif dist_git_remove_fmf_root:
            try:
                extracted_fmf_root = tmt.utils.find_fmf_root(
                    sourcedir, ignore_paths=[sourcedir])[0]
            except tmt.utils.MetadataError:
                self.warn("No fmf root to remove, there isn't one already.")
            if not self.is_dry_run:
                shutil.rmtree((dist_git_extract or extracted_fmf_root) / '.fmf')
        if not dist_git_extract:
            try:
                top_fmf_root = tmt.utils.find_fmf_root(sourcedir, ignore_paths=[sourcedir])[0]
            except tmt.utils.MetadataError:
                dist_git_extract = '/'  # Copy all extracted files as well (but later)
                if not dist_git_merge:
                    self.warn(
                        "Extracted sources do not contain fmf root, "
                        "merging with plan data. Avoid this warning by "
                        "explicit use of the '--dist-git-merge' option.")
                    # FIXME - Deprecate this behavior?
                    git_root = self.get_git_root(Path(self.step.plan.node.root))
                    self.debug(f"Copy '{git_root}' to '{self.testdir}'.")
                    if not self.is_dry_run:
                        shutil.copytree(git_root, self.testdir, symlinks=True, dirs_exist_ok=True)

        # Copy extracted sources into testdir
        if not self.is_dry_run:
            flatten = True
            if dist_git_extract == '/':
                flatten = False
                copy_these = created_content
            elif dist_git_extract:
                copy_these = [dist_git_extract.relative_to(sourcedir)]
            else:
                copy_these = [top_fmf_root.relative_to(sourcedir)]
            for to_copy in copy_these:
                src = sourcedir / to_copy
                if src.is_dir():
                    shutil.copytree(
                        sourcedir / to_copy,
                        self.testdir if flatten else self.testdir / to_copy,
                        symlinks=True,
                        dirs_exist_ok=True)
                else:
                    shutil.copyfile(src, self.testdir / to_copy)

        # Discover tests
        self.do_the_discovery()

        # Add TMT_SOURCE_DIR variable for each test
        for test in self._tests:
            test.environment['TMT_SOURCE_DIR'] = EnvVarValue(sourcedir)

        # Inject newly found tests into parent discover at the right position
        # FIXME
        # Prefix test name only if multiple plugins configured
        prefix = f'/{self.name}' if len(self.step.phases()) > 1 else ''
        # Check discovered tests, modify test name/path
        for test in self.tests(enabled=True):
            test.name = f"{prefix}{test.name}"
            test.path = Path(f"/{self.safe_name}{test.path}")
            # Update test environment with plan environment
            test.environment.update(self.step.plan.environment)
            self.step.plan.discover._tests[self.name].append(test)
            test.serial_number = self.step.plan.draw_test_serial_number(test)
        self.step.save()
        self.step.summary()

    def tests(
            self,
            *,
            phase_name: Optional[str] = None,
            enabled: Optional[bool] = None) -> list['tmt.Test']:
        """ Return all discovered tests """

        if phase_name is not None and phase_name != self.name:
            return []

        if enabled is None:
            return self._tests

        return [test for test in self._tests if test.enabled is enabled]
