import copy
import dataclasses
import shutil
from typing import Any, Dict, List, Optional, Type, TypeVar, cast

import click
import fmf

import tmt
import tmt.base
import tmt.log
import tmt.steps
import tmt.steps.discover
import tmt.utils
from tmt.utils import Command, Path, ShellScript, field

T = TypeVar('T', bound='TestDescription')


@dataclasses.dataclass
class TestDescription(
        tmt.utils.SpecBasedContainer,
        tmt.utils.NormalizeKeysMixin,
        tmt.utils.SerializableContainer):
    """
    Keys necessary to describe a shell-based test.

    Provides basic functionality for tansition between "raw" step data representation,
    which consists of keys and values given by fmf tree and CLI options, and this
    container representation for internal use.
    """

    name: str

    # TODO: following keys are copy & pasted from base.Test. It would be much, much better
    # to re-use the definitions from base.Test instead copying them here, but base.Test
    # does not support save/load operations. This is a known issue, introduced by a patch
    # transitioning step data to data classes, it is temporary, and it will be fixed as
    # soon as possible - nobody want's to keep two very same lists of attributes.
    test: ShellScript = field(
        default=ShellScript(''),
        normalize=lambda key_address, raw_value, logger: ShellScript(raw_value),
        serialize=lambda test: str(test),
        unserialize=lambda serialized_test: ShellScript(serialized_test)
        )

    # Core attributes (supported across all levels)
    summary: Optional[str] = None
    description: Optional[str] = None
    enabled: bool = True
    order: int = field(
        # TODO: ugly circular dependency (see tmt.base.DEFAULT_ORDER)
        default=50,
        normalize=lambda key_address, raw_value, logger:
            50 if raw_value is None else int(raw_value)
        )
    link: Optional[tmt.base.Links] = field(
        default=None,
        normalize=lambda key_address, raw_value, logger: tmt.base.Links(data=raw_value),
        # Using `to_spec()` on purpose: `Links` does not provide serialization
        # methods, because specification of links is already good enough. We
        # can use existing `to_spec()` method, and undo it with a simple
        # `Links(...)` call.
        #
        # ignore[attr-defined]: mypy reports `to_spec` to be an unknown attribute,
        # but reveal_type() reports `link` to be a known type, not Any, and it's
        # not clear why would mypy misread the situation.
        serialize=lambda link: link.to_spec() if link else None,  # type: ignore[attr-defined]
        unserialize=lambda serialized_link: tmt.base.Links(data=serialized_link)
        )
    id: Optional[str] = None
    tag: List[str] = field(
        default_factory=list,
        normalize=tmt.utils.normalize_string_list
        )
    tier: Optional[str] = field(
        default=None,
        normalize=lambda key_address, raw_value, logger:
            None if raw_value is None else str(raw_value)
        )
    adjust: Optional[List[tmt.base._RawAdjustRule]] = field(
        default=None,
        normalize=lambda key_address, raw_value, logger: [] if raw_value is None else (
            [raw_value] if not isinstance(raw_value, list) else raw_value
            )
        )

    # Basic test information
    contact: List[str] = field(
        default_factory=list,
        normalize=tmt.utils.normalize_string_list
        )
    component: List[str] = field(
        default_factory=list,
        normalize=tmt.utils.normalize_string_list
        )

    # Test execution data
    path: Optional[str] = None
    framework: Optional[str] = None
    manual: bool = False
    require: List[tmt.base.Dependency] = field(
        default_factory=list,
        normalize=tmt.base.normalize_require,
        serialize=lambda requires: [require.to_spec() for require in requires],
        unserialize=lambda serialized_requires: [
            tmt.base.dependency_factory(require) for require in serialized_requires
            ]
        )
    recommend: List[tmt.base.Dependency] = field(
        default_factory=list,
        normalize=tmt.base.normalize_require,
        serialize=lambda recommends: [recommend.to_spec() for recommend in recommends],
        unserialize=lambda serialized_recommends: [
            tmt.base.DependencySimple.from_spec(recommend)
            if isinstance(recommend, str) else tmt.base.DependencyFmfId.from_spec(recommend)
            for recommend in serialized_recommends
            ]
        )
    environment: tmt.utils.EnvironmentType = field(default_factory=dict)
    duration: str = '1h'
    result: str = 'respect'

    # ignore[override]: expected, we do want to accept more specific
    # type than the one declared in superclass.
    @classmethod
    def from_spec(  # type: ignore[override]
            cls: Type[T],
            raw_data: Dict[str, Any],
            logger: tmt.log.Logger) -> T:
        """ Convert from a specification file or from a CLI option """

        data = cls(name=raw_data['name'], test=raw_data['test'])
        data._load_keys(raw_data, cls.__name__, logger)

        return data

    def to_spec(self) -> Dict[str, Any]:
        """ Convert to a form suitable for saving in a specification file """

        data = super().to_spec()
        data['link'] = self.link.to_spec() if self.link else None
        data['require'] = [require.to_spec() for require in self.require]
        data['recommend'] = [recommend.to_spec() for recommend in self.recommend]
        data['test'] = str(self.test)

        return data


@dataclasses.dataclass
class DiscoverShellData(tmt.steps.discover.DiscoverStepData):
    tests: List[TestDescription] = field(
        default_factory=list,
        normalize=lambda key_address, raw_value, logger: [
            TestDescription.from_spec(raw_datum, logger)
            for raw_datum in cast(List[Dict[str, Any]], raw_value)
            ],
        serialize=lambda tests: [
            test.to_serialized()
            for test in tests
            ],
        unserialize=lambda serialized_tests: [
            TestDescription.from_serialized(serialized_test)
            for serialized_test in serialized_tests
            ]
        )

    url: Optional[str] = tmt.utils.field(
        option="--url",
        metavar='REPOSITORY',
        default=None,
        help="URL of the git repository with tests to be fetched.")

    ref: Optional[str] = tmt.utils.field(
        option="--ref",
        metavar='REVISION',
        default=None,
        help="Branch, tag or commit specifying the git revision.")

    keep_git_metadata: Optional[bool] = tmt.utils.field(
        option="--keep-git-metadata",
        is_flag=True,
        default=False,
        help="Keep the git metadata if a repo is synced to guest.")


@tmt.steps.provides_method('shell')
class DiscoverShell(tmt.steps.discover.DiscoverPlugin):
    """
    Use provided list of shell script tests

    List of test cases to be executed can be defined manually directly
    in the plan as a list of dictionaries containing test name, actual
    test script and optionally a path to the test. Example config:

    discover:
        how: shell
        tests:
        - name: /help/main
          test: tmt --help
        - name: /help/test
          test: tmt test --help
        - name: /help/smoke
          test: ./smoke.sh
          path: /tests/shell

    For DistGit repo one can extract source tarball and use its code.
    It is extracted to TMT_SOURCE_DIR however no patches are applied
    (only source tarball is extracted).

    discover:
        how: shell
        dist-git-source: true
        tests:
        - name: /upstream
          test: cd $TMT_SOURCE_DIR/*/tests && make test

    To clone a remote repository and use it as a source specify `url`.
    It accepts also `ref` to checkout provided reference. Dynamic
    reference feature is supported as well.

    discover:
        how: shell
        url: https://github.com/teemtee/tmt.git
        ref: "1.18.0"
        tests:
        - name: first test
          test: ./script-from-the-repo.sh
    """

    _data_class = DiscoverShellData

    _tests: List[tmt.base.Test] = []

    def show(self, keys: Optional[List[str]] = None) -> None:
        """ Show config details """
        super().show([])
        # FIXME: cast() - typeless "dispatcher" method
        tests = cast(List[TestDescription], self.get('tests'))
        if tests:
            test_names = [test.name for test in tests]
            click.echo(tmt.utils.format('tests', test_names))

    def fetch_remote_repository(
            self, url: Optional[str], ref: Optional[str], testdir: Path) -> None:
        """ Fetch remote git repo from given url to testdir """
        # Nothing to do if no url provided
        if not url:
            return

        # Clone first - it might clone dist git
        self.info('url', url, 'green')
        tmt.utils.git_clone(
            url=url,
            destination=testdir,
            common=self,
            env={"GIT_ASKPASS": "echo"},
            shallow=ref is None)

        # Resolve possible dynamic references
        try:
            ref = tmt.base.resolve_dynamic_ref(
                logger=self._logger,
                workdir=testdir,
                ref=ref,
                plan=self.step.plan)
        except tmt.utils.FileError as error:
            raise tmt.utils.DiscoverError(str(error))

        # Checkout revision if requested
        if ref:
            self.info('ref', ref, 'green')
            self.debug(f"Checkout ref '{ref}'.")
            self.run(Command('git', 'checkout', '-f', str(ref)), cwd=testdir)

        # Remove .git so that it's not copied to the SUT
        # if 'keep-git-metadata' option is not specified
        if not self.get('keep_git_metadata', False):
            shutil.rmtree(testdir / '.git')

    def go(self) -> None:
        """ Discover available tests """
        super(DiscoverShell, self).go()
        tests = fmf.Tree(dict(summary='tests'))

        assert self.workdir is not None
        testdir = self.workdir / "tests"

        # Fetch remote repository
        url = self.get('url', None)
        ref = self.get('ref', None)
        self.fetch_remote_repository(url, ref, testdir)

        # dist-git related
        sourcedir = self.workdir / 'source'
        dist_git_source = self.get('dist-git-source', False)

        # Check and process each defined shell test
        # FIXME: cast() - https://github.com/teemtee/tmt/issues/1540
        for data in cast(DiscoverShellData, self.data).tests:
            # Create data copy (we want to keep original data for save()
            data = copy.deepcopy(data)
            # Extract name, make sure it is present
            # TODO: can this ever happen? With annotations, `name: str` and `test: str`, nothing
            # should ever assign `None` there and pass the test.
            if not data.name:
                raise tmt.utils.SpecificationError(
                    f"Missing test name in '{self.step.plan.name}'.")
            # Make sure that the test script is defined
            if not data.test:
                raise tmt.utils.SpecificationError(
                    f"Missing test script in '{self.step.plan.name}'.")
            # Prepare path to the test working directory (tree root by default)
            data.path = f"/tests{data.path}" if data.path else '/tests'
            # Apply default test duration unless provided
            if not data.duration:
                data.duration = tmt.base.DEFAULT_TEST_DURATION_L2
            # Add source dir path variable
            if dist_git_source:
                data.environment['TMT_SOURCE_DIR'] = str(sourcedir)

            # Create a simple fmf node, with correct name. Emit only keys and values
            # that are no longer default. Do not add `name` itself into the node,
            # it's not a supported test key, and it's given to the node itself anyway.
            # Note the exception for `duration` key - it's expected in the output
            # even if it still has its default value.
            test_fmf_keys: Dict[str, Any] = {
                key: value
                for key, value in data.to_spec().items()
                if key != 'name' and (key == 'duration' or value != data.default(key))
                }
            tests.child(data.name, test_fmf_keys)

        # Symlink tests directory to the plan work tree
        # (unless remote repository is provided using 'url')
        if not url:
            assert self.step.plan.worktree  # narrow type

            relative_path = self.step.plan.worktree.relative_to(self.workdir)
            testdir.symlink_to(relative_path)

        if dist_git_source:
            assert self.step.plan.my_run is not None  # narrow type
            assert self.step.plan.my_run.tree is not None  # narrow type
            assert self.step.plan.my_run.tree.root is not None  # narrow type
            try:
                run_result = self.run(
                    Command("git", "rev-parse", "--show-toplevel"),
                    cwd=self.step.plan.my_run.tree.root,
                    ignore_dry=True)[0]
                assert run_result is not None
                git_root = Path(run_result.strip('\n'))
            except tmt.utils.RunError:
                assert self.step.plan.my_run is not None  # narrow type
                assert self.step.plan.my_run.tree is not None  # narrow type
                raise tmt.utils.DiscoverError(
                    f"Directory '{self.step.plan.my_run.tree.root}' "
                    f"is not a git repository.")
            try:
                self.extract_distgit_source(
                    git_root, sourcedir, self.get('dist-git-type'))
            except Exception as error:
                raise tmt.utils.DiscoverError(
                    "Failed to process 'dist-git-source'.") from error

        # Use a tmt.Tree to apply possible command line filters
        self._tests = tmt.Tree(
            logger=self._logger,
            tree=tests).tests(
            conditions=["manual is False"])

        # Propagate `where` key
        for test in self._tests:
            test.where = cast(tmt.steps.discover.DiscoverStepData, self.data).where

    def tests(
            self,
            *,
            phase_name: Optional[str] = None,
            enabled: Optional[bool] = None) -> List['tmt.Test']:

        if phase_name is not None and phase_name != self.name:
            return []

        if enabled is None:
            return self._tests

        return [test for test in self._tests if test.enabled is enabled]
