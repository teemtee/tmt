import copy
from typing import TYPE_CHECKING, Any, Optional, TypeVar, cast

import click
import fmf

import tmt
import tmt.steps
from tmt.container import container
from tmt.options import option
from tmt.plugins import PluginRegistry
from tmt.result import PhaseResult, ResultOutcome
from tmt.steps import (
    Action,
    Method,
    PhaseQueue,
    PluginOutcome,
    PluginTask,
    PullTask,
    sync_with_guests,
)
from tmt.steps.provision import Guest

if TYPE_CHECKING:
    import tmt.cli


@container
class FinishStepData(tmt.steps.WhereableStepData, tmt.steps.StepData):
    pass


FinishStepDataT = TypeVar('FinishStepDataT', bound=FinishStepData)


class FinishPlugin(tmt.steps.Plugin[FinishStepDataT, PluginOutcome]):
    """
    Common parent of finish plugins
    """

    # ignore[assignment]: as a base class, FinishStepData is not included in
    # FinishStepDataT.
    _data_class = FinishStepData  # type: ignore[assignment]

    # Methods ("how: ..." implementations) registered for the same step.
    _supported_methods: PluginRegistry[Method] = PluginRegistry('step.finish')

    @classmethod
    def base_command(
        cls,
        usage: str,
        method_class: Optional[type[click.Command]] = None,
    ) -> click.Command:
        """
        Create base click command (common for all finish plugins)
        """

        # Prepare general usage message for the step
        if method_class:
            usage = Finish.usage(method_overview=usage)

        # Create the command
        @click.command(cls=method_class, help=usage)
        @click.pass_context
        @option('-h', '--how', metavar='METHOD', help='Use specified method for finishing tasks.')
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
        logger: tmt.log.Logger,
    ) -> PluginOutcome:
        self.go_prolog(logger)

        return PluginOutcome()


class Finish(tmt.steps.Step):
    """
    Perform the finishing tasks

    Additional actions to be performed after the test execution has been
    completed. Counterpart of the ``prepare`` step useful for various
    cleanup or log-gathering actions.
    """

    _plugin_base_class = FinishPlugin

    @property
    def _preserved_workdir_members(self) -> set[str]:
        """
        A set of members of the step workdir that should not be removed.
        """

        return {*super()._preserved_workdir_members, 'results.yaml'}

    def wake(self) -> None:
        """
        Wake up the step (process workdir and command line)
        """

        super().wake()

        # Choose the right plugin and wake it up
        for data in self.data:
            # FIXME: cast() - see https://github.com/teemtee/tmt/issues/1599
            plugin = cast(FinishPlugin[FinishStepData], FinishPlugin.delegate(self, data=data))
            plugin.wake()
            # Add plugin only if there are data
            if not plugin.data.is_bare:
                self._phases.append(plugin)

        # Nothing more to do if already done and not asked to run again
        if self.status() == 'done' and not self.should_run_again:
            self.debug('Finish wake up complete (already done before).', level=2)
        # Save status and step data (now we know what to do)
        else:
            self.status('todo')
            self.save()

    def summary(self) -> None:
        """
        Give a concise summary
        """

        tasks = fmf.utils.listed(self.phases(), 'task')
        self.info('summary', f'{tasks} completed', 'green', shift=1)

    def go(self, force: bool = False) -> None:
        """
        Execute finishing tasks
        """

        super().go(force=force)

        # Nothing more to do if already done
        if self.status() == 'done':
            self.info('status', 'done', 'green', shift=1)
            self.summary()
            self.actions()
            return

        # Nothing to do if no guests were provisioned
        if not self.plan.provision.guests:
            self.warn("Nothing to finish, no guests provisioned.", shift=1)
            return

        if self.plan.provision.ready_guests:
            # Prepare guests
            guest_copies: list[Guest] = []

            for guest in self.plan.provision.ready_guests:
                # Create a guest copy and change its parent so that the
                # operations inside finish plugins on the guest use the
                # finish step config rather than provision step config.
                guest_copy = copy.copy(guest)
                guest_copy.inject_logger(
                    guest._logger.clone().apply_verbosity_options(**self._cli_options)
                )
                guest_copy.parent = self

                guest_copies.append(guest_copy)

            queue: PhaseQueue[FinishStepData, PluginOutcome] = PhaseQueue(
                'finish', self._logger.descend(logger_name=f'{self}.queue')
            )

            for phase in self.phases(classes=(Action, FinishPlugin)):
                if isinstance(phase, Action):
                    queue.enqueue_action(phase=phase)

                elif phase.enabled_by_when:
                    queue.enqueue_plugin(
                        phase=phase,  # type: ignore[arg-type]
                        guests=[guest for guest in guest_copies if phase.enabled_on_guest(guest)],
                    )

            results: list[PhaseResult] = []
            exceptions: list[Exception] = []

            def _record_exception(
                outcome: PluginTask[FinishStepData, PluginOutcome], exc: Exception
            ) -> None:
                outcome.logger.fail(str(exc))

                exceptions.append(exc)

            for outcome in queue.run():
                if not isinstance(outcome.phase, FinishPlugin):
                    continue

                # Possible outcomes: plugin crashed, raised an exception,
                # and that exception has been delivered to the top of the
                # phase's thread and propagated to us in the task outcome.
                #
                # Log the failure, save the exception, and add an error
                # result to represent the crash. Plugin did not return any
                # usable results, otherwise it would not have ended with
                # an exception...
                if outcome.exc:
                    _record_exception(outcome, outcome.exc)

                    results.append(
                        PhaseResult(
                            name=outcome.phase.name,
                            result=ResultOutcome.ERROR,
                            note=['Plugin raised an unhandled exception.'],
                        )
                    )

                    continue

                # Or, plugin finished successfully - not necessarily after
                # achieving its goals successfully. Save results, and if
                # plugin returned also some exceptions, do the same as above:
                # log them and save them, but do not emit any special result.
                # Plugin was alive till the very end, and returned results.
                if outcome.result:
                    results += outcome.result.results

                    if outcome.result.exceptions:
                        for exc in outcome.result.exceptions:
                            _record_exception(outcome, exc)

                        continue

            self._save_results(results)

            if exceptions:
                raise tmt.utils.GeneralError(
                    'finish step failed',
                    causes=exceptions,
                )

            # To separate "finish" from "pull" queue visually
            self.info('')

            # Pull artifacts created in the plan data directory
            # if there was at least one plugin executed
            if self.phases() and guest_copies:
                sync_with_guests(
                    self,
                    'pull',
                    PullTask(guest_copies, self.plan.data_directory, self._logger),
                    self._logger,
                )

                # To separate "finish" from "pull" queue visually
                self.info('')

            self.summary()

        # Update status and save
        self.status('done')
        self.save()
