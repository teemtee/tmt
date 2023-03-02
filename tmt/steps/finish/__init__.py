import copy
import dataclasses
from typing import TYPE_CHECKING, Any, List, Optional, Type, cast

import click
import fmf

import tmt
import tmt.steps
from tmt.steps import Action, Method
from tmt.utils import GeneralError

if TYPE_CHECKING:
    import tmt.cli


@dataclasses.dataclass
class FinishStepData(tmt.steps.WhereableStepData, tmt.steps.StepData):
    pass


class FinishPlugin(tmt.steps.Plugin):
    """ Common parent of finish plugins """

    _data_class = FinishStepData

    # List of all supported methods aggregated from all plugins of the same step.
    _supported_methods: List[Method] = []

    @classmethod
    def base_command(
            cls,
            usage: str,
            method_class: Optional[Type[click.Command]] = None) -> click.Command:
        """ Create base click command (common for all finish plugins) """

        # Prepare general usage message for the step
        if method_class:
            usage = Finish.usage(method_overview=usage)

        # Create the command
        @click.command(cls=method_class, help=usage)
        @click.pass_context
        @click.option(
            '-h', '--how', metavar='METHOD',
            help='Use specified method for finishing tasks.')
        def finish(context: 'tmt.cli.Context', **kwargs: Any) -> None:
            context.obj.steps.add('finish')
            Finish._save_context(context)

        return finish


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

    def wake(self) -> None:
        """ Wake up the step (process workdir and command line) """
        super().wake()

        # Choose the right plugin and wake it up
        for data in self.data:
            # FIXME: cast() - see https://github.com/teemtee/tmt/issues/1599
            plugin = cast(FinishPlugin, FinishPlugin.delegate(self, data=data))
            plugin.wake()
            # Add plugin only if there are data
            if not plugin.data.is_bare:
                self._phases.append(plugin)

        # Nothing more to do if already done
        if self.status() == 'done':
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

    def go(self) -> None:
        """ Execute finishing tasks """
        super().go()

        # Nothing more to do if already done
        if self.status() == 'done':
            self.info('status', 'done', 'green', shift=1)
            self.summary()
            self.actions()
            return

        # Go and execute each plugin on all guests
        for guest in self.plan.provision.guests():
            # Create a guest copy and change its parent so that the
            # operations inside finish plugins on the guest use the
            # finish step config rather than provision step config.
            guest_copy = copy.copy(guest)
            guest_copy._logger = guest._logger.clone().apply_verbosity_options(**self._options)
            guest_copy.parent = self
            for phase in self.phases(classes=(Action, FinishPlugin)):
                if isinstance(phase, Action):
                    phase.go()

                elif isinstance(phase, FinishPlugin):
                    # TODO: re-injecting the logger already given to the guest,
                    # with multihost support heading our way this will change
                    # to be not so trivial.
                    phase.go(guest=guest_copy, logger=guest_copy._logger)

                else:
                    raise GeneralError(f'Unexpected phase in finish step: {phase}')

            # Pull artifacts created in the plan data directory
            # if there was at least one plugin executed
            if self.phases():
                guest_copy.pull(self.plan.data_directory)

        # Stop and remove provisioned guests
        for guest in self.plan.provision.guests():
            guest.stop()
            guest.remove()

        # Prune all irrelevant files and dirs
        assert self.plan.my_run is not None
        if not (self.plan.my_run.opt('keep') or self.opt('dry')):
            self.plan.prune()

        # Give a summary, update status and save
        self.summary()
        self.status('done')
        self.save()
