import copy
import dataclasses
from typing import TYPE_CHECKING, Any, Optional, TypeVar, Union, cast

import click
import fmf

import tmt
import tmt.steps
from tmt.options import option
from tmt.plugins import PluginRegistry
from tmt.result import PhaseResult
from tmt.steps import (
    Action,
    ActionTask,
    Method,
    PhaseQueue,
    PluginTask,
    PullTask,
    sync_with_guests,
    )
from tmt.steps.provision import Guest

if TYPE_CHECKING:
    import tmt.cli


@dataclasses.dataclass
class FinishStepData(tmt.steps.WhereableStepData, tmt.steps.StepData):
    pass


FinishStepDataT = TypeVar('FinishStepDataT', bound=FinishStepData)


class FinishPlugin(tmt.steps.Plugin[FinishStepDataT, list[PhaseResult]]):
    """ Common parent of finish plugins """

    # ignore[assignment]: as a base class, FinishStepData is not included in
    # FinishStepDataT.
    _data_class = FinishStepData  # type: ignore[assignment]

    # Methods ("how: ..." implementations) registered for the same step.
    _supported_methods: PluginRegistry[Method] = PluginRegistry()

    @classmethod
    def base_command(
            cls,
            usage: str,
            method_class: Optional[type[click.Command]] = None) -> click.Command:
        """ Create base click command (common for all finish plugins) """

        # Prepare general usage message for the step
        if method_class:
            usage = Finish.usage(method_overview=usage)

        # Create the command
        @click.command(cls=method_class, help=usage)
        @click.pass_context
        @option(
            '-h', '--how', metavar='METHOD',
            help='Use specified method for finishing tasks.')
        @tmt.steps.PHASE_OPTIONS
        def finish(context: 'tmt.cli.Context', **kwargs: Any) -> None:
            context.obj.steps.add('finish')
            Finish.store_cli_invocation(context)

        return finish

    def go(
            self,
            *,
            guest: 'Guest',
            environment: Optional[tmt.utils.Environment] = None,
            logger: tmt.log.Logger) -> list[PhaseResult]:
        self.go_prolog(logger)

        return []


class Finish(tmt.steps.Step):
    """
    Perform the finishing tasks and clean up provisioned guests.

    Additional actions to be performed after the test execution has been
    completed. Counterpart of the ``prepare`` step useful for various
    cleanup actions. Also takes care of stopping and removing guests.

    Note that the ``finish`` step is also run when any of the previous
    steps failed (for example when the environment preparation was not
    successful) so that provisioned systems are not kept running.
    """

    _plugin_base_class = FinishPlugin

    _preserved_workdir_members = [
        *tmt.steps.Step._preserved_workdir_members,
        'results.yaml']

    def wake(self) -> None:
        """ Wake up the step (process workdir and command line) """
        super().wake()

        # Choose the right plugin and wake it up
        for data in self.data:
            # FIXME: cast() - see https://github.com/teemtee/tmt/issues/1599
            plugin = cast(
                FinishPlugin[FinishStepData],
                FinishPlugin.delegate(self, data=data))
            plugin.wake()
            # Add plugin only if there are data
            if not plugin.data.is_bare:
                self._phases.append(plugin)

        # Nothing more to do if already done and not asked to run again
        if self.status() == 'done' and not self.should_run_again:
            self.debug(
                'Finish wake up complete (already done before).', level=2)
        # Save status and step data (now we know what to do)
        else:
            self.status('todo')
            self.save()

    def summary(self) -> None:
        """ Give a concise summary """
        tasks = fmf.utils.listed(self.phases(), 'task')
        self.info('summary', f'{tasks} completed', 'green', shift=1)

    def go(self, force: bool = False) -> None:
        """ Execute finishing tasks """
        super().go(force=force)

        # Nothing more to do if already done
        if self.status() == 'done':
            self.info('status', 'done', 'green', shift=1)
            self.summary()
            self.actions()
            return

        # Nothing to do if no guests were provisioned
        if not self.plan.provision.guests():
            self.warn("Nothing to finish, no guests provisioned.", shift=1)
            return

        # Prepare guests
        guest_copies: list[Guest] = []

        for guest in self.plan.provision.guests():
            # Create a guest copy and change its parent so that the
            # operations inside finish plugins on the guest use the
            # finish step config rather than provision step config.
            guest_copy = copy.copy(guest)
            guest_copy.inject_logger(
                guest._logger.clone().apply_verbosity_options(**self._cli_options))
            guest_copy.parent = self

            guest_copies.append(guest_copy)

        queue: PhaseQueue[FinishStepData, list[PhaseResult]] = PhaseQueue(
            'finish',
            self._logger.descend(logger_name=f'{self}.queue'))

        for phase in self.phases(classes=(Action, FinishPlugin)):
            if isinstance(phase, Action):
                queue.enqueue_action(phase=phase)

            elif phase.enabled_by_when:
                queue.enqueue_plugin(
                    phase=phase,  # type: ignore[arg-type]
                    guests=[guest for guest in guest_copies if phase.enabled_on_guest(guest)]
                    )

        failed_tasks: list[Union[ActionTask, PluginTask[FinishStepData, list[PhaseResult]]]] = []
        results: list[PhaseResult] = []

        for outcome in queue.run():
            if not isinstance(outcome.phase, FinishPlugin):
                continue

            if outcome.exc:
                outcome.logger.fail(str(outcome.exc))

                failed_tasks.append(outcome)
                continue

            if outcome.result:
                results += outcome.result

        self._save_results(results)

        if failed_tasks:
            raise tmt.utils.GeneralError(
                'finish step failed',
                causes=[outcome.exc for outcome in failed_tasks if outcome.exc is not None]
                )

        # To separate "finish" from "pull" queue visually
        self.info('')

        # Pull artifacts created in the plan data directory
        # if there was at least one plugin executed
        if self.phases() and guest_copies:
            sync_with_guests(
                self,
                'pull',
                PullTask(
                    logger=self._logger,
                    guests=guest_copies,
                    source=self.plan.data_directory
                    ),
                self._logger)

            # To separate "finish" from "pull" queue visually
            self.info('')

        # Stop and remove provisioned guests
        for guest in self.plan.provision.guests():
            guest.stop()
            guest.remove()

        # Prune all irrelevant files and dirs
        assert self.plan.my_run is not None
        if not (self.plan.my_run.opt('keep') or self.is_dry_run):
            self.plan.prune()

        # Give a summary, update status and save
        self.summary()
        self.status('done')
        self.save()
