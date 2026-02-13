import abc
import contextlib
import shutil
from collections import defaultdict
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any, Literal, Optional, TypeVar, cast

import click
from fmf.utils import listed

import tmt
from tmt.container import container, field, key_to_option

if TYPE_CHECKING:
    import tmt.cli
    import tmt.export
    import tmt.options
    import tmt.steps

import tmt.base.core
import tmt.steps
import tmt.utils
import tmt.utils.filesystem
import tmt.utils.git
import tmt.utils.url
from tmt.options import option
from tmt.plugins import PluginRegistry
from tmt.steps import Action
from tmt.utils import Command, Environment, EnvVarValue, GeneralError, Path


def normalize_ref(
    key_address: str,
    value: Optional[Any],
    logger: tmt.log.Logger,
) -> Optional[str]:
    if value is None:
        return None

    if isinstance(value, str):
        return value

    raise tmt.utils.NormalizationError(key_address, value, 'unset or a string')


@container
class TestOrigin:
    """
    Describes the origin of a test.
    """

    #: Name of the ``discover`` phase that added the test.
    phase: str

    #: The test in question.
    test: 'tmt.Test'


@container
class DiscoverStepData(tmt.steps.WhereableStepData, tmt.steps.StepData):
    url: Optional[str] = field(
        default=cast(Optional[str], None),
        option=('-u', '--url'),
        metavar='URL',
        help="""
            External URL containing the metadata tree.
            Current git repository used by default.
            See ``url-content-type`` key for details on what content is accepted.
            """,
    )

    url_content_type: Literal["git", "archive"] = field(
        default="git",
        option="--url-content-type",
        help="""
            How to handle the ``url`` key.
            """,
        choices=("git", "archive"),
    )

    ref: Optional[str] = field(
        default=cast(Optional[str], None),
        option=('-r', '--ref'),
        metavar='REVISION',
        help="""
            Branch, tag or commit specifying the desired git
            revision. Defaults to the remote repository's default
            branch if ``url`` was set or to the current ``HEAD``
            of the current repository.

            Additionally, one can set ``ref`` dynamically.
            This is possible using a special file in tmt format
            stored in the *default* branch of a tests repository.
            This special file should contain rules assigning attribute ``ref``
            in an *adjust* block, for example depending on a test run context.

            Dynamic ``ref`` assignment is enabled whenever a test plan
            reference has the format ``ref: @FILEPATH``.
            """,
        normalize=normalize_ref,
    )

    dist_git_source: bool = field(
        default=False,
        option='--dist-git-source',
        is_flag=True,
        help='Download DistGit sources and ``rpmbuild -bp`` them (can be skipped).',
    )

    # TODO: use enum!
    dist_git_type: Optional[str] = field(
        default=None,
        option='--dist-git-type',
        choices=tmt.utils.git.get_distgit_handler_names,
        help="""
            Use the provided DistGit handler instead of the auto detection.
            Useful when running from forked repositories.
            """,
    )

    dist_git_download_only: bool = field(
        default=False,
        option="--dist-git-download-only",
        is_flag=True,
        help="Just download the sources. No ``rpmbuild -bp``, "
        "nor installation of require or buildddeps happens.",
    )

    dist_git_install_builddeps: bool = field(
        default=False,
        option="--dist-git-install-builddeps",
        is_flag=True,
        help="Install package build dependencies according to the specfile.",
    )

    dist_git_require: list['tmt.base.core.DependencySimple'] = field(
        default_factory=list,
        option="--dist-git-require",
        metavar='PACKAGE',
        multiple=True,
        help="""
            Additional required package to be present before sources are prepared.
            The ``rpm-build`` package itself is installed automatically.
            """,
        # *simple* requirements only
        normalize=lambda key_address, value, logger: tmt.base.core.assert_simple_dependencies(
            tmt.base.core.normalize_require(key_address, value, logger),
            "'dist_git_require' can be simple packages only",
            logger,
        ),
        serialize=lambda packages: [package.to_spec() for package in packages],
        unserialize=lambda serialized: [
            tmt.base.core.DependencySimple.from_spec(package) for package in serialized
        ],
    )

    require_test: list[str] = field(
        default_factory=list,
        option=('--require-test'),
        metavar='NAMES',
        multiple=True,
        help="""
            A list of test names that must be discovered during the run. If an execute
            step is present, these tests must also be executed. If any of the
            specified tests are not discovered or executed, an exception is raised.
            """,
        normalize=tmt.utils.normalize_string_list,
    )


DiscoverStepDataT = TypeVar('DiscoverStepDataT', bound=DiscoverStepData)


class DiscoverPlugin(tmt.steps.GuestlessPlugin[DiscoverStepDataT, None]):
    """
    Common parent of discover plugins
    """

    # ignore[assignment]: as a base class, DiscoverStepData is not included in
    # DiscoverStepDataT.
    _data_class = DiscoverStepData  # type: ignore[assignment]

    # Methods ("how: ..." implementations) registered for the same step.
    _supported_methods: PluginRegistry[tmt.steps.Method] = PluginRegistry('step.discover')

    @property
    def test_dir(self) -> Path:
        return self.phase_workdir / 'tests'

    @property
    def source_dir(self) -> Path:
        return self.phase_workdir / 'source'

    @classmethod
    def base_command(
        cls,
        usage: str,
        method_class: Optional[type[click.Command]] = None,
    ) -> click.Command:
        """
        Create base click command (common for all discover plugins)
        """

        # Prepare general usage message for the step
        if method_class:
            usage = Discover.usage(method_overview=usage)

        # Create the command
        @click.command(cls=method_class, help=usage)
        @click.pass_context
        @option('-h', '--how', metavar='METHOD', help='Use specified method to discover tests.')
        @tmt.steps.PHASE_OPTIONS
        def discover(context: 'tmt.cli.Context', **kwargs: Any) -> None:
            context.obj.steps.add('discover')
            Discover.store_cli_invocation(context)

        return discover

    def go(self, *, path: Optional[Path] = None, logger: Optional[tmt.log.Logger] = None) -> None:
        """
        Perform actions shared among plugins when beginning their tasks
        """

        self.go_prolog(logger or self._logger)

    @abc.abstractmethod
    def tests(
        self, *, phase_name: Optional[str] = None, enabled: Optional[bool] = None
    ) -> list['TestOrigin']:
        """
        Return discovered tests.

        :param phase_name: if set, return only tests discovered by the
            phase of this name. Otherwise, all tests discovered by the
            phase are returned.

            .. note::

               This parameter exists to present unified interface with
               :py:meth:`tmt.steps.discover.Discover.tests` API, but it
               has no interesting effect in case of individual phases:

               * left unset, all tests discovered by the phase are
                 returned,
               * set to a phase name, tests discovered by that phase
                 should be returned. But a phase does not have access to
                 other phases' tests, therefore setting it to anything
                 but this phase name would produce an empty list.
        :param enabled: if set, return only tests that are enabled
            (``enabled=True``) or disabled (``enabled=False``). Otherwise,
            all tests are returned.
        :returns: a list of phase name and test pairs.
        """

        raise NotImplementedError

    def download_distgit_source(
        self,
        distgit_dir: Path,
        target_dir: Path,
        handler_name: Optional[str] = None,
    ) -> None:
        """
        Download sources to the target_dir

        distgit_dir is path to the DistGit repository
        """

        tmt.utils.git.distgit_download(
            distgit_dir=distgit_dir,
            target_dir=target_dir,
            handler_name=handler_name,
            caller=self,
            logger=self._logger,
        )

    def log_import_plan_details(self) -> None:
        """
        Log details about the imported plan
        """

        parent = cast(Optional[Discover], self.parent)
        if (
            parent
            and parent.plan._original_plan
            and parent.plan._original_plan._imported_plan_references
        ):
            for remote_plan_id in parent.plan._original_plan._imported_plan_references:
                # FIXME: cast() - https://github.com/python/mypy/issues/7981
                # Note the missing Optional for values - to_minimal_dict() would
                # not include unset keys, therefore all values should be valid.
                for key, value in cast(dict[str, str], remote_plan_id.to_minimal_spec()).items():
                    self.verbose(f'import {key}', value, 'green')

    def post_dist_git(self, created_content: list[Path]) -> None:
        """
        Discover tests after dist-git applied patches
        """

    def _fetch_remote_source(self, url: str) -> Optional[Path]:
        """
        Fetch a remote git repository or archive from the given url to test_dir.

        :param url: URL of the remote source.
        :returns: Potential path to the metadata tree root within the fetched source.
        """
        self.info('url', url, 'green')
        if self.data.url_content_type == "git":
            self.debug(f"Clone '{url}' to '{self.test_dir}'.")
            tmt.utils.git.git_clone(
                url=url,
                destination=self.test_dir,
                shallow=self.data.ref is None,
                env=Environment({"GIT_ASKPASS": EnvVarValue("echo")}),
                logger=self._logger,
            )
        elif self.data.url_content_type == "archive":
            archive_path = tmt.utils.url.download(url, self.phase_workdir, logger=self._logger)
            self.debug(f"Extracting archive to '{self.test_dir}'.")
            shutil.unpack_archive(archive_path, self.test_dir)
        else:
            raise ValueError(
                f"url-content-type has unsupported value: '{self.data.url_content_type}'. "
                "Only 'git' and 'archive' are supported."
            )
        return None

    def _fetch_local_repository(self) -> Optional[Path]:
        """
        Fetch local repository.

        :returns: Path to the root of the metadata tree within the copied repository.
        """
        raise NotImplementedError

    def fetch_source(self) -> Path:
        """
        Fetch a local repository or remote source based on phase configuration.

        :returns: Path to the root of the metadata tree within the fetched source.
        """
        if self.data.url is None:
            path = self._fetch_local_repository()
        else:
            path = self._fetch_remote_source(url=self.data.url)

        if path is None or path.resolve() == Path.cwd().resolve():
            return Path('')
        self.info('path', path, 'green')
        return path

    def checkout_ref(self) -> None:
        """
        Resolve dynamic reference and perform checkout based on phase configuration
        """
        if not self.test_dir.exists():
            self.debug('Test directory does not exist, skipping ref checkout.')
            return

        # Check if we are in a git repository
        if not tmt.utils.git.git_root(fmf_root=self.test_dir, logger=self._logger):
            self.debug('Not a git repository, skipping ref checkout.')
            return

        # Prepare path of the dynamic reference
        try:
            ref = tmt.base.core.resolve_dynamic_ref(
                logger=self._logger,
                workdir=self.test_dir,
                ref=self.data.ref,
                plan=self.step.plan,
            )
        except tmt.utils.FileError as error:
            raise tmt.utils.DiscoverError("Could not resolve dynamic reference") from error

        if ref:
            self.info('ref', ref, 'green')
            self.debug(f"Checkout ref '{ref}'.")
            self.run(Command('git', 'checkout', '-f', ref), cwd=self.test_dir)

        # Show current commit hash if inside a git repository
        if self.test_dir.is_dir():
            with contextlib.suppress(tmt.utils.RunError, AttributeError):
                self.verbose(
                    'commit-hash',
                    tmt.utils.git.git_hash(directory=self.test_dir, logger=self._logger),
                    'green',
                )

    def prune_tree(
        self,
        clone_dir: Path,
        path: Path,
    ) -> None:
        """
        Prune test directory to include only discovered tests and required metadata.

        :param clone_dir: Path to the temporary clone directory.
        :param path: Original path used for discovery.
        """
        tree_path = self.test_dir / path.unrooted()
        clone_tree_path = clone_dir / path.unrooted()

        # Save fmf metadata
        for file_path in tmt.utils.filter_paths(tree_path, [r'\.fmf']):
            tmt.utils.filesystem.copy_tree(
                file_path,
                clone_tree_path / file_path.relative_to(tree_path),
                self._logger,
            )

        # Save upgrade plan
        upgrade_path = self.get('upgrade-path')
        if upgrade_path:
            upgrade_path = f"{upgrade_path.lstrip('/')}.fmf"
            (clone_tree_path / upgrade_path).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(tree_path / upgrade_path, clone_tree_path / upgrade_path)
            shutil.copymode(tree_path / upgrade_path, clone_tree_path / upgrade_path)

        for test_origin in self.tests():
            test = test_origin.test
            # Save only current test data
            assert test.path is not None  # narrow type
            relative_test_path = test.path.unrooted()
            tmt.utils.filesystem.copy_tree(
                tree_path / relative_test_path,
                clone_tree_path / relative_test_path,
                self._logger,
            )

            # Copy all parent main.fmf files
            parent_dir = relative_test_path
            while parent_dir.resolve() != Path.cwd().resolve():
                parent_dir = parent_dir.parent
                if (tree_path / parent_dir / 'main.fmf').exists():
                    # Ensure parent directory exists
                    (clone_tree_path / parent_dir).mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(
                        tree_path / parent_dir / 'main.fmf',
                        clone_tree_path / parent_dir / 'main.fmf',
                    )

        # Clean phase.test_dir and copy back only required tests and files from clone_dir
        # This is to have correct paths in tests
        shutil.rmtree(self.test_dir, ignore_errors=True)
        tmt.utils.filesystem.copy_tree(clone_dir, self.test_dir, self._logger)

        if self.clone_dirpath.exists():
            shutil.rmtree(self.clone_dirpath, ignore_errors=True)

    def install_libraries(self, source: Path, target: Path) -> None:
        """
        Install required beakerlib libraries for discovered tests.

        :param source: Source directory of the tests.
        :param target: Target directory where libraries should be installed.
        """
        import tmt.libraries

        unresolved_dependencies: dict[str, dict[str, set[str]]] = defaultdict(
            lambda: defaultdict(set)
        )

        for test_origin in self.tests():
            test = test_origin.test
            if test.require or test.recommend:
                test.require, test.recommend, _ = tmt.libraries.dependencies(
                    original_require=test.require,
                    original_recommend=test.recommend,
                    parent=self,
                    logger=self._logger,
                    source_location=source,
                    target_location=target,
                )

                dependencies = (*test.require, *test.recommend)

                for dependency in dependencies:
                    if isinstance(dependency, tmt.base.DependencySimple):
                        continue

                    dependency_class_name = dependency.__class__.__name__

                    if isinstance(dependency, tmt.base.DependencyFmfId):
                        unresolved_dependencies[dependency_class_name][dependency.name or '/'].add(
                            test.name
                        )

                    elif isinstance(dependency, tmt.base.DependencyFile):
                        for pattern in dependency.pattern or []:
                            unresolved_dependencies[dependency_class_name][pattern].add(test.name)

                    else:
                        unresolved_dependencies[dependency_class_name][str(dependency)].add(
                            test.name
                        )

        # Report all failures in one go so users can fix multiple tests
        # without rerunning tmt repeatedly.
        if unresolved_dependencies:

            def _report_unresolved_dependencies(
                dependencies: dict[str, dict[str, set[str]]],
                dependency_class_name: str,
                label: Optional[str] = None,
            ) -> None:
                display_label = label or f"{dependency_class_name} dependency"
                for dependency_name, tests in sorted(
                    dependencies.pop(dependency_class_name, {}).items()
                ):
                    test_names = ', '.join(f"'{name}'" for name in sorted(tests))
                    self._logger.fail(
                        f"Failed to process {display_label} ({dependency_name}) "
                        f"for test {test_names}."
                    )

            # Known types first
            for dependency_class_name, label in (
                (tmt.base.DependencyFmfId.__name__, "beakerlib libraries"),
                (tmt.base.DependencyFile.__name__, "file dependencies"),
            ):
                _report_unresolved_dependencies(
                    unresolved_dependencies, dependency_class_name, label
                )

            # Anything else
            for dependency_class_name in sorted(unresolved_dependencies):
                _report_unresolved_dependencies(unresolved_dependencies, dependency_class_name)

            raise tmt.utils.DiscoverError('Failed to process some dependencies.')

    def apply_policies(self) -> None:
        """
        Apply policies to discovered tests.
        """

        if self.step.plan.my_run is not None:
            tests = [test_origin.test for test_origin in self.tests()]
            for policy in self.step.plan.my_run.policies:
                policy.apply_to_tests(tests=tests, logger=self._logger)

    def adjust_test_attributes(self, path: Path) -> None:
        """
        Adjust test attributes such as path, where condition, and environment

        :param path: Original path used for discovery.
        """
        for test_origin in self.tests():
            test = test_origin.test
            # Prefix test path with 'tests' and possible 'path' prefix
            if test.path is None:
                test.path = Path('/tests') / path.unrooted()
            else:
                test.path = Path('/tests') / path.unrooted() / test.path.unrooted()

            # Propagate 'where' condition from discover phase to the test
            test.where = self.data.where

            if bool(self.get('dist-git-source', False)):
                test.environment['TMT_SOURCE_DIR'] = EnvVarValue(self.source_dir)

    def apply_phase_prefix(self, prefix: str) -> None:
        """
        Apply phase name prefix to discovered tests
        """
        for test_origin in self.tests():
            test = test_origin.test

            test.name = f"{prefix}{test.name}"
            test.path = Path(f"/{self.safe_name}{test.path}")

    def discover_from_recipe(self, logger: Optional[tmt.log.Logger] = None) -> None:
        """
        Discover tests directly from the recipe.
        """
        self.go_prolog(logger or self._logger)

        assert self.step.plan.my_run is not None
        assert self.step.plan.my_run.recipe is not None

        self._tests = [
            test_origin.test
            for test_origin in self.step.plan.my_run.recipe_manager.tests(
                self.step.plan.my_run.recipe,
                self.step.plan.name,
            )
            if test_origin.phase == self.name
        ]


class Discover(tmt.steps.Step):
    """
    Gather information about test cases to be executed.
    """

    _plugin_base_class = DiscoverPlugin

    def __init__(
        self,
        *,
        plan: 'tmt.base.core.Plan',
        data: tmt.steps.RawStepDataArgument,
        logger: tmt.log.Logger,
    ) -> None:
        """
        Store supported attributes, check for sanity
        """

        super().__init__(plan=plan, data=data, logger=logger)

        # Collection of discovered tests
        self._tests: dict[str, list[tmt.Test]] = {}
        self._failed_tests: dict[str, list[tmt.Test]] = {}

        # Collection of required tests per discover step phase
        self._required_test_names: dict[str, list[str]] = {}

        # Test will be (re)discovered in other phases/steps
        self.extract_tests_later: bool = False

    @property
    def loaded_from_recipe(self) -> bool:
        """
        Whether this plan run was loaded from a recipe.
        """
        return self.plan.my_run is not None and self.plan.my_run.recipe is not None

    @property
    def _preserved_workdir_members(self) -> set[str]:
        """
        A set of members of the step workdir that should not be removed.
        """

        return {*super()._preserved_workdir_members, 'tests.yaml'}

    @property
    def required_tests(self) -> list[TestOrigin]:
        """
        The list of required tests gathered from all phases
        """

        tests = []
        for phase_name, required_test_names in self._required_test_names.items():
            tests += [
                test_origin
                for test_origin in self.tests(phase_name=phase_name)
                if test_origin.test.name in required_test_names
            ]
        return tests

    def discover_tests(
        self, phase: DiscoverPlugin[DiscoverStepData], logger: Optional[tmt.log.Logger] = None
    ) -> None:
        """
        Discover tests using the given phase.
        """
        path = phase.fetch_source()
        phase.checkout_ref()

        # Go and discover tests
        if self.loaded_from_recipe:
            phase.discover_from_recipe(logger=logger)
        else:
            phase.go(path=path, logger=logger)

        if phase.get('prune', False):
            clone_dir = phase.clone_dirpath / 'tests'
            phase.install_libraries(phase.test_dir, clone_dir)
            phase.prune_tree(clone_dir, path)
        else:
            phase.install_libraries(phase.test_dir, phase.test_dir)

        if not self.loaded_from_recipe:
            phase.adjust_test_attributes(path)

        phase.apply_policies()

    @property
    def dependencies_to_tests(self) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
        """
        A tuple containing two dictionaries mapping dependencies to tests (required & recommended)
        """

        required_dependencies_to_tests: dict[str, list[str]] = defaultdict(list)
        recommended_dependencies_to_tests: dict[str, list[str]] = defaultdict(list)

        def _normalize_dependency_name(dependency: tmt.base.Dependency) -> str:
            """
            Handles debuginfo dependencies by removing the '-debuginfo' suffix.
            Such dependencies are installed by their base name.
            """
            dependency_name = str(dependency)
            return (
                dependency_name.removesuffix('-debuginfo')
                if dependency_name.endswith('-debuginfo')
                else dependency_name
            )

        for test_origin in self.tests(enabled=True):
            test = test_origin.test
            test_name = test.name
            # Collect dependencies separately for required and recommended
            for dependency in test.require:
                required_dependencies_to_tests[_normalize_dependency_name(dependency)].append(
                    test_name
                )
            for dependency in test.recommend:
                recommended_dependencies_to_tests[_normalize_dependency_name(dependency)].append(
                    test_name
                )

        return required_dependencies_to_tests, recommended_dependencies_to_tests

    def load(self) -> None:
        """
        Load step data from the workdir
        """

        if self.should_run_again:
            self.debug('Run discover again when reexecuting to capture changes in plans')
        else:
            super().load()

        try:
            raw_test_data: list[tmt.export._RawExportedInstance] = tmt.utils.yaml_to_list(
                self.read(Path('tests.yaml'))
            )

            self._tests = {}

            for raw_test_datum in raw_test_data:
                # The name of `discover` phases providing the test was added in 1.24.
                # Unfortunately, the field is required for correct work of `execute`,
                # now when it is parallel in nature. Without it, it's not possible
                # to pick the right `discover` phase which then provides the list
                # of tests to execute. Therefore raising an error instead of guessing
                # what the phase could be.
                if key_to_option('discover_phase') not in raw_test_datum:
                    # TODO: there should be a method for creating workdir-aware paths...
                    path = (
                        self.workdir / Path('tests.yaml') if self.workdir else Path('tests.yaml')
                    )

                    raise tmt.utils.BackwardIncompatibleDataError(
                        f"Could not load '{path}' whose format is not compatible "
                        "with tmt 1.24 and newer."
                    )

                phase_name = raw_test_datum.pop(key_to_option('discover_phase'))

                if phase_name not in self._tests:
                    self._tests[phase_name] = []

                self._tests[phase_name].append(
                    tmt.Test.from_dict(
                        logger=self._logger,
                        mapping=raw_test_datum,
                        name=raw_test_datum['name'],
                        skip_validation=True,
                    )
                )

        except tmt.utils.FileError:
            self.debug('Discovered tests not found.', level=2)

    def save(self) -> None:
        """
        Save step data to the workdir
        """

        super().save()

        # Create tests.yaml with the full test data
        raw_test_data: list[tmt.export._RawExportedInstance] = []

        for phase_name, phase_tests in self._tests.items():
            for test in phase_tests:
                if test.enabled is not True:
                    continue

                exported_test = test._export(include_internal=True)
                exported_test[key_to_option('discover_phase')] = phase_name

                raw_test_data.append(exported_test)

        self.write(Path('tests.yaml'), tmt.utils.to_yaml(raw_test_data))

    def _discover_from_execute(self) -> None:
        """
        Check the execute step for possible shell script tests
        """

        # Check scripts for command line and data, convert to list if needed
        scripts = self.plan.execute.opt('script')
        if not scripts:
            scripts = getattr(self.plan.execute.data[0], 'script', [])
        if not scripts:
            return
        if isinstance(scripts, str):
            scripts = [scripts]

        # Avoid circular imports
        from tmt.steps.discover.shell import DiscoverShellData, TestDescription

        # Give a warning when discover step defined as well
        if self.data and not all(datum.is_bare for datum in self.data):
            raise tmt.utils.DiscoverError(
                "Use either 'discover' or 'execute' step to define tests, but not both."
            )

        if not isinstance(self.data[0], DiscoverShellData):
            # TODO: or should we rather create a new `shell` discovery step data,
            # and fill it with our tests? Before step data patch, `tests` attribute
            # was simply created as a list, with no check whether the step data and
            # plugin even support `data.tests`. Which e.g. `internal` does not.
            # Or should we find the first DiscoverShellData instance, use it, and
            # create a new one when no such entry exists yet?
            raise GeneralError(
                f'Cannot append tests from execute to non-shell step "{self.data[0].how}"'
            )

        discover_step_data = self.data[0]

        # Check the execute step for possible custom duration limit
        # FIXME: cast() - https://github.com/teemtee/tmt/issues/1540
        duration = cast(
            str,
            getattr(self.plan.execute.data[0], 'duration', tmt.base.core.DEFAULT_TEST_DURATION_L2),
        )

        # Prepare the list of tests
        for index, script in enumerate(scripts):
            name = f'script-{str(index).zfill(2)}'
            discover_step_data.tests.append(
                TestDescription(name=name, test=script, duration=duration)
            )

    def wake(self) -> None:
        """
        Wake up the step (process workdir and command line)
        """

        super().wake()

        # Check execute step for possible tests (unless already done)
        if self.status() is None:
            self._discover_from_execute()

        # Choose the right plugin and wake it up
        for data in self.data:
            # FIXME: cast() - see https://github.com/teemtee/tmt/issues/1599
            plugin = cast(
                DiscoverPlugin[DiscoverStepData], DiscoverPlugin.delegate(self, data=data)
            )
            self._phases.append(plugin)
            plugin.wake()

        # Nothing more to do if already done and not asked to run again
        if self.status() == 'done' and not self.should_run_again:
            self.debug('Discover wake up complete (already done before).', level=2)
        # Save status and step data (now we know what to do)
        else:
            self.status('todo')
            self.save()

    def summary(self) -> None:
        """
        Give a concise summary of the discovery
        """

        # Summary of selected tests
        text = listed(len(self.tests(enabled=True)), 'test') + ' selected'
        self.info('summary', text, 'green', shift=1)
        # Test list in verbose mode
        for test_origin in self.tests(enabled=True):
            self.verbose(test_origin.test.name, color='red', shift=2)

    def go(self, force: bool = False) -> None:
        """
        Discover all tests
        """

        super().go(force=force)

        # Nothing more to do if already done
        if self.status() == 'done':
            self.info('status', 'done', 'green', shift=1)
            self.summary()
            self.actions()
            return

        # Perform test discovery, gather discovered tests
        for phase in self.phases(classes=(Action, DiscoverPlugin)):
            if isinstance(phase, Action):
                phase.go()

            elif isinstance(phase, DiscoverPlugin):
                if not phase.enabled_by_when:
                    continue

                self.discover_tests(phase)

                prefix = f'/{phase.name}' if len(self.phases()) > 1 else ''

                if not self.loaded_from_recipe:
                    phase.apply_phase_prefix(prefix)

                self._tests[phase.name] = [
                    test_origin.test for test_origin in phase.tests(enabled=True)
                ]

                self._required_test_names[phase.name] = [
                    f"{prefix}{test_name}"
                    for test_name in cast(DiscoverStepData, phase.data).require_test
                ]

            else:
                raise GeneralError(f'Unexpected phase in discover step: {phase}')

        for test_origin in self.tests():
            test_origin.test.serial_number = self.plan.draw_test_serial_number(test_origin.test)

        # Show fmf identifiers for tests discovered in plan
        # TODO: This part should go into the 'fmf.py' module
        if self.opt('fmf_id'):
            if self.tests(enabled=True):
                export_fmf_ids: list[str] = []

                for test_origin in self.tests(enabled=True):
                    fmf_id = test_origin.test.fmf_id

                    if not fmf_id.url:
                        raise tmt.utils.DiscoverError(
                            f"`tmt run discover --fmf-id` without `url` option "
                            f"in plan `{self.plan}` can be used only within git repo."
                        )

                    exported = test_origin.test.fmf_id.to_minimal_spec()

                    if fmf_id.default_branch and fmf_id.ref == fmf_id.default_branch:
                        exported.pop('ref')

                    export_fmf_ids.append(tmt.utils.to_yaml(exported, start=True))

                click.echo(''.join(export_fmf_ids), nl=False)
            return

        if self.should_run_again and tmt.base.core.Test._opt('failed_only'):
            failed_results: list[tmt.base.core.Result] = []
            assert self.parent is not None  # narrow type
            assert isinstance(self.parent, tmt.base.core.Plan)  # narrow type

            # Get failed results from previous run execute
            failed_results = [
                result
                for result in self.parent.execute._results
                if (
                    result.result is not tmt.result.ResultOutcome.PASS
                    and result.result is not tmt.result.ResultOutcome.INFO
                )
            ]

            # Filter existing tests into another variable which is then used by tests() method
            for test_phase in self._tests:
                self._failed_tests[test_phase] = []
                for test in self._tests[test_phase]:
                    for result in failed_results:
                        if test.name == result.name and test.serial_number == result.serial_number:
                            self._failed_tests[test_phase].append(test)

        # Assert that all required tests were discovered
        for phase_name, required_test_names in self._required_test_names.items():
            for required_test in required_test_names:
                if not any(required_test == test.name for test in self._tests.get(phase_name, [])):
                    raise tmt.utils.DiscoverError(
                        f"Required test '{required_test}' not discovered in phase '{phase_name}'."
                    )

        # Give a summary, update status and save
        self.summary()
        self.status('done')
        self.save()

    def tests(
        self, *, phase_name: Optional[str] = None, enabled: Optional[bool] = None
    ) -> list['TestOrigin']:
        """
        Return discovered tests.

        :param phase_name: if set, return only tests discovered by the
            phase of this name. Otherwise, tests discovered by all
            phases are returned.
        :param enabled: if set, return only tests that are enabled
            (``enabled=True``) or disabled (``enabled=False``). Otherwise,
            all tests are returned.
        :returns: a list of phase name and test pairs.
        """

        from tmt.steps.discover import TestOrigin

        suitable_tests = self._failed_tests or self._tests
        suitable_phases = [phase_name] if phase_name is not None else list(self._tests.keys())

        def _iter_tests() -> Iterator['TestOrigin']:
            # PLR1704: this redefinition of `phase_name` is acceptable, the original
            # value is not longer needed as it has been turned into `suitable_phases`.
            for phase_name, phase_tests in suitable_tests.items():  # noqa: PLR1704
                if phase_name not in suitable_phases:
                    continue

                for test in phase_tests:
                    yield TestOrigin(test=test, phase=phase_name)

        if enabled is None:
            return list(_iter_tests())

        return [
            test_origin for test_origin in _iter_tests() if test_origin.test.enabled is enabled
        ]
