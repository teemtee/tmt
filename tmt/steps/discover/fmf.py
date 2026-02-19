import contextlib
import glob
import re
import shutil
from typing import Optional, cast

import fmf

import tmt
import tmt.base
import tmt.log
import tmt.options
import tmt.steps
import tmt.steps.discover
import tmt.utils
import tmt.utils.filesystem
import tmt.utils.git
import tmt.utils.url
from tmt.base import _RawAdjustRule
from tmt.container import container, field
from tmt.steps.prepare.distgit import insert_to_prepare_step
from tmt.utils import Command, Path


@container
class DiscoverFmfStepData(tmt.steps.discover.DiscoverStepData):
    path: Optional[str] = field(
        default=cast(Optional[str], None),
        option=('-p', '--path'),
        metavar='ROOT',
        help="""
            Path to the metadata tree root. Must be relative to
            the git repository root if ``url`` was provided, absolute
            local filesystem path otherwise. By default ``.`` is used.
            """,
    )

    # Selecting tests
    test: list[str] = field(
        default_factory=list,
        option=('-t', '--test'),
        metavar='NAMES',
        multiple=True,
        help="""
            List of test names or regular expressions used to
            select tests by name. Duplicate test names are allowed
            to enable repetitive test execution, preserving the
            listed test order. The search mode is used for pattern
            matching. See the :ref:`regular-expressions` section for
            details.
            """,
        normalize=tmt.utils.normalize_string_list,
    )

    link: list[str] = field(
        default_factory=list,
        option='--link',
        metavar="RELATION:TARGET",
        multiple=True,
        help="""
            Select tests using the :tmt:story:`/spec/core/link` keys.
            Values must be in the form of ``RELATION:TARGET``,
            tests containing at least one of them are selected.
            Regular expressions are supported for both relation
            and target. Relation part can be omitted to match all
            relations.
             """,
        normalize=tmt.utils.normalize_string_list,
    )

    filter: list[str] = field(
        default_factory=list,
        option=('-F', '--filter'),
        metavar='FILTERS',
        multiple=True,
        help="""
            Apply advanced filter based on test metadata attributes.
            See ``pydoc fmf.filter`` for more info.
            """,
        normalize=tmt.utils.normalize_string_list,
    )

    include: list[str] = field(
        default_factory=list,
        option=('-i', '--include'),
        metavar='REGEXP',
        multiple=True,
        help="""
            Include only tests matching given regular expression.
            Respect the :tmt:story:`/spec/core/order` defined in test.
            The search mode is used for pattern matching. See the
            :ref:`regular-expressions` section for details.
            """,
        normalize=tmt.utils.normalize_string_list,
    )

    exclude: list[str] = field(
        default_factory=list,
        option=('-x', '--exclude'),
        metavar='REGEXP',
        multiple=True,
        help="""
            Exclude tests matching given regular expression.
            The search mode is used for pattern matching. See the
            :ref:`regular-expressions` section for details.
            """,
        normalize=tmt.utils.normalize_string_list,
    )

    # Modified only
    modified_only: bool = field(
        default=False,
        option=('-m', '--modified-only'),
        is_flag=True,
        help="""
            Set to ``true`` if you want to filter modified tests
            only. The test is modified if its name starts with
            the name of any directory modified since ``modified-ref``.
            """,
    )

    modified_url: Optional[str] = field(
        default=cast(Optional[str], None),
        option='--modified-url',
        metavar='REPOSITORY',
        help="""
            An additional remote repository to be used as the
            reference for comparison. Will be fetched as a
            reference remote in the test dir.
            """,
    )

    modified_ref: Optional[str] = field(
        default=cast(Optional[str], None),
        option='--modified-ref',
        metavar='REVISION',
        help="""
            The branch, tag or commit specifying the reference git revision (if not provided, the
            default branch is used). Note that you need to specify ``reference/<branch>`` to
            compare to a branch from the repository specified in ``modified-url``.
            """,
    )

    # Dist git integration
    dist_git_init: bool = field(
        default=False,
        option='--dist-git-init',
        is_flag=True,
        help="""
             Set to ``true`` to initialize fmf root inside extracted sources at
             ``dist-git-extract`` location or top directory. To be used when the
             sources contain fmf files (for example tests) but do not have an
             associated fmf root.
             """,
    )
    dist_git_remove_fmf_root: bool = field(
        default=False,
        option='--dist-git-remove-fmf-root',
        is_flag=True,
        help="""
             Remove fmf root from extracted source (top one or selected by copy-path, happens
             before dist-git-extract.
             """,
    )
    dist_git_merge: bool = field(
        default=False,
        option='--dist-git-merge',
        is_flag=True,
        help="""
            Set to ``true`` to combine fmf root from the sources and fmf root from the plan.
            It allows to have plans and tests defined in the DistGit repo which use tests
            and other resources from the downloaded sources. Any plans in extracted sources
            will not be processed.
            """,
    )
    dist_git_extract: Optional[str] = field(
        default=cast(Optional[str], None),
        option='--dist-git-extract',
        help="""
             What to copy from extracted sources, globbing is supported. Defaults to the top fmf
             root if it is present, otherwise top directory (shortcut "/").
             """,
    )

    # Special options
    sync_repo: bool = field(
        default=False,
        option='--sync-repo',
        is_flag=True,
        help="""
             Force the sync of the whole git repo. By default, the repo is copied only if the used
             options require it.
             """,
    )
    fmf_id: bool = field(
        default=False,
        option='--fmf-id',
        is_flag=True,
        help='Only print fmf identifiers of discovered tests to the standard output and exit.',
    )
    prune: bool = field(
        default=False,
        option=('--prune / --no-prune'),
        is_flag=True,
        show_default=True,
        help="Copy only immediate directories of executed tests and their required files.",
    )

    # Edit discovered tests
    # Note: normalize_adjust returns a list as per its type hint
    adjust_tests: list[_RawAdjustRule] = field(
        default_factory=list,
        normalize=tmt.utils.normalize_adjust,
        help="""
             Modify metadata of discovered tests from the plan itself. Use the
             same format as for adjust rules.
             """,
    )

    # Upgrade plan path so the plan is not pruned
    upgrade_path: Optional[str] = field(default=None, internal=True)

    # Legacy fields
    repository: Optional[str] = field(
        default=None,
        option='--repository',
        deprecated=tmt.options.Deprecated(since="1.66", hint="use 'url' instead"),
    )
    revision: Optional[str] = field(
        default=None,
        option='--revision',
        deprecated=tmt.options.Deprecated(since="1.66", hint="use 'ref' instead"),
    )

    def post_normalization(
        self,
        raw_data: tmt.steps._RawStepData,
        logger: tmt.log.Logger,
    ) -> None:
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

    Archive
    ^^^^^^^

    By default ``url`` is treated as a git url to be cloned, but you can set
    ``url-content-type`` to ``archive`` to instead treat it as an archive url
    and download and extract it. For example:

    .. code-block:: yaml

        discover:
            how: fmf
            url: https://github.com/teemtee/tmt/archive/refs/heads/main.tar.gz
            url-content-type: archive
            path: /tmt-main/fmf/root

    Dist Git
    ^^^^^^^^

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

    Name Filter
    ^^^^^^^^^^^

    Use the ``test`` key to limit which tests should be executed by
    providing regular expression matching the test name:

    .. code-block:: yaml

        discover:
            how: fmf
            test: ^/tests/area/.*

    .. code-block:: shell

        tmt run discover --how fmf --verbose --test "^/tests/core.*"

    When several regular expressions are provided, tests matching each
    regular expression are concatenated. In this way it is possible to
    execute a single test multiple times:

    .. code-block:: yaml

        discover:
            how: fmf
            test:
              - ^/test/one$
              - ^/test/two$
              - ^/special/setup$
              - ^/test/one$
              - ^/test/two$

    .. code-block:: shell

        tmt run discover -h fmf -v -t '^/test/one$' -t '^/special/setup$' -t '^/test/two$'

    The ``include`` key also allows to select tests by name, with two
    important distinctions from the ``test`` key:

    * The original test :tmt:story:`/spec/core/order` is preserved so it does
      not matter in which order tests are listed under the ``include``
      key.

    * Test duplication is not allowed, so even if a test name is
      repeated several times, test will be executed only once.

    Finally, the ``exclude`` key can be used to specify regular
    expressions matching tests which should be skipped during the
    discovery.

    The ``test``, ``include`` and ``exclude`` keys use search mode for
    matching patterns. See the :ref:`regular-expressions` section for
    detailed information about how exactly the regular expressions are
    handled.

    Link Filter
    ^^^^^^^^^^^

    Selecting tests containing specified link is possible using ``link``
    key accepting ``RELATION:TARGET`` format of values. Regular
    expressions are supported for both relation and target part of the
    value. Relation can be omitted to target match any relation.

    .. code-block:: yaml

        discover:
            how: fmf
            link: verifies:.*issue/850$

    Multiple links can be provided as well:

    .. code-block:: yaml

        discover:
            how: fmf
            link:
              - verifies:.*issue/850$
              - verifies:.*issue/1374$

    Advanced Filter
    ^^^^^^^^^^^^^^^

    The ``filter`` key can be used to apply an advanced filter based on
    test metadata attributes. These can be especially useful when tests
    are grouped by the :tmt:story:`/spec/core/tag` or :tmt:story:`/spec/core/tier`
    keys:

    .. code-block:: yaml

        discover:
            how: fmf
            filter: tier:3 & tag:provision

    .. code-block:: shell

        tmt run discover --how fmf --filter "tier:3 & tag:provision"

    See the ``pydoc fmf.filter`` documentation for more details about
    the supported syntax and available operators.

    Modified Tests
    ^^^^^^^^^^^^^^

    It is also possible to limit tests only to those that have changed
    in git since a given revision. This can be particularly useful when
    testing changes to tests themselves (e.g. in a pull request CI).

    Related keys: ``modified-only``, ``modified-url``, ``modified-ref``

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

    Adjust Tests
    ^^^^^^^^^^^^

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
    _REQUIRES_GIT = {
        "ref",
        "modified_url",
        "modified_only",
        "fmf_id",
        "sync_repo",
    }

    @property
    def is_in_standalone_mode(self) -> bool:
        """
        Enable standalone mode when listing fmf ids
        """

        if self.data.fmf_id:
            return True
        return super().is_in_standalone_mode

    def _fetch_remote_source(self, url: str) -> Optional[Path]:
        super()._fetch_remote_source(url)
        return Path(self.data.path) if self.data.path else None

    def _fetch_local_repository(self) -> Optional[Path]:
        path = Path(self.data.path) if self.data.path else None
        if path is not None:
            fmf_root: Optional[Path] = path
        else:
            fmf_root = self.step.plan.fmf_root

        requires_git = any(getattr(self.data, key) for key in self._REQUIRES_GIT)

        # Path for distgit sources cannot be checked until
        # they are extracted
        if path and not path.is_dir() and not self.data.dist_git_source:
            raise tmt.utils.DiscoverError(f"Provided path '{path}' is not a directory.")
        if self.data.dist_git_source:
            # Ensure we're in a git repo when extracting dist-git sources
            if self.step.plan.fmf_root is None:
                raise tmt.utils.DiscoverError("No git repository found for DistGit.")
            git_root = tmt.utils.git.git_root(
                fmf_root=self.step.plan.fmf_root, logger=self._logger
            )
            if not git_root:
                raise tmt.utils.DiscoverError(f"{self.step.plan.fmf_root} is not a git repo")
        else:
            if fmf_root is None:
                raise tmt.utils.DiscoverError("No metadata found in the current directory.")
            # Check git repository root (use fmf root if not found)
            git_root = tmt.utils.git.git_root(fmf_root=fmf_root, logger=self._logger)
            if not git_root:
                self.debug(f"Git root not found, using '{fmf_root}.'")
                git_root = fmf_root
            # Set path to relative path from the git root to fmf root
            path = fmf_root.resolve().relative_to(
                git_root.resolve() if requires_git else fmf_root.resolve()
            )

        # Copy the git/fmf root directory to test_dir
        # (for dist-git case only when merge explicitly requested)
        if requires_git:
            directory: Path = git_root
        else:
            assert fmf_root is not None  # narrow type
            directory = fmf_root
        self.info('directory', directory, 'green')
        if not self.data.dist_git_source or self.data.dist_git_merge:
            self.debug(f"Copy '{directory}' to '{self.test_dir}'.")
            if not self.is_dry_run:
                tmt.utils.filesystem.copy_tree(directory, self.test_dir, self._logger)
        return path

    def go(self, *, path: Optional[Path] = None, logger: Optional[tmt.log.Logger] = None) -> None:
        """
        Discover available tests
        """

        super().go(path=path, logger=logger)

        dist_git_source = self.get('dist-git-source', False)
        dist_git_merge = self.get('dist-git-merge', False)

        # No tests are selected in some cases
        self._tests: list[tmt.Test] = []

        # Self checks
        if dist_git_source and not dist_git_merge and (self.data.ref or self.data.url):
            raise tmt.utils.DiscoverError(
                "Cannot manipulate with dist-git without the `--dist-git-merge` option."
            )

        self.log_import_plan_details()

        # Dist-git source processing during discover step
        if dist_git_source:
            try:
                if self.data.url:
                    fmf_root = self.test_dir
                elif self.step.plan.fmf_root:
                    fmf_root = self.step.plan.fmf_root
                else:
                    raise tmt.utils.DiscoverError("No git repository found.")

                git_root = tmt.utils.git.git_root(fmf_root=fmf_root, logger=self._logger)
                if not git_root:
                    raise tmt.utils.DiscoverError(
                        f"Directory '{fmf_root}' is not a git repository."
                    )

                distgit_dir = self.test_dir if self.data.ref else git_root
                self.process_distgit_source(distgit_dir)
                return
            except Exception as error:
                raise tmt.utils.DiscoverError("Failed to process 'dist-git-source'.") from error

        # Discover tests
        self._tests = self.do_the_discovery(path)

    def process_distgit_source(self, distgit_dir: Path) -> None:
        """
        Process dist-git source during the discover step.
        """

        self.download_distgit_source(
            distgit_dir=distgit_dir,
            target_dir=self.source_dir,
            handler_name=self.get('dist-git-type'),
        )

        # Copy rest of files so TMT_SOURCE_DIR has patches, sources and spec file
        # FIXME 'worktree' could be used as source_dir when 'url' is not set
        tmt.utils.filesystem.copy_tree(
            distgit_dir,
            self.source_dir,
            self._logger,
        )

        # patch & rediscover will happen later in the prepare step
        if not self.get('dist-git-download-only'):
            # Check if prepare is enabled, warn user if not
            if not self.step.plan.prepare.enabled:
                self.warn("Sources will not be extracted, prepare step is not enabled.")

            insert_to_prepare_step(
                discover_plugin=self,
                sourcedir=self.source_dir,
            )

        # merge or not, detect later
        self.step.plan.discover.extract_tests_later = True
        self.info("Tests will be discovered after dist-git patching in prepare.")

    def do_the_discovery(self, path: Optional[Path] = None) -> list['tmt.base.Test']:
        """
        Discover the tests
        """
        # Prepare the whole tree path
        path = path or Path('')
        tree_path = self.test_dir / path.unrooted()
        if not tree_path.is_dir() and not self.is_dry_run:
            raise tmt.utils.DiscoverError(f"Metadata tree path '{path}' not found.")

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
        link_needles = [
            tmt.base.LinkNeedle.from_spec(raw_needle) for raw_needle in raw_link_needles
        ]

        for link_needle in link_needles:
            self.info('link', str(link_needle), 'green')

        excludes = list(tmt.base.Test._opt('exclude') or self.data.exclude)
        includes = list(tmt.base.Test._opt('include') or self.data.include)

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
            self.run(
                Command('git', 'remote', 'add', 'reference', modified_url),
                cwd=self.test_dir,
            )
            self.run(
                Command('git', 'fetch', 'reference'),
                cwd=self.test_dir,
            )
        if modified_only:
            modified_ref = self.get(
                'modified-ref',
                tmt.utils.git.default_branch(repository=self.test_dir, logger=self._logger),
            )
            self.info('modified-ref', modified_ref, 'green')
            ref_commit = self.run(
                Command('git', 'rev-parse', '--short', str(modified_ref)),
                cwd=self.test_dir,
            )
            assert ref_commit.stdout is not None
            self.verbose('modified-ref hash', ref_commit.stdout.strip(), 'green')
            output = self.run(
                Command(
                    'git', 'log', '--format=', '--stat', '--name-only', f"{modified_ref}..HEAD"
                ),
                cwd=self.test_dir,
            )
            if output.stdout:
                directories = [Path(name).parent for name in output.stdout.split('\n')]
                modified = {
                    f"^/{re.escape(str(directory))}" for directory in directories if directory
                }
                if not modified:
                    # Nothing was modified, do not select anything
                    return []
                self.debug(f"Limit to modified test dirs: {modified}", level=3)
                names.extend(modified)
            else:
                self.debug(f"No modified directories between '{modified_ref}..HEAD' found.")
                # Nothing was modified, do not select anything
                return []

        # Initialize the metadata tree, search for available tests
        self.debug(f"Check metadata tree in '{tree_path}'.")
        if self.is_dry_run:
            return []
        tree = tmt.Tree(
            logger=self._logger,
            path=tree_path,
            fmf_context=self.step.plan.fmf_context,
            additional_rules=self.data.adjust_tests,
        )
        return tree.tests(
            filters=filters,
            names=names,
            conditions=["manual is False"],
            unique=False,
            links=link_needles,
            includes=includes,
            excludes=excludes,
        )

    def post_dist_git(self, created_content: list[Path]) -> None:
        """
        Discover tests after dist-git applied patches
        """

        # Directory to copy out from sources
        dist_git_extract = self.get('dist-git-extract', None)
        dist_git_init = self.get('dist-git-init', False)
        dist_git_merge = self.get('dist-git-merge', False)
        dist_git_remove_fmf_root = self.get('dist-git-remove-fmf-root', False)

        # '/' means everything which was extracted from the srpm and do not flatten
        # glob otherwise
        if dist_git_extract and dist_git_extract != '/':
            try:
                dist_git_extract = Path(
                    glob.glob(str(self.source_dir / dist_git_extract.lstrip('/')))[0]
                )
            except IndexError as error:
                raise tmt.utils.DiscoverError(
                    f"Couldn't glob '{dist_git_extract}' within extracted sources."
                ) from error
        if dist_git_init:
            if dist_git_extract == '/' or not dist_git_extract:
                dist_git_extract = '/'
                location = self.source_dir
            else:
                location = dist_git_extract
            # User specified location or 'root' of extracted sources
            if not (Path(location) / '.fmf').is_dir() and not self.is_dry_run:
                fmf.Tree.init(location)
        elif dist_git_remove_fmf_root:
            try:
                extracted_fmf_root = tmt.utils.find_fmf_root(
                    self.source_dir,
                    ignore_paths=[self.source_dir],
                )[0]
            except tmt.utils.MetadataError:
                self.warn("No fmf root to remove, there isn't one already.")
            if not self.is_dry_run:
                shutil.rmtree((dist_git_extract or extracted_fmf_root) / '.fmf')
        if not dist_git_extract:
            try:
                top_fmf_root = tmt.utils.find_fmf_root(
                    self.source_dir, ignore_paths=[self.source_dir]
                )[0]
            except tmt.utils.MetadataError as error:
                dist_git_extract = '/'  # Copy all extracted files as well (but later)
                if not dist_git_merge:
                    self.warn(
                        "Extracted sources do not contain fmf root, "
                        "merging with plan data. Avoid this warning by "
                        "explicit use of the '--dist-git-merge' option."
                    )
                    # FIXME - Deprecate this behavior?
                    git_root = tmt.utils.git.git_root(
                        fmf_root=Path(self.step.plan.node.root), logger=self._logger
                    )
                    if not git_root:
                        raise tmt.utils.DiscoverError(
                            f"Directory '{self.step.plan.node.root}' is not in a git repository."
                        ) from error
                    self.debug(f"Copy '{git_root}' to '{self.test_dir}'.")
                    if not self.is_dry_run:
                        tmt.utils.filesystem.copy_tree(git_root, self.test_dir, self._logger)

        # Copy extracted sources into test_dir
        if not self.is_dry_run:
            flatten = True
            if dist_git_extract == '/':
                flatten = False
                copy_these = created_content
            elif dist_git_extract:
                copy_these = [dist_git_extract.relative_to(self.source_dir)]
            else:
                copy_these = [top_fmf_root.relative_to(self.source_dir)]
            for to_copy in copy_these:
                src = self.source_dir / to_copy
                if src.is_dir():
                    tmt.utils.filesystem.copy_tree(
                        self.source_dir / to_copy,
                        self.test_dir if flatten else self.test_dir / to_copy,
                        self._logger,
                    )
                else:
                    shutil.copyfile(src, self.test_dir / to_copy)

        path = Path(cast(str, self.get('path'))) if self.get('path') else None
        # Adjust path and optionally show
        if path is None or path.resolve() == Path.cwd().resolve():
            path = Path('')
        else:
            self.info('path', path, 'green')

        # Discover tests
        self._tests = self.do_the_discovery(path)

        if self.get('prune', False):
            clone_dir = self.clone_dirpath / 'tests'
            self.install_libraries(self.test_dir, clone_dir)
            self.prune_tree(clone_dir, path)
        else:
            self.install_libraries(self.test_dir, self.test_dir)

        self.adjust_test_attributes(path)
        self.apply_policies()

        # Inject newly found tests into parent discover at the right position
        # FIXME
        # Prefix test name only if multiple plugins configured
        prefix = f'/{self.name}' if len(self.step.phases()) > 1 else ''
        # Check discovered tests, modify test name/path
        for test_origin in self.tests(enabled=True):
            test = test_origin.test

            test.name = f"{prefix}{test.name}"
            test.path = Path(f"/{self.safe_name}{test.path}")

            self.step.plan.discover._tests[self.name].append(test)
            test.serial_number = self.step.plan.draw_test_serial_number(test)
        self.step.save()
        self.step.summary()

    def tests(
        self, *, phase_name: Optional[str] = None, enabled: Optional[bool] = None
    ) -> list[tmt.steps.discover.TestOrigin]:
        """
        Return all discovered tests
        """

        if phase_name is not None and phase_name != self.name:
            return []

        if enabled is None:
            return [
                tmt.steps.discover.TestOrigin(test=test, phase=self.name) for test in self._tests
            ]

        return [
            tmt.steps.discover.TestOrigin(test=test, phase=self.name)
            for test in self._tests
            if test.enabled is enabled
        ]
