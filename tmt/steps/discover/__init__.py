import dataclasses
from typing import TYPE_CHECKING, Any, Dict, Generator, List, Optional, Type, cast

import click
from fmf.utils import listed

import tmt

if TYPE_CHECKING:
    import tmt.cli
    import tmt.options
    import tmt.steps

import tmt.base
import tmt.steps
import tmt.utils
from tmt.options import option
from tmt.plugins import PluginRegistry
from tmt.steps import Action
from tmt.utils import Command, GeneralError, Path, flatten


@dataclasses.dataclass
class DiscoverStepData(tmt.steps.WhereableStepData, tmt.steps.StepData):
    dist_git_source: bool = tmt.utils.field(
        default=False,
        option='--dist-git-source',
        is_flag=True,
        help='Extract DistGit sources.'
        )

    # TODO: use enum!
    dist_git_type: Optional[str] = tmt.utils.field(
        default=None,
        option='--dist-git-type',
        choices=tmt.utils.get_distgit_handler_names,
        help='Use the provided DistGit handler instead of the auto detection.'
        )


class DiscoverPlugin(tmt.steps.GuestlessPlugin):
    """ Common parent of discover plugins """

    _data_class = DiscoverStepData

    # Methods ("how: ..." implementations) registered for the same step.
    _supported_methods: PluginRegistry[tmt.steps.Method] = PluginRegistry()

    @classmethod
    def base_command(
            cls,
            usage: str,
            method_class: Optional[Type[click.Command]] = None) -> click.Command:
        """ Create base click command (common for all discover plugins) """

        # Prepare general usage message for the step
        if method_class:
            usage = Discover.usage(method_overview=usage)

        # Create the command
        @click.command(cls=method_class, help=usage)
        @click.pass_context
        @option(
            '-h', '--how', metavar='METHOD',
            help='Use specified method to discover tests.')
        @tmt.steps.PHASE_OPTIONS
        def discover(context: 'tmt.cli.Context', **kwargs: Any) -> None:
            context.obj.steps.add('discover')
            Discover.store_cli_invocation(context)

        return discover

    def tests(
            self,
            *,
            phase_name: Optional[str] = None,
            enabled: Optional[bool] = None) -> List['tmt.Test']:
        """
        Return discovered tests

        Each DiscoverPlugin has to implement this method.
        Should return a list of Test() objects.
        """
        raise NotImplementedError

    def extract_distgit_source(
            self, distgit_dir: Path, target_dir: Path, handler_name: Optional[str] = None) -> None:
        """
        Extract source tarball into target_dir

        distgit_dir is path to the DistGit repository.
        Source tarball is discovered from the 'sources' file content.
        """
        if handler_name is None:
            output = self.run(
                Command("git", "config", "--get-regexp", '^remote\\..*.url'),
                cwd=distgit_dir)
            if output.stdout is None:
                raise tmt.utils.GeneralError("Missing remote origin url.")

            remotes = output.stdout.split('\n')
            handler = tmt.utils.get_distgit_handler(remotes=remotes)
        else:
            handler = tmt.utils.get_distgit_handler(usage_name=handler_name)
        for url, source_name in handler.url_and_name(distgit_dir):
            if not handler.re_supported_extensions.search(source_name):
                continue
            self.debug(f"Download sources from '{url}'.")
            with tmt.utils.retry_session() as session:
                response = session.get(url)
            response.raise_for_status()
            target_dir.mkdir(exist_ok=True, parents=True)
            with open(target_dir / source_name, 'wb') as tarball:
                tarball.write(response.content)
            self.run(
                Command("tar", "--auto-compress", "--extract", "-f", source_name),
                cwd=target_dir)

    def log_import_plan_details(self) -> None:
        """
        Log details about the imported plan
        """
        parent = cast(Optional[tmt.steps.discover.Discover], self.parent)
        if parent and parent.plan._original_plan and \
                parent.plan._original_plan._remote_plan_fmf_id:
            remote_plan_id = parent.plan._original_plan._remote_plan_fmf_id
            # FIXME: cast() - https://github.com/python/mypy/issues/7981
            # Note the missing Optional for values - to_minimal_dict() would
            # not include unset keys, therefore all values should be valid.
            for key, value in cast(Dict[str, str], remote_plan_id.to_minimal_spec()).items():
                self.verbose(f'import {key}', value, 'green')


class Discover(tmt.steps.Step):
    """ Gather information about test cases to be executed. """

    _plugin_base_class = DiscoverPlugin
    _preserved_workdir_members = ['step.yaml', 'tests.yaml']

    def __init__(
            self,
            *,
            plan: 'tmt.base.Plan',
            data: tmt.steps.RawStepDataArgument,
            logger: tmt.log.Logger) -> None:
        """ Store supported attributes, check for sanity """
        super().__init__(plan=plan, data=data, logger=logger)

        # Collection of discovered tests
        self._tests: Dict[str, List[tmt.Test]] = {}

    def load(self) -> None:
        """ Load step data from the workdir """
        super().load()
        try:
            raw_test_data = tmt.utils.yaml_to_list(self.read(Path('tests.yaml')))

            self._tests = {}

            for raw_test_datum in raw_test_data:
                phase_name = raw_test_datum.pop('discover_phase')

                if phase_name not in self._tests:
                    self._tests[phase_name] = []

                self._tests[phase_name].append(tmt.Test.from_dict(
                    logger=self._logger,
                    mapping=raw_test_datum,
                    name=raw_test_datum['name'],
                    skip_validation=True))

        except tmt.utils.FileError:
            self.debug('Discovered tests not found.', level=2)

    def save(self) -> None:
        """ Save step data to the workdir """
        super().save()

        # Create tests.yaml with the full test data
        raw_test_data: List['tmt.export._RawExportedInstance'] = []

        for phase_name, phase_tests in self._tests.items():
            for test in phase_tests:
                if test.enabled is not True:
                    continue

                exported_test = test._export()
                exported_test['discover_phase'] = phase_name

                raw_test_data.append(exported_test)

        self.write(Path('tests.yaml'), tmt.utils.dict_to_yaml(raw_test_data))

    def _discover_from_execute(self) -> None:
        """ Check the execute step for possible shell script tests """

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
                "Use either 'discover' or 'execute' step "
                "to define tests, but not both.")

        if not isinstance(self.data[0], DiscoverShellData):
            # TODO: or should we rather create a new `shell` discovery step data,
            # and fill it with our tests? Before step data patch, `tests` attribute
            # was simply created as a list, with no check whether the step data and
            # plugin even support `data.tests`. Which e.g. `internal` does not.
            # Or should we find the first DiscoverShellData instance, use it, and
            # create a new one when no such entry exists yet?
            raise GeneralError(
                f'Cannot append tests from execute to non-shell step "{self.data[0].how}"')

        discover_step_data = self.data[0]

        # Check the execute step for possible custom duration limit
        # FIXME: cast() - https://github.com/teemtee/tmt/issues/1540
        duration = cast(
            str,
            getattr(
                self.plan.execute.data[0],
                'duration',
                tmt.base.DEFAULT_TEST_DURATION_L2))

        # Prepare the list of tests
        for index, script in enumerate(scripts):
            name = f'script-{str(index).zfill(2)}'
            discover_step_data.tests.append(
                TestDescription(name=name, test=script, duration=duration)
                )

    def wake(self) -> None:
        """ Wake up the step (process workdir and command line) """
        super().wake()

        # Check execute step for possible tests (unless already done)
        if self.status() is None:
            self._discover_from_execute()

        # Choose the right plugin and wake it up
        for data in self.data:
            # FIXME: cast() - see https://github.com/teemtee/tmt/issues/1599
            plugin = cast(DiscoverPlugin, DiscoverPlugin.delegate(self, data=data))
            self._phases.append(plugin)
            plugin.wake()

        # Nothing more to do if already done
        if self.status() == 'done':
            self.debug(
                'Discover wake up complete (already done before).', level=2)
        # Save status and step data (now we know what to do)
        else:
            self.status('todo')
            self.save()

    def summary(self) -> None:
        """ Give a concise summary of the discovery """
        # Summary of selected tests
        text = listed(len(self.tests(enabled=True)), 'test') + ' selected'
        self.info('summary', text, 'green', shift=1)
        # Test list in verbose mode
        for test in self.tests(enabled=True):
            self.verbose(test.name, color='red', shift=2)

    def go(self) -> None:
        """ Execute all steps """
        super().go()

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
                # Go and discover tests
                phase.go()

                self._tests[phase.name] = []

                # Prefix test name only if multiple plugins configured
                prefix = f'/{phase.name}' if len(self.phases()) > 1 else ''
                # Check discovered tests, modify test name/path
                for test in phase.tests(enabled=True):
                    test.name = f"{prefix}{test.name}"
                    test.path = Path(f"/{phase.safe_name}{test.path}")
                    # Update test environment with plan environment
                    test.environment.update(self.plan.environment)
                    self._tests[phase.name].append(test)

            else:
                raise GeneralError(f'Unexpected phase in discover step: {phase}')

        for test in self.tests():
            test.serialnumber = self.plan.draw_test_serial_number(test)

        # Show fmf identifiers for tests discovered in plan
        # TODO: This part should go into the 'fmf.py' module
        if self.opt('fmf_id'):
            if self.tests(enabled=True):
                export_fmf_ids: List[str] = []

                for test in self.tests(enabled=True):
                    fmf_id = test.fmf_id

                    if not fmf_id.url:
                        continue

                    exported = test.fmf_id.to_minimal_spec()

                    if fmf_id.default_branch and fmf_id.ref == fmf_id.default_branch:
                        exported.pop('ref')

                    export_fmf_ids.append(tmt.utils.dict_to_yaml(exported, start=True))

                click.echo(''.join(export_fmf_ids), nl=False)
            return

        # Give a summary, update status and save
        self.summary()
        self.status('done')
        self.save()

    def tests(
            self,
            *,
            phase_name: Optional[str] = None,
            enabled: Optional[bool] = None) -> List['tmt.Test']:
        def _iter_all_tests() -> Generator['tmt.Test', None, None]:
            for phase_tests in self._tests.values():
                yield from phase_tests

        def _iter_phase_tests() -> Generator['tmt.Test', None, None]:
            assert phase_name is not None

            yield from self._tests[phase_name]

        iterator = _iter_all_tests if phase_name is None else _iter_phase_tests

        if enabled is None:
            return list(iterator())

        return [test for test in iterator() if test.enabled is enabled]

    def requires(self) -> List['tmt.base.Dependency']:
        """
        Collect all test requirements of all discovered tests in this step.

        Puts together a list of requirements which need to be installed on the
        provisioned guest so that all discovered tests of this step can be
        successfully executed.

        :returns: a list of requirements, with duplicaties removed.
        """
        return flatten((test.require for test in self.tests(enabled=True)), unique=True)

    def recommends(self) -> List['tmt.base.Dependency']:
        """ Return all packages recommended by tests """
        return flatten((test.recommend for test in self.tests(enabled=True)), unique=True)
