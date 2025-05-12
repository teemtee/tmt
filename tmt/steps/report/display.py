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

PER_LEVEL_INDENT = ' ' * INDENT

DEFAULT_RESULT_HEADER_TEMPLATE = """
{{ RESULT | format_duration | style(fg="cyan") }} {{ OUTCOME | style(fg=OUTCOME_COLOR) }} {{ RESULT.name }}
{%- if CONTEXT.display_guest %} (on {{ RESULT.guest | guest_full_name }}){% endif %}
{%- if PROGRESS is defined %} {{ PROGRESS }}{% endif %}
"""  # noqa: E501

DEFAULT_RESULT_CHECK_HEADER_TEMPLATE = """
{{ RESULT | format_duration | style(fg="cyan") }} {{ OUTCOME | style(fg=OUTCOME_COLOR) }} {{ RESULT.name }} ({{ RESULT.event.value }} check)
"""  # noqa: E501

DEFAULT_SUBRESULT_HEADER_TEMPLATE = """
{{ RESULT | format_duration | style(fg="cyan") }} {{ OUTCOME | style(fg=OUTCOME_COLOR) }} {{ RESULT.name }} (subresult)
"""  # noqa: E501

DEFAULT_SUBRESULT_CHECK_HEADER_TEMPLATE = """
{{ RESULT | format_duration | style(fg="cyan") }} {{ OUTCOME | style(fg=OUTCOME_COLOR) }} {{ RESULT.name }} ({{ RESULT.event.value }} check)
"""  # noqa: E501

DEFAULT_NOTE_TEMPLATE = """
{{ "Note:" | style(fg="yellow") }} {{ NOTE_LINES.pop(0) }}
{% for line in NOTE_LINES %}
      {{ line }}
{% endfor %}
"""


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
    #: When 3 or more, log output would be printed out as well.
    verbosity: int = 0
    #: Whether guest from which results originated should be printed out.
    display_guest: bool = True

    #: Additional variables to use when rendering templates.
    variables: dict[str, Any] = simple_field(default_factory=dict[str, Any])

    result_header_template: str = DEFAULT_RESULT_HEADER_TEMPLATE
    result_check_header_template: str = DEFAULT_RESULT_CHECK_HEADER_TEMPLATE
    subresult_header_template: str = DEFAULT_SUBRESULT_HEADER_TEMPLATE
    subresult_check_header_template: str = DEFAULT_SUBRESULT_CHECK_HEADER_TEMPLATE
    note_template: str = DEFAULT_NOTE_TEMPLATE

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
                    yield f'{level * PER_LEVEL_INDENT}{line}'

    def render_note(self, note: str) -> Iterator[str]:
        """
        Render a single result note.
        """

        yield render_template(
            self.note_template,
            environment=self.environment,
            CONTEXT=self,
            NOTE_LINES=note.splitlines(),
            **self.variables,
        )

    def render_notes(self, result: BaseResult) -> Iterator[str]:
        """
        Render result notes.
        """

        for note in result.note:
            yield from self.render_note(note)

    @staticmethod
    def render_log_info(log: Path) -> Iterator[str]:
        """
        Render info about a single log.
        """

        yield f'{log.name} ({log})'

    def render_logs_info(self, result: BaseResult) -> Iterator[str]:
        """
        Render info about result logs.
        """

        if not result.log:
            return

        yield 'logs:'

        for log in result.log:
            yield from self._indent(1, self.render_log_info(self.basepath / log))

    @staticmethod
    def render_log_content(log: Path) -> Iterator[str]:
        """
        Render log info and content of a single log.
        """

        with open(log) as f:
            for line in f:
                yield f'content: {line}'

    def render_logs_content(self, result: BaseResult) -> Iterator[str]:
        """
        Render log info and content of result logs.
        """

        if not result.log:
            return

        yield 'logs (with content):'

        for log in result.log:
            yield from self._indent(1, self.render_log_info(self.basepath / log))

            if log.name == TEST_OUTPUT_FILENAME:
                yield from self._indent(2, self.render_log_content(self.basepath / log))

    def render_check_result(self, result: CheckResult, template: str) -> Iterator[str]:
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

        yield from self._indent(1, self.render_notes(result))

    def render_check_results(self, results: Iterable[CheckResult], template: str) -> Iterator[str]:
        """
        Render test check results.
        """

        for result in results:
            yield from self.render_check_result(result, template)

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
            **self.variables,
        )

        yield from self._indent(1, self.render_notes(result))

        # With verbosity increased to `-vvv` or more, display content of the main test log
        if self.verbosity > 2:
            yield from self._indent(1, self.render_logs_content(result))

        # With verbosity increased to `-vv`, display the list of logs
        elif self.verbosity > 1:
            yield from self._indent(1, self.render_logs_info(result))

        yield from self._indent(
            1, self.render_check_results(result.check, self.subresult_check_header_template)
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

        yield from self._indent(1, self.render_notes(result))

        # With verbosity increased to `-vvv` or more, display content of the main test log
        if self.verbosity > 2:
            yield from self._indent(1, self.render_logs_content(result))

        # With verbosity increased to `-vv`, display the list of logs
        elif self.verbosity > 1:
            yield from self._indent(1, self.render_logs_info(result))

        yield from self._indent(
            1, self.render_check_results(result.check, self.result_check_header_template)
        )

        yield from self._indent(1, self.render_subresults(result.subresult))

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
