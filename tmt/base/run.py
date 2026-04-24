import functools
import os
import re
import shutil
import sys
import time
from collections.abc import Iterable, Sequence
from typing import (
    TYPE_CHECKING,
    Any,
    ClassVar,
    Optional,
    cast,
)

import fmf
import fmf.utils

import tmt.config
import tmt.log
import tmt.policy
import tmt.result
import tmt.steps
import tmt.steps.cleanup
import tmt.steps.execute
import tmt.steps.finish
import tmt.steps.prepare
import tmt.steps.provision
import tmt.steps.scripts
import tmt.templates
import tmt.utils
from tmt.base.core import Tree
from tmt.container import (
    SerializableContainer,
    container,
    field,
)
from tmt.recipe import RecipeManager
from tmt.result import Result
from tmt.utils import (
    Command,
    Environment,
    GeneralError,
    HasEnvironment,
    HasRunWorkdir,
    Path,
    StateFormat,
    WorkdirArgumentType,
)

if TYPE_CHECKING:
    import tmt.cli
    import tmt.steps.provision.local
    from tmt.base.plan import Plan

# How many already existing lines should tmt run --follow show
FOLLOW_LINES = 10


@container
class RunData(SerializableContainer):
    root: Optional[str]
    plans: Optional[list[str]]
    # TODO: this needs resolution - _context_object.steps is List[Step],
    # but stores as a List[str] in run.yaml...
    steps: list[str]
    remove: bool

    #: Stores the environment supplied via CLI over all uses of this
    #: workdir. CLI options provided to subsequent ``tmt run``
    #: invocations are added into this set.
    environment: Environment = field(
        default_factory=Environment,
        serialize=lambda environment: environment.to_fmf_spec(),
        unserialize=lambda serialized: tmt.utils.Environment.from_fmf_spec(serialized),
    )


class Run(HasRunWorkdir, HasEnvironment, tmt.utils.Common):
    """
    Test run, a container of plans
    """

    tree: Optional[Tree]

    #: Run policies to apply to tests, plans and stories.
    policies: list[tmt.policy.Policy]

    data: Optional[RunData] = None

    WARNINGS_FILE_NAME: ClassVar[str] = "warnings.yaml"

    def __init__(
        self,
        *,
        id_: Optional[Path] = None,
        tree: Optional[Tree] = None,
        cli_invocation: Optional['tmt.cli.CliInvocation'] = None,
        parent: Optional[tmt.utils.Common] = None,
        workdir_root: Optional[Path] = None,
        policies: Optional[list[tmt.policy.Policy]] = None,
        recipe_path: Optional[Path] = None,
        logger: tmt.log.Logger,
    ) -> None:
        """
        Initialize tree, workdir and plans
        """
        # Use the last run id if requested
        self.config = tmt.config.Config(logger)

        if cli_invocation is not None:
            if cli_invocation.options.get('last'):
                id_ = self.config.last_run
                if id_ is None:
                    raise tmt.utils.GeneralError(
                        "No last run id found. Have you executed any run?"
                    )
            if id_ is None:
                id_required_options = ('follow', 'again')
                for option in id_required_options:
                    if cli_invocation.options.get(option):
                        raise tmt.utils.GeneralError(
                            f"Run id has to be specified in order to use --{option}."
                        )
        # Do not create workdir now, postpone it until later, as options
        # have not been processed yet and we do not want commands such as
        # tmt run discover --how fmf --help to create a new workdir.
        super().__init__(
            cli_invocation=cli_invocation, logger=logger, parent=parent, workdir_root=workdir_root
        )
        self._workdir_path: WorkdirArgumentType = id_ or True
        self._tree: Optional[Tree] = tree
        self._plans: Optional[list[Plan]] = None
        self.remove = self.opt('remove')
        self.unique_id = str(time.time()).split('.')[0]

        self.policies = policies or []
        self.recipe_manager = RecipeManager(logger)
        self.recipe = None
        if recipe_path is not None:
            self.recipe = self.recipe_manager.load(self, recipe_path)

    @property
    def run_workdir(self) -> Path:
        if self.workdir is None:
            raise GeneralError(
                "Existence of a run workdir was presumed but the workdir does not exist."
            )

        return self.workdir

    @functools.cached_property
    def state_format_marker_filepath(self) -> Path:
        return self.run_workdir / 'state-format'

    @functools.cached_property
    def state_format(self) -> StateFormat:
        try:
            format_name = self.state_format_marker_filepath.read_text().strip()

        except FileNotFoundError:
            state_format = tmt.utils.get_state_format()

            self.debug(
                "No state format marker file found,"
                f" using the default state format '{state_format.name}'."
            )

            return state_format

        except Exception as exc:
            raise GeneralError('Failed to read state format marker.') from exc

        state_format = tmt.utils.get_state_format(format=format_name)

        self.debug(
            f"State format marker file found, using the '{state_format.name}' state format."
        )

        return state_format

    def read_state(self, filepath: Path) -> Any:
        """
        Read a stored state from the given file.

        .. important::

            No deserialization is performed, it is the responsibility of the
            caller to turn loaded structure, consisting of built-in-like
            types, into objects of desired classes, e.g. by the power of
            :py:meth:`tmt.container.SerializableContainer.deserialize`.

        :param filepath: file to read the state from.
        :returns: stored state as Python data structure.
        """

        return self.state_format.from_state(
            self.read_file(Path(f'{filepath}{self.state_format.suffix}'))
        )

    def write_state(self, filepath: Path, data: Any) -> None:
        """
        Write a state into the given file.

        .. important::

            No serialization is performed, it is the responsibility of the
            caller to turn internal objects into built-in-like Python types,
            e.g. by the power of
            :py:meth:`tmt.container.SerializableContainer.serialize`.

        :param filepath: file to write the state into.
        :param data: state as Python data structure.
        """

        return self.write_file(
            Path(f'{filepath}{self.state_format.suffix}'), self.state_format.to_state(data)
        )

    def load_workdir(self, *, with_logfiles: bool = True) -> None:
        """
        Prepare the run workdir and associated.

        :param with_logfiles: whether to attach logfile handlers
        """
        self._workdir_load(self._workdir_path)
        if with_logfiles:
            warnings_file = self.run_workdir / self.WARNINGS_FILE_NAME
            self._logger.add_runwarnings_handler(warnings_file)

    @functools.cached_property
    def runner(self) -> 'tmt.steps.provision.local.GuestLocal':
        import tmt.guest
        import tmt.steps.provision.local

        guest_runner = tmt.steps.provision.local.GuestLocal(
            data=tmt.guest.GuestData(primary_address='localhost', role=None),
            name='tmt runner',
            logger=self._logger,
        )
        # Override some facts that we do not want to expose
        # No sudo access on the runner
        guest_runner.facts.can_sudo = False
        guest_runner.facts.sudo_prefix = ""
        return guest_runner

    def _use_default_plan(self) -> None:
        """
        Prepare metadata tree with only the default plan
        """
        default_plan: dict[str, Any] = tmt.utils.yaml_to_dict(
            tmt.templates.MANAGER.render_default_plan()
        )
        # The default discover method for this case is 'shell'
        default_plan[tmt.templates.DEFAULT_PLAN_NAME]['discover']['how'] = 'shell'
        self.tree = tmt.Tree(logger=self._logger, tree=fmf.Tree(default_plan))
        self.debug("No metadata found, using the default plan.")

    def _save_tree(self, tree: Optional[Tree]) -> None:
        """
        Save metadata tree, handle the default plan
        """
        from tmt.base.plan import Plan

        default_plan: dict[str, Any] = tmt.utils.yaml_to_dict(
            tmt.templates.MANAGER.render_default_plan()
        )
        try:
            self.tree = tree or tmt.Tree(logger=self._logger, path=Path('.'))
            self.debug(f"Using tree '{self.tree.root}'.")
            # Clear the tree and insert default plan if requested
            if Plan._opt("default"):
                default_plan_tree = fmf.Tree(default_plan)

                # Make sure the fmf root is set for both the default
                # plan (needed during the discover step) and the whole
                # tree (which is stored to 'run.yaml' during save()).
                default_plan_node = cast(
                    Optional[fmf.Tree], default_plan_tree.find(tmt.templates.DEFAULT_PLAN_NAME)
                )
                if default_plan_node is None:
                    raise GeneralError(
                        f"Failed to find default plan '{tmt.templates.DEFAULT_PLAN_NAME}'"
                        " in the default plan tree."
                    )

                default_plan_node.root = self.tree.root
                default_plan_tree.root = self.tree.root

                self.tree.tree = default_plan_tree
                self.debug("Enforcing use of the default plan.")

            # Insert default plan if no plan detected. Check using
            # tree.prune() instead of self.tree.plans() to prevent
            # creating plan objects which leads to wrong expansion of
            # environment variables from the command line.
            existing_plans: list[fmf.Tree] = list(
                cast(Iterable[fmf.Tree], self.tree.tree.prune(keys=['execute']))
            ) + list(cast(Iterable[fmf.Tree], self.tree.tree.prune(keys=['plan'])))

            if not existing_plans:
                self.tree.tree.update(default_plan)
                self.debug("No plan found, adding the default plan.")
        # Create an empty default plan if no fmf metadata found
        except tmt.utils.MetadataError:
            self._use_default_plan()

    @property
    def _environment_from_workdir(self) -> Environment:
        """
        Environment variables saved in the workdir.
        """

        if self.data is None:
            return Environment()

        return self.data.environment.copy()

    @property
    def _environment_from_cli(self) -> Environment:
        """
        Environment variables from ``--environment`` and ``--environment-file`` options.
        """

        assert self.tree is not None  # narrow type

        return tmt.utils.Environment.from_inputs(
            raw_cli_environment_files=self.opt('environment-file') or [],
            raw_cli_environment=self.opt('environment'),
            file_root=Path(self.tree.root) if self.tree.root else None,
            logger=self._logger,
        )

    @property
    def _environment_from_recipe(self) -> Environment:
        """
        Environment variables from the recipe.
        """

        if self.recipe is None:
            return Environment()

        return self.recipe.run.environment.copy()

    @property
    def environment(self) -> Environment:
        """
        Environment variables of the run.

        Contains all environment variables collected from multiple
        sources (in the following order):

        * run's environment, saved from the previous runs in the same
          workdir,
        * run's environment, ``--environment`` and ``--environment-file``
          options.

        If a recipe was provided, the environment is taken directly
        from the recipe instead.
        """
        if self._environment_from_recipe:
            return Environment(
                {
                    **self._environment_from_recipe,
                }
            )
        return Environment(
            {
                **self._environment_from_workdir,
                **self._environment_from_cli,
            }
        )

    def save(self) -> None:
        """
        Save list of selected plans and enabled steps
        """

        self.state_format_marker_filepath.unlink(missing_ok=True)
        self.state_format_marker_filepath.write_text(self.state_format.name)

        assert self.tree is not None  # narrow type
        assert self._cli_context_object is not None  # narrow type
        assert self.workdir is not None  # narrow type
        data = RunData(
            root=str(self.tree.root) if self.tree.root else None,
            plans=[plan.name for plan in self._plans] if self._plans is not None else None,
            steps=list(self._cli_context_object.steps),
            environment=self.environment,
            remove=self.remove,
        )
        self.write_state(self.workdir / 'run', data.to_serialized())

    def load_from_workdir(self) -> None:
        """
        Load the run from its workdir, do not require the root in
        run.yaml to exist. Does not load the fmf tree.

        Use only when the data in workdir is sufficient (e.g. tmt
        clean and status only require the steps to be loaded and
        their status).
        """
        from tmt.base.plan import Plan

        self._save_tree(self._tree)
        # with_logfiles=False: This function is currently only called by `tmt.utils.load_run`
        #  which in turn is only called by status and clean, both cases where we do not want
        #  to attach the logfile loggers to.
        self.load_workdir(with_logfiles=False)

        assert self.workdir is not None  # narrow type

        try:
            self.data = RunData.from_serialized(self.read_state(self.workdir / 'run'))

        except tmt.utils.FileError:
            self.debug('Run data not found.')
            return

        assert self._cli_context_object is not None  # narrow type
        self._cli_context_object.steps = set(self.data.steps)

        self._plans = []

        # The root directory of the tree may not be available, create
        # an fmf node that only contains the necessary attributes
        # required for plan/step loading. We will also need a dummy
        # parent for these nodes, so we would correctly load each
        # plan's name.
        dummy_parent = fmf.Tree({'summary': 'unused'})

        for plan in self.data.plans or []:
            node = fmf.Tree({'execute': None}, name=plan, parent=dummy_parent)
            self._plans.append(
                Plan(node=node, logger=self._logger.descend(), run=self, skip_validation=True)
            )

    def load(self) -> None:
        """
        Load list of selected plans and enabled steps
        """
        from tmt.base.plan import Plan

        assert self.workdir is not None  # narrow type

        try:
            self.data = RunData.from_serialized(self.read_state(self.workdir / 'run'))

        except tmt.utils.FileError:
            self.debug('Run data not found.')
            return

        # If run id was given and root was not explicitly specified,
        # create a new Tree from the root in run.yaml
        if self._workdir and not self.opt('root'):
            if self.data.root:
                self._save_tree(tmt.Tree(logger=self._logger.descend(), path=Path(self.data.root)))
            else:
                # The run was used without any metadata, default plan
                # was used, load it
                self._use_default_plan()

        # Filter plans by name unless specified on the command line
        plan_options = ['names', 'filters', 'conditions', 'links', 'default']
        if not any(Plan._opt(option) for option in plan_options):
            assert self.tree is not None  # narrow type

            if self.data.plans is None:
                plan_names = []
            else:
                plan_names = [f"^{re.escape(plan_name)}$" for plan_name in self.data.plans]

            self._plans = self.tree.plans(run=self, names=plan_names)

        # Initialize steps only if not selected on the command line
        step_options = ['all', 'since', 'until', 'after', 'before', 'skip']
        selected = any(self.opt(option) for option in step_options)
        assert self._cli_context_object is not None  # narrow type
        if not selected and not self._cli_context_object.steps:
            self._cli_context_object.steps = set(self.data.steps)

        # If the remove was enabled, restore it, option overrides
        self.remove = self.remove or self.data.remove
        self.debug(f"Remove workdir when finished: {self.remove}", level=3)

    @functools.cached_property
    def plans(self) -> Sequence["Plan"]:
        """
        Test plans for execution
        """

        if self._plans is None:
            assert self.tree is not None  # narrow type
            self._plans = self.tree.plans(run=self, filters=['enabled:true'])
        return self._plans

    @functools.cached_property
    def plan_queue(self) -> Sequence["Plan"]:
        """
        A list of plans remaining to be executed.

        It is being populated via :py:attr:`plans`, but eventually,
        :py:meth:`go` will remove plans from it as they get processed.
        :py:attr:`plans` will remain untouched and will represent all
        plans collected.
        """

        return self.plans[:]

    def swap_plans(self, plan: "Plan", *others: "Plan") -> None:
        """
        Replace given plan with one or more plans.

        :param plan: a plan to remove.
        :param others: plans to put into the queue instead of ``plans``.
        """
        from tmt.base.plan import Plan

        plans = cast(list[Plan], self.plans)
        plan_queue = cast(list[Plan], self.plan_queue)

        if plan in plan_queue:
            plan_queue.remove(plan)
            plans.remove(plan)

        plan_queue.extend(others)
        plans.extend(others)

    def finish(self) -> None:
        """
        Check overall results, return appropriate exit code
        """
        # Save recipe
        if not self.is_dry_run:
            self.recipe_manager.save(self)

        # We get interesting results only if execute or prepare step is enabled
        execute = self.plans[0].execute
        report = self.plans[0].report
        interesting_results = execute.enabled or report.enabled

        # Gather all results and give an overall summary
        results = [result for plan in self.plans for result in plan.execute.results()]
        if interesting_results:
            self.info('')
            self.info('total', Result.summary(results), color='cyan')

        # Remove the workdir if enabled
        if self.remove and self.plans[0].cleanup.enabled:
            self._workdir_cleanup(self.run_workdir)

        # Skip handling of the exit codes in dry mode and
        # when there are no interesting results available
        if self.is_dry_run or not interesting_results:
            return

        # Return 0 if test execution has been intentionally skipped
        if tmt.steps.execute.Execute._opt("dry"):
            raise SystemExit(0)

        # Return appropriate exit code based on the total stats
        raise SystemExit(tmt.result.results_to_exit_code(results, bool(execute.enabled)))

    def follow(self) -> None:
        """
        Periodically check for new lines in the log.
        """
        with open(self.run_workdir / tmt.log.LOG_FILENAME) as logfile:
            # Move to the end of the file
            logfile.seek(0, os.SEEK_END)
            # Rewind some lines back to show more context
            location = logfile.tell()
            read_lines = 0
            while location >= 0:
                logfile.seek(location)
                location -= 1
                current_char = logfile.read(1)
                if current_char == '\n':
                    read_lines += 1
                if read_lines > FOLLOW_LINES:
                    break

            while True:
                line = logfile.readline()
                if line:
                    print(line, end='')
                else:
                    time.sleep(0.5)

    def show_runner(self, logger: tmt.log.Logger) -> None:
        """
        Log facts about the machine on which tmt runs
        """

        # populate facts before logging
        _ = self.runner.facts

        log = functools.partial(logger.debug, color='green', level=3)

        log('tmt runner')

        for _, key_formatted, value_formatted in self.runner.facts.format():
            log(key_formatted, value_formatted, shift=1)

    def copy_scripts(self) -> None:
        """
        Copy the tmt helper scripts under the running workdir
        into a new scripts directory.
        """
        destination = self.run_workdir / tmt.steps.scripts.SCRIPTS_DIR_NAME
        destination.mkdir(exist_ok=True)

        for script in tmt.steps.scripts.SCRIPTS:
            with script as source:
                # TODO: Consider making these symlinks instead
                for filename in [script.source_filename, *script.aliases]:
                    target_file = destination / filename
                    shutil.copy(source, target_file)
                    target_file.chmod(0o0755)

    def prepare_for_try(self, tree: Tree) -> None:
        """
        Prepare the run for the try command
        """
        self.tree = tree
        self._save_tree(self.tree)
        self.load_workdir()
        self.config.last_run = self.run_workdir
        self.info(str(self.run_workdir), color='magenta')

        # Create scripts directory and copy tmt scripts there
        self.copy_scripts()

    def go(self) -> None:
        """
        Go and do test steps for selected plans
        """
        from tmt.base.plan import Plan

        # Create the workdir and save last run
        self._save_tree(self._tree)
        self.load_workdir()
        assert self.tree is not None  # narrow type
        assert self._workdir is not None  # narrow type
        if self.tree.root and self._workdir.is_relative_to(self.tree.root):
            raise tmt.utils.GeneralError(
                f"Run workdir '{self._workdir}' must not be inside fmf root '{self.tree.root}'."
            )
        self.config.last_run = self.run_workdir
        # Show run id / workdir path
        self.info(str(self.run_workdir), color='magenta')
        self.debug(f"tmt version: {tmt.__version__}")
        self.debug('tmt command line', Command(*sys.argv))

        if self.is_feeling_safe:
            self.warn('User is feeling safe.')

        self.show_runner(self._logger)

        # Create scripts directory and copy tmt scripts there
        self.copy_scripts()

        # Attempt to load run data
        self.load()
        # Follow log instead of executing the run
        if self.opt('follow'):
            self.follow()

        # Propagate dry mode from provision to prepare, execute, finish
        # and cleanup (basically nothing can be done in any of these if
        # there is no guest provisioned)
        if tmt.steps.provision.Provision._opt("dry"):
            for _klass in (
                tmt.steps.prepare.Prepare,
                tmt.steps.execute.Execute,
                tmt.steps.finish.Finish,
                tmt.steps.cleanup.Cleanup,
            ):
                klass = cast(type[tmt.steps.Step], _klass)

                cli_invocation = klass.cli_invocation

                if cli_invocation is None:
                    klass.cli_invocation = tmt.cli.CliInvocation(
                        context=None, options={'dry': True}
                    )

                else:
                    cli_invocation.options['dry'] = True

        # Enable selected steps
        assert self._cli_context_object is not None  # narrow type
        enabled_steps = self._cli_context_object.steps
        all_steps = self.opt('all') or not enabled_steps
        since = self.opt('since')
        until = self.opt('until')
        after = self.opt('after')
        before = self.opt('before')
        skip = self.opt('skip')

        if any([all_steps, since, until, after, before]):
            # Detect index of the first and last enabled step
            if since:
                first = tmt.steps.STEPS.index(since)
            elif after:
                first = tmt.steps.STEPS.index(after) + 1
            else:
                first = tmt.steps.STEPS.index('discover')
            if until:
                last = tmt.steps.STEPS.index(until)
            elif before:
                last = tmt.steps.STEPS.index(before) - 1
            else:
                last = tmt.steps.STEPS.index('cleanup')
            # Enable all steps between the first and last
            for index in range(first, last + 1):
                step = tmt.steps.STEPS[index]
                if step not in skip:
                    enabled_steps.add(step)
        self.debug(f"Enabled steps: {fmf.utils.listed(enabled_steps)}")

        # Show summary, store run data
        if not self.plans:
            raise tmt.utils.GeneralError("No plans found.")
        self.verbose(f"Found {fmf.utils.listed(self.plans, 'plan')}.")
        self.save()

        # Iterate over plans
        crashed_plans: list[tuple[Plan, Exception]] = []

        while self.plan_queue:
            plan = cast(list[Plan], self.plan_queue).pop(0)

            try:
                plan.go()

            except Exception as error:
                if self.opt('on-plan-error') == 'quit':
                    raise tmt.utils.GeneralError('plan failed.') from error

                crashed_plans.append((plan, error))

        if crashed_plans:
            raise tmt.utils.GeneralError(
                'plan failed', causes=[error for _, error in crashed_plans]
            )

        # Update the last run id at the very end
        # (override possible runs created during execution)
        self.config.last_run = self.run_workdir

        # Give the final summary, remove workdir, handle exit codes
        self.finish()
