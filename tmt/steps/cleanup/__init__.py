import copy
from typing import TYPE_CHECKING, Any, Optional, TypeVar, cast

import click
import fmf
import fmf.utils

import tmt
import tmt.log
import tmt.steps
import tmt.utils
from tmt.container import container
from tmt.options import option
from tmt.plugins import PluginRegistry
from tmt.result import PhaseResult, ResultOutcome
from tmt.steps import (
    Method,
    PhaseQueue,
    PluginOutcome,
    PluginTask,
)
from tmt.steps.provision import Guest

if TYPE_CHECKING:
    import tmt.cli


@container
class CleanupStepData(tmt.steps.StepData):
    pass


CleanupStepDataT = TypeVar('CleanupStepDataT', bound=CleanupStepData)


class CleanupPlugin(tmt.steps.Plugin[CleanupStepDataT, PluginOutcome]):
    """
    Common parent of cleanup plugins
    """

    # ignore[assignment]: as a base class, CleanupStepData is not included in
    # CleanupStepDataT.
    _data_class = CleanupStepData  # type: ignore[assignment]

    # Methods ("how: ..." implementations) registered for the same step.
    _supported_methods: PluginRegistry[Method] = PluginRegistry('step.cleanup')

    # Internal cleanup plugin is the default implementation
    how = 'tmt'

    @classmethod
    def base_command(
        cls,
        usage: str,
        method_class: Optional[type[click.Command]] = None,
    ) -> click.Command:
        """
        Create base click command (common for all cleanup plugins)
        """

        # Prepare general usage message for the step
        if method_class:
            usage = Cleanup.usage(method_overview=usage)

        # Create the command
        @click.command(cls=method_class, help=usage)
        @click.pass_context
        @option('-h', '--how', metavar='METHOD', help='Use specified method for cleanup tasks.')
        @tmt.steps.PHASE_OPTIONS
        def cleanup(context: 'tmt.cli.Context', **kwargs: Any) -> None:
            context.obj.steps.add('cleanup')
            Cleanup.store_cli_invocation(context)

        return cleanup

    def go(
        self,
        *,
        guest: 'Guest',
        environment: Optional[tmt.utils.Environment] = None,
        logger: tmt.log.Logger,
    ) -> PluginOutcome:
        self.go_prolog(logger)

        return PluginOutcome()


class Cleanup(tmt.steps.Step):
    """
    Clean up the provisioned guests and prune the workdir.

    Stop and remove all guests after the testing is finished. Also takes
    care of pruning irrelevant files and directories from the workdir so
    that we do not eat up unnecessary disk space after everything is
    done.

    Note that the ``cleanup`` step is also run when any of the previous
    steps failed (for example when the environment preparation was not
    successful) so that provisioned systems are not kept running and
    consuming resources.
    """

    # Internal cleanup plugin is the default implementation
    DEFAULT_HOW = 'tmt'

    _plugin_base_class = CleanupPlugin

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
            plugin = cast(CleanupPlugin[CleanupStepData], CleanupPlugin.delegate(self, data=data))
            plugin.wake()
            self._phases.append(plugin)

        # Nothing more to do if already done and not asked to run again
        if self.status() == 'done' and not self.should_run_again:
            self.debug('Cleanup wake up complete (already done before).', level=2)
        # Save status and step data (now we know what to do)
        else:
            self.status('todo')
            self.save()

    def summary(self) -> None:
        """
        Give a concise summary
        """

        # TODO Provide a number of stopped guests
        tasks = fmf.utils.listed(self.phases(), 'task')
        self.info('summary', f'{tasks} completed', 'green', shift=1)

    def go(self, force: bool = False) -> None:
        """
        Execute cleanup tasks
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
            self.warn("Nothing to cleanup, no guests provisioned.", shift=1)
            return

        # Prepare guest copies
        guest_copies: list[Guest] = []

        for guest in self.plan.provision.guests:
            # Create a guest copy and change its parent so that the
            # operations inside cleanup plugins on the guest use the
            # cleanup step config rather than provision step config.
            guest_copy = copy.copy(guest)
            guest_copy.inject_logger(
                guest._logger.clone().apply_verbosity_options(**self._cli_options)
            )
            guest_copy.parent = self

            guest_copies.append(guest_copy)

        # Prepare the queue
        queue: PhaseQueue[CleanupStepData, PluginOutcome] = PhaseQueue(
            'cleanup', self._logger.descend(logger_name=f'{self}.queue')
        )

        # Pick only the CleanupPlugin phases, Action phases are not
        # expected in the cleanup step
        phases: list[CleanupPlugin[CleanupStepData]] = self.phases(classes=(CleanupPlugin,))

        for phase in phases:
            if phase.enabled_by_when:
                queue.enqueue_plugin(
                    phase=phase,
                    guests=[guest for guest in guest_copies if phase.enabled_on_guest(guest)],
                )

        results: list[PhaseResult] = []
        exceptions: list[Exception] = []

        def _record_exception(
            outcome: PluginTask[CleanupStepData, PluginOutcome], exc: Exception
        ) -> None:
            outcome.logger.fail(str(exc))

            exceptions.append(exc)

        # Run the queue
        for outcome in queue.run():
            if not isinstance(outcome.phase, CleanupPlugin):
                continue

            # At this point, outcome must be a PluginTask since
            # ActionTask would have Action phase
            assert isinstance(outcome, PluginTask)

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
            if outcome.result and outcome.result.exceptions:
                for exc in outcome.result.exceptions:
                    _record_exception(outcome, exc)

                continue

        if exceptions:
            raise tmt.utils.GeneralError('cleanup step failed', causes=exceptions)

        # Prune all irrelevant files and dirs
        assert self.plan.my_run is not None
        if self.is_dry_run:
            self.debug("Nothing to prune in dry mode.", level=3)
        elif self.plan.my_run.opt('keep'):
            self.verbose("Skipping workdir prune as requested.", level=2)
        else:
            self.plan.prune()

        self.summary()

        # Update status and save
        self.status('done')
        self.save()
