import tmt
import tmt.steps
import tmt.steps.report
from tmt.steps.execute import TEST_OUTPUT_FILENAME
from tmt.utils import Path


@tmt.steps.provides_method('display')
class ReportDisplay(tmt.steps.report.ReportPlugin):
    """
    Show test results on the terminal

    Give a concise summary of test results directly on the terminal.
    List individual test results in verbose mode.
    """

    def details(self, result: tmt.Result, verbosity: int) -> None:
        """ Print result details based on the verbose mode """
        # -v prints just result + name
        # -vv prints path to logs
        # -vvv prints also test output
        self.verbose(result.show(), shift=1)
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
        for result in self.step.plan.execute.results():
            self.details(result, self.opt('verbose'))
