from collections.abc import Iterable, Iterator
from typing import Any, Optional

import tmt
import tmt.log
import tmt.steps
import tmt.steps.report
from tmt.container import container, field, simple_field
from tmt.result import (
    RESULT_OUTCOME_COLORS,
    BaseResult,
    CheckResult,
    Result,
    ResultOutcome,
    SubResult,
)
from tmt.steps.execute import TEST_OUTPUT_FILENAME
from tmt.utils import INDENT, Path
from tmt.utils.templates import default_template_environment, render_template

# How much test and test check info should be shifted to the right in the output.
# We want tests to be shifted by one extra level, with their checks shifted by
# yet another level.
RESULT_SHIFT = 0
RESULT_CHECK_SHIFT = 1
SUBRESULT_SHIFT = RESULT_CHECK_SHIFT
SUBRESULT_CHECK_SHIFT = SUBRESULT_SHIFT + 1

NOTE_SHIFT = 1
NOTE_PREFIX = (NOTE_SHIFT * INDENT) * ' '

DEFAULT_RESULT_HEADER_TEMPLATE = """
{{ RESULT | format_duration | style(fg="cyan") }} {{ OUTCOME | style(fg=OUTCOME_COLOR) }} {{ RESULT.name }}
{%- if CONTEXT.display_guest %} (on {{ RESULT.guest | guest_full_name }}){% endif %}
{%- if PROGRESS is defined %} {{ PROGRESS }}{% endif %}
"""  # noqa: E501

DEFAULT_RESULT_CHECK_HEADER_TEMPLATE = """
{{ RESULT | format_duration | style(fg="cyan") }}{{ '\u00a0' * 4 }}{{ OUTCOME | style(fg=OUTCOME_COLOR) }} {{ RESULT.name }} ({{ RESULT.event.value }} check)
"""  # noqa: E501

DEFAULT_SUBRESULT_HEADER_TEMPLATE = """
{{ RESULT | format_duration | style(fg="cyan") }}{{ '\u00a0' * 4 }}{{ OUTCOME | style(fg=OUTCOME_COLOR) }} {{ RESULT.name }}
{%- if CONTEXT.display_guest %} (on {{ RESULT.guest | guest_full_name }}){% endif %}
"""  # noqa: E501

DEFAULT_SUBRESULT_CHECK_HEADER_TEMPLATE = """
{{ RESULT | format_duration | style(fg="cyan") }}{{ '\u00a0' * 8 }}{{ OUTCOME | style(fg=OUTCOME_COLOR) }} {{ RESULT.name }} ({{ RESULT.event.value }} check)
"""  # noqa: E501


@container
class ReportDisplayData(tmt.steps.report.ReportStepData):
    display_guest: str = field(
        default='auto',
        option='--display-guest',
        metavar='auto|always|never',
        choices=['auto', 'always', 'never'],
        help="""
             When to display full guest name in report: when more than a single guest was involved
             (default), always, or never.
             """,
    )


@container
class ResultRenderer:
    """
    A rendering engine for turning results into printable representation.
    """

    #: A base path for all log references.
    basepath: Path

    logger: tmt.log.Logger

    #: Default shift of all rendered lines.
    shift: int

    #: When 2 or more, log info - name and path - would be printed out.
    #: When 3 or more, og output would be printed out as well.
    verbosity: int = 0
    #: Whether guest from which results originated should be printed out.
    display_guest: bool = True

    #: Additional variables to use when rendering templates.
    variables: dict[str, Any] = simple_field(default_factory=dict)

    result_header_template: str = DEFAULT_RESULT_HEADER_TEMPLATE
    result_check_header_template: str = DEFAULT_RESULT_CHECK_HEADER_TEMPLATE
    subresult_header_template: str = DEFAULT_SUBRESULT_HEADER_TEMPLATE
    subresult_check_header_template: str = DEFAULT_SUBRESULT_CHECK_HEADER_TEMPLATE

    def __post_init__(self) -> None:
        self.environment = default_template_environment()

    @staticmethod
    def _indent(level: int, iterable: Iterable[str]) -> Iterator[str]:
        """
        Indent each string from iterable by the given indentation levels.
        """

        for item in iterable:
            if not item:
                yield item

            else:
                for line in item.splitlines():
                    yield f'{(INDENT * level) * " "}{line}'

    @staticmethod
    def render_note(note: str) -> Iterator[str]:
        """
        Render a single result note.
        """

        note_lines = note.splitlines()

        yield f'{NOTE_PREFIX}* Note: {note_lines.pop(0)}'

        for note_line in note_lines:
            yield f'{NOTE_PREFIX}        {note_line}'

    @classmethod
    def render_notes(cls, result: BaseResult) -> Iterator[str]:
        """
        Render result notes.
        """

        for note in result.note:
            yield from cls.render_note(note)

    @staticmethod
    def render_log_info(log: Path) -> Iterator[str]:
        """
        Render info about a single log.
        """

        yield f'{log.name} ({log})'

    def render_logs_info(self, result: BaseResult, shift: int) -> Iterator[str]:
        """
        Render info about result logs.
        """

        yield from self._indent(shift, ['logs:'])

        for log in result.log:
            yield from self._indent(shift + 1, self.render_log_info(self.basepath / log))

    @staticmethod
    def render_log_content(log: Path) -> Iterator[str]:
        """
        Render log info and content of a single log.
        """

        with open(log) as f:
            yield from f.readlines()

    def render_logs_content(self, result: BaseResult, shift: int) -> Iterator[str]:
        """
        Render log info and content of result logs.
        """

        yield from self._indent(shift, ['logs (with content):'])

        for log in result.log:
            yield from self._indent(shift + 1, self.render_log_info(self.basepath / log))

            if log.name == TEST_OUTPUT_FILENAME:
                yield from self._indent(shift + 2, self.render_log_content(self.basepath / log))

    def render_check_result(self, result: CheckResult, shift: int, template: str) -> Iterator[str]:
        """
        Render a single test check result.
        """

        outcome = 'errr' if result.result == ResultOutcome.ERROR else result.result.value

        yield render_template(
            template,
            environment=self.environment,
            CONTEXT=self,
            RESULT=result,
            OUTCOME=outcome,
            OUTCOME_COLOR=RESULT_OUTCOME_COLORS[result.result],
            **self.variables,
        )

        yield from self._indent(shift + 1, self.render_notes(result))

    def render_check_results(
        self, results: Iterable[CheckResult], shift: int, template: str
    ) -> Iterator[str]:
        """
        Render test check results.
        """

        for result in results:
            yield from self.render_check_result(result, shift, template)

    def render_subresult(self, result: SubResult) -> Iterator[str]:
        """
        Render a single subresult.
        """

        outcome = 'errr' if result.result == ResultOutcome.ERROR else result.result.value

        yield render_template(
            self.subresult_header_template,
            environment=self.environment,
            CONTEXT=self,
            RESULT=result,
            OUTCOME=outcome,
            OUTCOME_COLOR=RESULT_OUTCOME_COLORS[result.result],
            INDENT=INDENT * ' ',
            **self.variables,
        )

        yield from self._indent(SUBRESULT_SHIFT + 1, self.render_notes(result))

        # With verbosity increased to `-vvv` or more, display content of the main test log
        if self.verbosity > 2:
            yield from self.render_logs_content(result, SUBRESULT_SHIFT + 1)

        # With verbosity increased to `-vv`, display the list of logs
        elif self.verbosity > 1:
            yield from self.render_logs_info(result, SUBRESULT_SHIFT + 1)

        yield from self.render_check_results(
            result.check, SUBRESULT_CHECK_SHIFT, self.subresult_check_header_template
        )

    def render_subresults(self, results: Iterable[SubResult]) -> Iterator[str]:
        """
        Render subresults.
        """

        for result in results:
            yield from self.render_subresult(result)

    def render_result(self, result: Result) -> Iterator[str]:
        """
        Render a single test result.
        """

        outcome = 'errr' if result.result == ResultOutcome.ERROR else result.result.value

        yield render_template(
            self.result_header_template,
            environment=self.environment,
            CONTEXT=self,
            RESULT=result,
            OUTCOME=outcome,
            OUTCOME_COLOR=RESULT_OUTCOME_COLORS[result.result],
            **self.variables,
        )

        yield from self._indent(RESULT_SHIFT + 1, self.render_notes(result))

        # With verbosity increased to `-vvv` or more, display content of the main test log
        if self.verbosity > 2:
            yield from self.render_logs_content(result, RESULT_SHIFT + 1)

        # With verbosity increased to `-vv`, display the list of logs
        elif self.verbosity > 1:
            yield from self.render_logs_info(result, RESULT_SHIFT + 1)

        yield from self.render_check_results(
            result.check, RESULT_CHECK_SHIFT, self.result_check_header_template
        )
        yield from self.render_subresults(result.subresult)

    def render_results(self, results: Iterable[Result]) -> Iterator[str]:
        """
        Render test results.
        """

        for result in results:
            yield from self.render_result(result)

    def print_result(self, result: Result) -> None:
        """
        Print out a single rendered test result.
        """

        for line in self.render_result(result):
            self.logger.verbose(line, shift=self.shift)

    def print_results(self, results: Iterable[Result]) -> None:
        """
        Print out rendered test results.
        """

        for line in self.render_results(results):
            self.logger.verbose(line, shift=self.shift)


@tmt.steps.provides_method('display')
class ReportDisplay(tmt.steps.report.ReportPlugin[ReportDisplayData]):
    """
    Show test results on the terminal.

    Give a concise summary of test results directly on the terminal.
    Allows to select the desired level of verbosity.

    .. code-block:: yaml

        tmt run -l report        # overall summary only
        tmt run -l report -v     # individual test results
        tmt run -l report -vv    # show full paths to logs
        tmt run -l report -vvv   # provide complete test output
    """

    _data_class = ReportDisplayData

    def go(self, *, logger: Optional[tmt.log.Logger] = None) -> None:
        """
        Discover available tests
        """

        super().go(logger=logger)
        # Show individual test results only in verbose mode
        if not self.verbosity_level:
            return

        if self.data.display_guest == 'always':
            display_guest = True

        elif self.data.display_guest == 'never':
            display_guest = False

        else:
            seen_guests = {result.guest.name for result in self.step.plan.execute.results()}

            display_guest = len(seen_guests) > 1

        assert self.step.plan.execute.workdir is not None

        ResultRenderer(
            basepath=self.step.plan.execute.workdir,
            logger=self._logger,
            shift=1,
            verbosity=self.verbosity_level,
            display_guest=display_guest,
        ).print_results(self.step.plan.execute.results())
