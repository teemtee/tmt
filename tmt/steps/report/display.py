import dataclasses

import tmt
import tmt.steps
import tmt.steps.report
from tmt.steps.execute import TEST_OUTPUT_FILENAME
from tmt.utils import Path, field


@dataclasses.dataclass
class ReportDisplayData(tmt.steps.report.ReportStepData):
    display_guest: str = field(
        default='auto',
        option='--display-guest',
        metavar='auto|always|never',
        choices=['auto', 'always', 'never'],
        help="When to display full guest name in report:"
             " when more than a single guest was involved (default), always, or never."
        )


@tmt.steps.provides_method('display')
class ReportDisplay(tmt.steps.report.ReportPlugin):
    """
    Show test results on the terminal

    Give a concise summary of test results directly on the terminal.
    List individual test results in verbose mode.
    """

    _data_class = ReportDisplayData

    def details(self, result: tmt.Result, verbosity: int, display_guest: bool) -> None:
        """ Print result details based on the verbose mode """
        # -v prints just result + name
        # -vv prints path to logs
        # -vvv prints also test output
        self.verbose(result.show(display_guest=display_guest), shift=1)
        if verbosity == 1:
            return
        # -vv and more follows
        # TODO: are we sure it cannot be None?
        assert self.step.plan.execute.workdir is not None
        for _log_file in result.log:
            # TODO: this should be done already, result.log should use Path instead
            # of strings, but result.log structure is not so clear right now.
            log_file = Path(_log_file)
            log_name = log_file.name
            full_path = self.step.plan.execute.workdir / log_file
            # List path to logs (-vv and more)
            self.verbose(log_name, str(full_path), color='yellow', shift=2)
            # Show the whole test output (-vvv and more)
            if verbosity > 2 and log_name == TEST_OUTPUT_FILENAME:
                self.verbose(
                    'content', self.read(full_path), color='yellow', shift=2)

    def go(self) -> None:
        """ Discover available tests """
        super().go()
        # Show individual test results only in verbose mode
        if not self.opt('verbose'):
            return

        if self.get('display-guest') == 'always':
            display_guest = True

        elif self.get('display-guest') == 'never':
            display_guest = False

        else:
            seen_guests = {
                result.guest.name
                for result in self.step.plan.execute.results() if result.guest.name is not None
                }

            display_guest = len(seen_guests) > 1

        for result in self.step.plan.execute.results():
            self.details(result, self.opt('verbose'), display_guest)
