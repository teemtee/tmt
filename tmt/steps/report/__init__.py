import dataclasses
from typing import TYPE_CHECKING, Any, Optional, TypeVar, Union, cast

import click

import tmt
import tmt.plugins
import tmt.steps
from tmt.options import option
from tmt.plugins import PluginRegistry
from tmt.steps import Action

if TYPE_CHECKING:
    import tmt.cli


@dataclasses.dataclass
class ReportStepData(tmt.steps.StepData):
    pass


ReportStepDataT = TypeVar('ReportStepDataT', bound=ReportStepData)


class ReportPlugin(tmt.steps.GuestlessPlugin[ReportStepDataT]):
    """ Common parent of report plugins """

    # ignore[assignment]: as a base class, ReportStepData is not included in
    # ReportStepDataT.
    _data_class = ReportStepData  # type: ignore[assignment]

    # Default implementation for report is display
    how = 'display'

    # Methods ("how: ..." implementations) registered for the same step.
    _supported_methods: PluginRegistry[tmt.steps.Method] = PluginRegistry()

    @classmethod
    def base_command(
            cls,
            usage: str,
            method_class: Optional[type[click.Command]] = None) -> click.Command:
        """ Create base click command (common for all report plugins) """

        # Prepare general usage message for the step
        if method_class:
            usage = Report.usage(method_overview=usage)

        # Create the command
        @click.command(cls=method_class, help=usage)
        @click.pass_context
        @option(
            '-h', '--how', metavar='METHOD',
            help='Use specified method for results reporting.')
        @tmt.steps.PHASE_OPTIONS
        def report(context: 'tmt.cli.Context', **kwargs: Any) -> None:
            context.obj.steps.add('report')
            Report.store_cli_invocation(context)

        return report


class Report(tmt.steps.Step):
    """ Provide test results overview and send reports. """

    # Default implementation for report is display
    DEFAULT_HOW = 'display'

    _plugin_base_class = ReportPlugin

    def wake(self) -> None:
        """ Wake up the step (process workdir and command line) """
        super().wake()

        # Choose the right plugin and wake it up
        for data in self.data:
            # FIXME: cast() - see https://github.com/teemtee/tmt/issues/1599
            plugin = cast(
                ReportPlugin[ReportStepData],
                ReportPlugin.delegate(self, data=data))
            plugin.wake()
            self._phases.append(plugin)

        # Nothing more to do if already done and not asked to run again
        if self.status() == 'done' and not self.should_run_again:
            self.debug(
                'Report wake up complete (already done before).', level=2)
        # Save status and step data (now we know what to do)
        else:
            self.status('todo')
            self.save()

    def summary(self) -> None:
        """ Give a concise report summary """
        summary = tmt.result.Result.summary(self.plan.execute.results())
        self.info('summary', summary, 'green', shift=1)

    def go(self, force: bool = False) -> None:
        """ Report the results """
        super().go(force=force)

        # Nothing more to do if already done
        if self.status() == 'done':
            self.info('status', 'done', 'green', shift=1)
            self.summary()
            self.actions()
            return

        # Perform the reporting
        for phase in self.phases(classes=(Action, ReportPlugin)):
            # TODO: I don't understand this, but mypy seems to be confused about the type
            # of `phase`. Mypy in my Code reports correct `Action | ReportPlugin` union,
            # but pre-commit's mypy sees `Phase` - which should not be the right answer
            # since `classes` is clearly not `None`. Adding `cast()` to overcome this
            # because I can't find the actual error :/
            cast(Union[Action, ReportPlugin[ReportStepData]], phase).go()

        # Give a summary, update status and save
        self.summary()
        self.status('done')
        self.save()
