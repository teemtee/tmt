import functools
from collections.abc import Iterator
from typing import (
    TYPE_CHECKING,
    Any,
    Optional,
    TypeVar,
    Union,
    cast,
)

import click
import fmf.utils
from click import echo

import tmt
import tmt.guest
import tmt.hardware
import tmt.log
import tmt.queue
import tmt.steps
import tmt.utils
from tmt._compat.typing import Self
from tmt.ansible import AnsibleInventory
from tmt.container import (
    SerializableContainer,
    container,
    field,
)
from tmt.log import Logger
from tmt.options import option
from tmt.plugins import PluginRegistry
from tmt.steps import Action, ActionTask, PhaseQueue, PushTask, sync_with_guests
from tmt.utils import Path

if TYPE_CHECKING:
    import tmt.base.core
    import tmt.cli


@container
class ProvisionStepData(tmt.steps.StepData):
    # guest role in the multihost scenario
    role: Optional[str] = None

    hardware: Optional[tmt.hardware.Hardware] = field(
        default=cast(Optional[tmt.hardware.Hardware], None),
        normalize=tmt.guest.normalize_hardware,
        serialize=lambda hardware: hardware.to_spec() if hardware else None,
        unserialize=lambda serialized: (
            tmt.hardware.Hardware.from_spec(serialized) if serialized is not None else None
        ),
    )


ProvisionStepDataT = TypeVar('ProvisionStepDataT', bound=ProvisionStepData)


class ProvisionPlugin(tmt.steps.GuestlessPlugin[ProvisionStepDataT, None]):
    """
    Common parent of provision plugins
    """

    # ignore[assignment]: as a base class, ProvisionStepData is not included in
    # ProvisionStepDataT.
    _data_class = ProvisionStepData  # type: ignore[assignment]
    # TODO: Make Guest be a generic input
    _guest_class = tmt.guest.Guest

    #: If set, the plugin can be asked to provision in multiple threads at the
    #: same time. Plugins that do not support parallel provisioning should keep
    #: this set to ``False``.
    _thread_safe: bool = False

    # Default implementation for provision is a virtual machine
    how = 'virtual'

    # Methods ("how: ..." implementations) registered for the same step.
    _supported_methods: PluginRegistry[tmt.steps.Method] = PluginRegistry('step.provision')

    # TODO: Generics would provide a better type, https://github.com/teemtee/tmt/issues/1437
    _guest: Optional[tmt.guest.Guest] = None

    @property
    def _preserved_workdir_members(self) -> set[str]:
        """
        A set of members of the step workdir that should not be removed.
        """

        return {*super()._preserved_workdir_members, "logs"}

    @classmethod
    def base_command(
        cls,
        usage: str,
        method_class: Optional[type[click.Command]] = None,
    ) -> click.Command:
        """
        Create base click command (common for all provision plugins)
        """

        # Prepare general usage message for the step
        if method_class:
            usage = Provision.usage(method_overview=usage)

        # Create the command
        @click.command(cls=method_class, help=usage)
        @click.pass_context
        @option('-h', '--how', metavar='METHOD', help='Use specified method for provisioning.')
        @tmt.steps.PHASE_OPTIONS
        def provision(context: 'tmt.cli.Context', **kwargs: Any) -> None:
            context.obj.steps.add('provision')
            Provision.store_cli_invocation(context)

        return provision

    def go(self, *, logger: Optional[tmt.log.Logger] = None) -> None:
        """
        Perform actions shared among plugins when beginning their tasks
        """

        self.go_prolog(logger or self._logger)

    # TODO: this might be needed until https://github.com/teemtee/tmt/issues/1696 is resolved
    def opt(self, option: str, default: Optional[Any] = None) -> Any:
        """
        Get an option from the command line options
        """

        if option == 'ssh-option':
            value = super().opt(option, default=default)

            if isinstance(value, tuple):
                return list(value)

            return value

        return super().opt(option, default=default)

    def _verify_guest(self) -> None:
        """
        Verify that the guest is acceptable for a Provision step.

        May report the state of the guest and incidentally its facts.
        """

        assert self.guest is not None  # Narrow type

        # Check if we need or can have sudo access
        if not self.guest.facts.is_superuser and not self.guest.facts.can_sudo:
            self.info("User does not have sudo access, we assume everything is pre-setup.")

    def wake(self, data: Optional[tmt.guest.GuestData] = None) -> None:
        """
        Wake up the plugin

        Override data with command line options.
        Wake up the guest based on provided guest data.
        """

        super().wake()

        if data is not None:
            # Note: This is a genuine type-annotation issue. _guest_class must be non-abstract here
            guest = self._guest_class(  # type: ignore[abstract]
                logger=self._logger, data=data, name=self.name, parent=self.step
            )
            guest.wake()
            self._guest = guest
            self._verify_guest()

    # TODO: getter. Like in Java. Do we need it?
    @property
    def guest(self) -> Optional[tmt.guest.Guest]:
        """
        Return the provisioned guest.
        """

        return self._guest

    def essential_requires(self) -> list['tmt.base.core.Dependency']:
        """
        Collect all essential requirements of the guest implementation.

        Essential requirements of a guest are necessary for the guest to be
        usable for testing.

        By default, plugin's guest class, :py:attr:`ProvisionPlugin._guest_class`,
        is asked to provide the list of required packages via
        :py:meth:`Guest.requires` method.

        :returns: a list of requirements.
        """

        return self._guest_class.essential_requires()

    @classmethod
    def options(cls, how: Optional[str] = None) -> list[tmt.options.ClickOptionDecoratorType]:
        """
        Return list of options.
        """

        return super().options(how) + cls._guest_class.options(how)

    @classmethod
    def clean_images(cls, clean: 'tmt.base.core.Clean', dry: bool, workdir_root: Path) -> bool:
        """
        Remove the images of one particular plugin
        """

        return True

    def show(self, keys: Optional[list[str]] = None) -> None:
        keys = keys or list(set(self.data.keys()))

        show_hardware = 'hardware' in keys

        if show_hardware:
            keys.remove('hardware')

        super().show(keys=keys)

        if show_hardware:
            hardware: Optional[tmt.hardware.Hardware] = self.data.hardware

            if hardware:
                echo(tmt.utils.format('hardware', tmt.utils.to_yaml(hardware.to_spec())))


class ProvisionTask(tmt.queue.GuestlessTask[None]):
    """
    A task to run provisioning of multiple guests
    """

    #: Phases describing guests to provision. In the ``provision`` step,
    #: each phase describes one guest.
    phases: list[ProvisionPlugin[ProvisionStepData]]

    #: When ``ProvisionTask`` instance is received from the queue, ``phase``
    #: points to the phase that has been provisioned by the task.
    phase: Optional[ProvisionPlugin[ProvisionStepData]] = None

    def __init__(
        self, phases: list[ProvisionPlugin[ProvisionStepData]], logger: tmt.log.Logger
    ) -> None:
        super().__init__(logger)

        self.phases = phases

    @property
    def name(self) -> str:
        return cast(str, fmf.utils.listed([phase.name for phase in self.phases]))

    def go(self) -> Iterator['ProvisionTask']:
        def _on_complete(task: 'Self', phase: ProvisionPlugin[ProvisionStepData]) -> 'Self':
            task.phases = []
            task.phase = phase

            return task

        yield from self._invoke_in_pool(
            # Run across all phases known to this task.
            units=self.phases,
            # Unit ID here is phases's name
            get_label=lambda task, phase: phase.name,
            extract_logger=lambda task, phase: phase._logger,
            inject_logger=lambda task, phase, logger: phase.inject_logger(logger),
            # Submit work for the executor pool.
            submit=lambda task, phase, logger, executor: executor.submit(phase.go),
            on_complete=_on_complete,
            logger=self.logger,
        )

    def run(self, logger: Logger) -> None:
        raise AssertionError("run is not used by ProvisionTask.go")


class ProvisionQueue(tmt.queue.Queue[ProvisionTask]):
    """
    Queue class for running provisioning tasks
    """

    def enqueue(self, *, phases: list[ProvisionPlugin[ProvisionStepData]], logger: Logger) -> None:
        self.enqueue_task(ProvisionTask(phases, logger))


class Provision(tmt.steps.Step):
    """
    Provision an environment for testing or use localhost.
    """

    # Default implementation for provision is a virtual machine
    DEFAULT_HOW = 'virtual'

    _plugin_base_class = ProvisionPlugin

    #: All known guests.
    #:
    #: .. warning::
    #:
    #:    Guests may not necessarily be fully provisioned. They are
    #:    from plugins as soon as possible, and guests may easily be
    #:    still waiting for their infrastructure to finish the task.
    #:    For the list of successfully provisioned guests, see
    #:    :py:attr:`ready_guests`.
    guests: list[tmt.guest.Guest]

    @property
    def ready_guests(self) -> list[tmt.guest.Guest]:
        """
        All successfully provisioned guests.

        Most of the time, after ``provision`` step finishes successfully,
        the list should be the same as :py:attr:`guests`, i.e. it should
        contain all known guests. There are situations when
        ``ready_guests`` will be a subset of ``guests``, and their users
        must decide which collection is the best for the desired goal:

        * when ``provision`` is still running. ``ready_guests`` will be
          slowly gaining new guests as they get up and running.
        * in dry-run mode, no actual provisioning is expected to happen,
          therefore there are no unsuccessfully provisioned guests. In
          this mode, all known guests are considered as ready, and
          ``ready_guests`` is the same as ``guests``.
        * if tmt is interrupted by a signal or user. Not all guests will
          finish their provisioning process, and ``ready_guests`` may
          contain just the finished ones.
        """

        if self.is_dry_run:
            return self.guests

        return [guest for guest in self.guests if guest.is_ready]

    @functools.cached_property
    def ansible_inventory_path(self) -> Path:
        """
        Get path to Ansible inventory
        This property lazily generates the Ansible inventory file on first access.

        :returns: Path to the generated inventory.yaml file
        """
        inventory_path = self.step_workdir / 'inventory.yaml'

        # Get layout from plan-level ansible configuration and resolve path
        layout_path = None
        if (
            self.plan.ansible
            and self.plan.ansible.inventory
            and self.plan.ansible.inventory.layout
        ):
            layout_path = self.plan.anchor_path / self.plan.ansible.inventory.layout

        inventory = AnsibleInventory.generate(self.ready_guests, layout_path)
        self.write(inventory_path, tmt.utils.to_yaml(inventory))

        self.info('ansible', f"Inventory saved to '{inventory_path}'")

        return inventory_path

    def __init__(
        self,
        *,
        plan: 'tmt.Plan',
        data: tmt.steps.RawStepDataArgument,
        logger: tmt.log.Logger,
    ) -> None:
        """
        Initialize provision step data
        """

        super().__init__(plan=plan, data=data, logger=logger)

        self.guests = []
        self._guest_data: dict[str, tmt.guest.GuestData] = {}

    @property
    def _preserved_workdir_members(self) -> set[str]:
        """
        A set of members of the step workdir that should not be removed.
        """

        return {
            *super()._preserved_workdir_members,
            f'guests{tmt.utils.STATE_FILENAME_SUFFIX}',
            'inventory.yaml',
        }

    @property
    def is_multihost(self) -> bool:
        return len(self.data) > 1

    def get_guests_info(self) -> list[tuple[str, Optional[str]]]:
        """
        Get a list containing the names and roles of guests that should be enabled.
        """

        phases = [
            cast(ProvisionPlugin[ProvisionStepData], phase)
            for phase in self.phases(classes=ProvisionPlugin)
            if phase.enabled_by_when
        ]
        return [(phase.data.name, phase.data.role) for phase in phases]

    def load(self) -> None:
        """
        Load guest data from the workdir
        """

        super().load()
        try:
            raw_guest_data: dict[str, dict[str, Any]] = self.read_state('guests')

            self._guest_data = {
                name: SerializableContainer.unserialize(guest_data, self._logger)
                for name, guest_data in raw_guest_data.items()
            }

        except tmt.utils.FileError:
            self.debug('Provisioned guests not found.', level=2)

    def save(self) -> None:
        """
        Save guest data to the workdir
        """

        super().save()
        try:
            raw_guest_data = {
                guest.name: guest.save().to_serialized() for guest in self.ready_guests
            }

            self.write_state('guests', raw_guest_data)
        except tmt.utils.FileError:
            self.debug('Failed to save provisioned guests.')

    def wake(self) -> None:
        """
        Wake up the step (process workdir and command line)
        """

        super().wake()

        # Choose the right plugin and wake it up
        for data in self.data:
            # FIXME: cast() - see https://github.com/teemtee/tmt/issues/1599
            plugin = cast(
                ProvisionPlugin[ProvisionStepData], ProvisionPlugin.delegate(self, data=data)
            )
            self._phases.append(plugin)
            # If guest data loaded, perform a complete wake up
            plugin.wake(data=self._guest_data.get(plugin.name))

            if plugin.guest:
                self.guests.append(plugin.guest)

        # Nothing more to do if already done and not asked to run again
        if self.status() == 'done' and not self.should_run_again:
            self.debug('Provision wake up complete (already done before).', level=2)
        # Save status and step data (now we know what to do)
        else:
            self.status('todo')
            self.save()

    def suspend(self) -> None:
        super().suspend()

        for guest in self.guests:
            guest.suspend()

    def summary(self) -> None:
        """
        Give a concise summary of the provisioning
        """

        # Summary of provisioned guests
        guests = fmf.utils.listed(self.ready_guests, 'guest')
        self.info('summary', f'{guests} provisioned', 'green', shift=1)
        # Guest list in verbose mode
        for guest in self.ready_guests:
            if not guest.name.startswith(tmt.utils.DEFAULT_NAME):
                self.verbose(guest.name, color='red', shift=2)

    def go(self, force: bool = False) -> None:
        """
        Provision all guests
        """

        super().go(force=force)

        # Nothing more to do if already done
        if self.status() == 'done':
            self.info('status', 'done', 'green', shift=1)
            self.summary()
            self.actions()
            return

        # Provision guests
        self.guests = []

        def _run_provision_phases(
            phases: list[ProvisionPlugin[ProvisionStepData]],
        ) -> tuple[list[ProvisionTask], list[ProvisionTask]]:
            """
            Run the given set of ``provision`` phases.

            :param phases: list of ``provision`` step phases. By "running" them,
                they would provision their respective guests.
            :returns: two lists, a list of all :py:class:`ProvisionTask`
                instances queued, and a subset of the first list collecting only
                those tasks that failed.
            """

            queue: ProvisionQueue = ProvisionQueue(
                'provision.provision', self._logger.descend(logger_name=f'{self}.queue')
            )

            queue.enqueue(phases=phases, logger=queue._logger)

            all_tasks: list[ProvisionTask] = []
            failed_tasks: list[ProvisionTask] = []

            for outcome in queue.run():
                all_tasks.append(outcome)

                if outcome.exc:
                    outcome.logger.fail(str(outcome.exc))

                    failed_tasks.append(outcome)

                if outcome.phase and outcome.phase.guest:
                    guest = outcome.phase.guest

                    # Don't show guest details if there was an exception.
                    # The guest may not be reachable while syncing facts.
                    if not outcome.exc:
                        guest.show()

                    self.guests.append(guest)

            return all_tasks, failed_tasks

        def _run_action_phases(phases: list[Action]) -> tuple[list[ActionTask], list[ActionTask]]:
            """
            Run the given set of actions.

            :param phases: list of actions, e.g. ``login`` or ``reboot``, given
                in the ``provision`` step.
            :returns: two lists, a list of all :py:class:`ActionTask` instances
                queued, and a subset of the first list collecting only those
                tasks that failed.
            """

            queue: PhaseQueue[ProvisionStepData, None] = PhaseQueue(
                'provision.action', self._logger.descend(logger_name=f'{self}.queue')
            )

            for action in phases:
                queue.enqueue_action(phase=action)

            all_tasks: list[ActionTask] = []
            failed_tasks: list[ActionTask] = []

            for outcome in queue.run():
                assert isinstance(outcome, ActionTask)

                all_tasks.append(outcome)

                if outcome.exc:
                    outcome.logger.fail(str(outcome.exc))

                    failed_tasks.append(outcome)

            return all_tasks, failed_tasks

        # Provisioning phases may be intermixed with actions. To perform all
        # phases and actions in a consistent manner, we will process them in
        # the order or their `order` key. We will group provisioning phases
        # not interrupted by action into batches, and run the sequence of
        # provisioning phases in parallel.
        all_phases = [
            p
            for p in self.phases(classes=(Action, ProvisionPlugin))
            if isinstance(p, Action) or p.enabled_by_when
        ]
        all_phases.sort(key=lambda x: x.order)

        all_outcomes: list[Union[ActionTask, ProvisionTask]] = []
        failed_outcomes: list[Union[ActionTask, ProvisionTask]] = []

        # Wrapping the code with try/except catching KeyboardInterrupt
        # exceptions that signals tmt has been interrupted. We need to
        # collect all known guests and populate `self.guests` so finish
        # can release them if necessary.
        try:
            while all_phases:
                # Start looking for sequences of phases of the same kind. Collect
                # as many as possible, until hitting a different one
                phase = all_phases.pop(0)

                if isinstance(phase, Action):
                    action_phases: list[Action] = [phase]

                    while all_phases and isinstance(all_phases[0], Action):
                        action_phases.append(cast(Action, all_phases.pop(0)))

                    all_action_outcomes, failed_action_outcomes = _run_action_phases(action_phases)

                    all_outcomes += all_action_outcomes
                    failed_outcomes += failed_action_outcomes

                else:
                    plugin_phases: list[ProvisionPlugin[ProvisionStepData]] = [phase]  # type: ignore[list-item]

                    # ignore[attr-defined]: mypy does not recognize `phase` as `ProvisionPlugin`.
                    if phase._thread_safe:  # type: ignore[attr-defined]
                        while all_phases:
                            if not isinstance(all_phases[0], ProvisionPlugin):
                                break

                            if not all_phases[0]._thread_safe:
                                break

                            plugin_phases.append(
                                cast(ProvisionPlugin[ProvisionStepData], all_phases.pop(0))
                            )

                    all_plugin_outcomes, failed_plugin_outcomes = _run_provision_phases(
                        plugin_phases
                    )

                    all_outcomes += all_plugin_outcomes
                    failed_outcomes += failed_plugin_outcomes

        except KeyboardInterrupt:
            self.guests = [
                phase.guest
                for phase in self.phases(classes=ProvisionPlugin)
                if phase.guest is not None
            ]

            raise

        # A plugin will only raise SystemExit if the exit is really desired
        # and no other actions should be done. An example of this is
        # listing available images. In such case, the workdir is deleted
        # as it's redundant and save() would throw an error.
        #
        # TODO: in theory, there may be many, many plugins raising `SystemExit`
        # but we can re-raise just a single one. It would be better to not use
        # an exception to signal this, but rather set/return a special object,
        # leaving the materialization into `SystemExit` to the step and/or tmt.
        # Or not do any one-shot actions under the disguise of provisioning...
        exiting_tasks = [outcome for outcome in all_outcomes if outcome.requested_exit is not None]

        if exiting_tasks:
            assert exiting_tasks[0].requested_exit is not None

            raise exiting_tasks[0].requested_exit

        if failed_outcomes:
            raise tmt.utils.GeneralError(
                'provision step failed',
                causes=[outcome.exc for outcome in failed_outcomes if outcome.exc is not None],
            )

        # Push the plan workdir to the provisioned guests as the last
        # step. This is a counterpart of the PullTask in Finish.go().
        # Without it `tmt run provision finish login` would break on
        # non-existent plan data directory.
        # TODO simplify as part of the data pulling/pushing cleanup
        # https://github.com/teemtee/tmt/issues/4067
        sync_with_guests(self, 'push', PushTask(self.guests, self._logger), self._logger)

        # To separate "provision" from the follow-up logging visually
        self.info('')

        # Give a summary, update status and save
        self.summary()
        self.status('done')
        self.save()
