import enum
from typing import TYPE_CHECKING, Any, Callable, Optional, cast

import fmf
import fmf.utils

import tmt.container
import tmt.identifier
import tmt.log
import tmt.utils
from tmt.checks import CheckEvent, CheckResultInterpret
from tmt.container import SerializableContainer, container, field
from tmt.utils import GeneralError, Path
from tmt.utils.themes import style

if TYPE_CHECKING:
    import tmt.base
    import tmt.steps.execute

# Extra keys used for identification in Result class
EXTRA_RESULT_IDENTIFICATION_KEYS = ['extra-nitrate', 'extra-task']


class ResultOutcome(enum.Enum):
    PASS = 'pass'
    FAIL = 'fail'
    INFO = 'info'
    WARN = 'warn'
    ERROR = 'error'
    SKIP = 'skip'
    PENDING = 'pending'

    @classmethod
    def from_spec(cls, spec: str) -> 'ResultOutcome':
        try:
            return ResultOutcome(spec)
        except ValueError:
            raise tmt.utils.SpecificationError(f"Invalid partial custom result '{spec}'.")

    @staticmethod
    def reduce(outcomes: list['ResultOutcome']) -> 'ResultOutcome':
        """
        Reduce several result outcomes into a single outcome

        Convert multiple outcomes into a single one by picking the
        worst. This is used when aggregating several test or check
        results to present a single value to the user.
        """

        outcomes_by_severity = (
            ResultOutcome.ERROR,
            ResultOutcome.FAIL,
            ResultOutcome.WARN,
            ResultOutcome.PASS,
            ResultOutcome.INFO,
            ResultOutcome.SKIP,
            ResultOutcome.PENDING,
        )

        for outcome in outcomes_by_severity:
            if outcome in outcomes:
                return outcome

        raise GeneralError("No result outcome found to reduce.")


# Cannot subclass enums :/
# https://docs.python.org/3/library/enum.html#restricted-enum-subclassing
class ResultInterpret(enum.Enum):
    # These are "inherited" from ResultOutcome
    PASS = 'pass'
    FAIL = 'fail'
    INFO = 'info'
    WARN = 'warn'
    ERROR = 'error'

    # Special interpret values
    RESPECT = 'respect'
    XFAIL = 'xfail'
    CUSTOM = 'custom'
    RESTRAINT = 'restraint'

    @classmethod
    def is_result_outcome(cls, value: 'ResultInterpret') -> bool:
        return value.name in list(ResultOutcome.__members__.keys())

    @classmethod
    def from_spec(cls, spec: str) -> 'ResultInterpret':
        try:
            return ResultInterpret(spec)
        except ValueError:
            raise tmt.utils.SpecificationError(f"Invalid result interpretation '{spec}'.")

    @classmethod
    def normalize(
        cls,
        key_address: str,
        value: Any,
        logger: tmt.log.Logger,
    ) -> 'ResultInterpret':
        if isinstance(value, ResultInterpret):
            return value

        if isinstance(value, str):
            return cls.from_spec(value)

        raise tmt.utils.SpecificationError(
            f"Invalid result interpretation '{value}' at {key_address}."
        )


RESULT_OUTCOME_COLORS: dict[ResultOutcome, str] = {
    ResultOutcome.PASS: 'green',
    ResultOutcome.FAIL: 'red',
    ResultOutcome.INFO: 'blue',
    ResultOutcome.WARN: 'yellow',
    ResultOutcome.ERROR: 'magenta',
    # TODO (happz) make sure the color is visible for all terminals
    ResultOutcome.SKIP: 'bright_black',
    ResultOutcome.PENDING: 'cyan',
}


#: A type of collection IDs tracked for a single result.
ResultIds = dict[str, Optional[str]]

#: Raw result as written in a YAML file. A dictionary, but for now
#: the actual keys are not important.
RawResult = Any


@container
class ResultGuestData(SerializableContainer):
    """
    Describes what tmt knows about a guest the result was produced on
    """

    name: str = f'{tmt.utils.DEFAULT_NAME}-0'
    role: Optional[str] = None
    primary_address: Optional[str] = None

    @classmethod
    def from_test_invocation(
        cls, *, invocation: 'tmt.steps.execute.TestInvocation'
    ) -> 'ResultGuestData':
        """
        Create a guest data for a result from a test invocation.

        A helper for extracting interesting guest data from a given test
        invocation.

        :param invocation: a test invocation capturing the test run and results.
        """

        return ResultGuestData(
            name=invocation.guest.name,
            role=invocation.guest.role,
            primary_address=invocation.guest.primary_address,
        )


# This needs to be a stand-alone function because of the import of `tmt.base`.
# It cannot be imported on module level because of circular dependency.
def _unserialize_fmf_id(serialized: 'tmt.base._RawFmfId') -> 'tmt.base.FmfId':
    from tmt.base import FmfId

    return FmfId.from_spec(serialized)


@container
class BaseResult(SerializableContainer):
    """
    Describes what tmt knows about a result
    """

    name: str
    result: ResultOutcome = field(
        default=ResultOutcome.PASS,
        serialize=lambda result: result.value,
        unserialize=ResultOutcome.from_spec,
    )
    original_result: ResultOutcome = field(
        default=ResultOutcome.PASS,
        serialize=lambda result: result.value,
        unserialize=ResultOutcome.from_spec,
    )
    note: list[str] = field(
        default_factory=cast(Callable[[], list[str]], list),
        unserialize=lambda value: [] if value is None else value,
    )
    log: list[Path] = field(
        default_factory=cast(Callable[[], list[Path]], list),
        serialize=lambda logs: [str(log) for log in logs],
        unserialize=lambda value: [Path(log) for log in value],
    )

    start_time: Optional[str] = None
    end_time: Optional[str] = None
    duration: Optional[str] = None

    def __post_init__(self) -> None:
        self.original_result = self.result

    def show(self) -> str:
        """
        Return a nicely colored result with test name (and note)
        """

        result = 'errr' if self.result == ResultOutcome.ERROR else self.result.value

        components: list[str] = [
            style(result, fg=RESULT_OUTCOME_COLORS[self.result]),
            self.name,
        ]

        if self.note:
            components.append(f'({self.printable_note})')

        return ' '.join(components)

    @property
    def printable_note(self) -> str:
        return ', '.join(self.note)

    @property
    def failure_logs(self) -> list[Path]:
        """
        Return paths to all failure logs from the result
        """

        if self.result not in (ResultOutcome.FAIL, ResultOutcome.ERROR, ResultOutcome.WARN):
            return []

        return list(
            {path for path in self.log if path.name == tmt.steps.execute.TEST_FAILURES_FILENAME}
        )


@container
class CheckResult(BaseResult):
    """
    Describes what tmt knows about a single test check result
    """

    event: CheckEvent = field(
        default=CheckEvent.BEFORE_TEST,
        serialize=lambda event: event.value,
        unserialize=CheckEvent.from_spec,
    )

    def to_subcheck(self) -> 'SubCheckResult':
        """
        Convert check to a tmt SubCheckResult
        """

        return SubCheckResult.from_serialized(self.to_serialized())


@container
class SubCheckResult(CheckResult):
    """
    Describes what tmt knows about a single subtest check result.

    It does not contain any additional fields; it simply defines a type to
    easily differentiate between a :py:class:`tmt.result.CheckResult` and a
    ``CheckResult`` located within a result phase.
    """


@container
class SubResult(BaseResult):
    """
    Describes what tmt knows about a single test subresult
    """

    check: list[SubCheckResult] = field(
        default_factory=cast(Callable[[], list[SubCheckResult]], list),
        serialize=lambda results: [result.to_serialized() for result in results],
        unserialize=lambda serialized: [
            SubCheckResult.from_serialized(check) for check in serialized
        ],
    )

    @property
    def failure_logs(self) -> list[Path]:
        """
        Return paths to all failure logs from the result
        """

        failure_logs = super().failure_logs
        for check in self.check:
            failure_logs += check.failure_logs
        return list(set(failure_logs))


@container
class PhaseResult(BaseResult):
    """
    Describes what tmt knows about result of individual phases, e.g. prepare ansible
    """


@container
class Result(BaseResult):
    """
    Describes what tmt knows about a single test result
    """

    serial_number: int = 0
    fmf_id: Optional['tmt.base.FmfId'] = field(
        default=cast(Optional['tmt.base.FmfId'], None),
        serialize=lambda fmf_id: fmf_id.to_minimal_spec() if fmf_id is not None else {},
        unserialize=_unserialize_fmf_id,
    )
    context: tmt.utils.FmfContext = field(
        default_factory=tmt.utils.FmfContext,
        serialize=lambda context: context.to_spec(),
        unserialize=lambda serialized: tmt.utils.FmfContext(serialized),
    )
    ids: ResultIds = field(default_factory=cast(Callable[[], ResultIds], dict))
    guest: ResultGuestData = field(
        default_factory=ResultGuestData,
        serialize=lambda value: value.to_serialized(),
        unserialize=lambda serialized: ResultGuestData.from_serialized(serialized),
    )

    subresult: list[SubResult] = field(
        default_factory=cast(Callable[[], list[SubResult]], list),
        serialize=lambda results: [result.to_serialized() for result in results],
        unserialize=lambda serialized: [
            SubResult.from_serialized(subresult) for subresult in serialized
        ],
    )

    check: list[CheckResult] = field(
        default_factory=cast(Callable[[], list[CheckResult]], list),
        serialize=lambda results: [result.to_serialized() for result in results],
        unserialize=lambda serialized: [
            CheckResult.from_serialized(check) for check in serialized
        ],
    )
    data_path: Optional[Path] = field(
        default=cast(Optional[Path], None),
        serialize=lambda path: None if path is None else str(path),
        unserialize=lambda value: None if value is None else Path(value),
    )

    @classmethod
    def from_test_invocation(
        cls,
        *,
        invocation: 'tmt.steps.execute.TestInvocation',
        result: ResultOutcome,
        note: Optional[list[str]] = None,
        ids: Optional[ResultIds] = None,
        log: Optional[list[Path]] = None,
        subresult: Optional[list[SubResult]] = None,
    ) -> 'Result':
        """
        Create a result from a test invocation.

        A helper for extracting interesting data from a given test invocation.
        While it's perfectly possible to go directly through ``Result(...)``,
        most of the time a result stems from a particular test invocation
        captured by a :py:class:`TestInvocation` instance.

        :param invocation: a test invocation capturing the test run and results.
        :param result: actual test outcome. It will be interpreted according to
            :py:attr:`Test.result` key (see
            https://tmt.readthedocs.io/en/stable/spec/tests.html#result).
        :param note: optional result notes.
        :param ids: additional test IDs. They will be added to IDs extracted
            from the test.
        :param log: optional list of test logs.
        """

        # Saving identifiable information for each test case so we can match them
        # to Polarion/Nitrate/other cases and report run results there
        # TODO: would an exception be better? Can test.id be None?
        ids = ids or {}
        default_ids: ResultIds = {tmt.identifier.ID_KEY: invocation.test.id}

        for key in EXTRA_RESULT_IDENTIFICATION_KEYS:
            value: Any = cast(Any, invocation.test.node.get(key))

            default_ids[key] = None if value is None else str(value)

        default_ids.update(ids)
        ids = default_ids

        _result = Result(
            name=invocation.test.name,
            serial_number=invocation.test.serial_number,
            fmf_id=invocation.test.fmf_id,
            context=invocation.phase.step.plan._fmf_context,
            result=result,
            note=note or [],
            start_time=invocation.start_time,
            end_time=invocation.end_time,
            duration=invocation.real_duration,
            ids=ids,
            log=log or [],
            guest=ResultGuestData.from_test_invocation(invocation=invocation),
            data_path=invocation.relative_test_data_path,
            subresult=subresult or [],
            check=invocation.check_results or [],
        )

        interpret_checks = {check.how: check.result for check in invocation.test.check}

        return _result.interpret_result(invocation.test.result, interpret_checks)

    def interpret_check_result(
        self,
        check_name: str,
        interpret_checks: dict[str, CheckResultInterpret],
    ) -> ResultOutcome:
        """
        Aggregate all checks of given name and interpret the outcome

        :param check_name: name of the check to be aggregated
        :param interpret_checks: mapping of check:how and its result interpret
        :returns: :py:class:`ResultOutcome` instance with the interpreted result
        """

        # Reduce all check outcomes into a single worst outcome
        reduced_outcome = ResultOutcome.reduce(
            [check.result for check in self.check if check.name == check_name]
        )

        # Now let's handle the interpretation
        interpret = interpret_checks[check_name]
        interpreted_outcome = reduced_outcome

        if interpret == CheckResultInterpret.RESPECT:
            if interpreted_outcome == ResultOutcome.FAIL:
                self.note.append(f"check '{check_name}' failed")

        elif interpret == CheckResultInterpret.INFO:
            interpreted_outcome = ResultOutcome.INFO
            self.note.append(f"check '{check_name}' is informational")

        elif interpret == CheckResultInterpret.XFAIL:
            if reduced_outcome == ResultOutcome.PASS:
                interpreted_outcome = ResultOutcome.FAIL
                self.note.append(f"check '{check_name}' did not fail as expected")

            if reduced_outcome == ResultOutcome.FAIL:
                interpreted_outcome = ResultOutcome.PASS
                self.note.append(f"check '{check_name}' failed as expected")

        return interpreted_outcome

    def interpret_result(
        self,
        interpret: ResultInterpret,
        interpret_checks: dict[str, CheckResultInterpret],
    ) -> 'Result':
        """
        Interpret result according to a given interpretation instruction.

        Inspect and possibly modify :py:attr:`result` and :py:attr:`note`
        attributes, following the ``interpret`` value.

        :param interpret: how to interpret current result.
        :param interpret_checks: mapping of check:how and its result interpret
        :returns: :py:class:`Result` instance containing the updated result.
        """

        if interpret not in ResultInterpret:
            raise tmt.utils.SpecificationError(
                f"Invalid result '{interpret.value}' in test '{self.name}'."
            )

        if interpret == ResultInterpret.CUSTOM:
            return self

        # Interpret check results (aggregated by the check name)
        check_outcomes: list[ResultOutcome] = [
            self.interpret_check_result(check_name, interpret_checks)
            for check_name in tmt.utils.uniq([check.name for check in self.check])
        ]

        # Aggregate check results with the main test result
        self.result = ResultOutcome.reduce([self.result, *check_outcomes])

        # Override result with result outcome provided by user
        if interpret not in (ResultInterpret.RESPECT, ResultInterpret.XFAIL):
            self.result = ResultOutcome(interpret.value)
            self.note.append(f"test result overridden: {self.result.value}")

            # Add original result to note if the result has changed
            if self.result != self.original_result:
                self.note.append(f"original test result: {self.original_result.value}")

            return self

        # Handle the expected fail
        if interpret == ResultInterpret.XFAIL:
            if self.result == ResultOutcome.PASS:
                self.result = ResultOutcome.FAIL
                self.note.append("test was expected to fail")

            elif self.result == ResultOutcome.FAIL:
                self.result = ResultOutcome.PASS
                self.note.append("test failed as expected")

        # Add original result to note if the result has changed
        if self.result != self.original_result:
            self.note.append(f"original test result: {self.original_result.value}")

        return self

    def to_subresult(self) -> 'SubResult':
        """
        Convert result to tmt subresult
        """
        options = [
            tmt.container.key_to_option(key) for key in tmt.container.container_keys(SubResult)
        ]

        return SubResult.from_serialized(
            {option: value for option, value in self.to_serialized().items() if option in options}
        )

    @staticmethod
    def total(results: list['Result']) -> dict[ResultOutcome, int]:
        """
        Return dictionary with total stats for given results
        """

        stats = dict.fromkeys(RESULT_OUTCOME_COLORS, 0)

        for result in results:
            stats[result.result] += 1
        return stats

    @staticmethod
    def summary(results: list['Result']) -> str:
        """
        Prepare a nice human summary of provided results
        """

        stats = Result.total(results)
        comments = []
        if stats.get(ResultOutcome.PASS):
            passed = ' ' + style('passed', fg='green')
            comments.append(fmf.utils.listed(stats[ResultOutcome.PASS], 'test') + passed)
        if stats.get(ResultOutcome.FAIL):
            failed = ' ' + style('failed', fg='red')
            comments.append(fmf.utils.listed(stats[ResultOutcome.FAIL], 'test') + failed)
        if stats.get(ResultOutcome.SKIP):
            skipped = ' ' + style('skipped', fg='bright_black')
            comments.append(fmf.utils.listed(stats[ResultOutcome.SKIP], 'test') + skipped)
        if stats.get(ResultOutcome.INFO):
            count, comment = fmf.utils.listed(stats[ResultOutcome.INFO], 'info').split()
            comments.append(count + ' ' + style(comment, fg='blue'))
        if stats.get(ResultOutcome.WARN):
            count, comment = fmf.utils.listed(stats[ResultOutcome.WARN], 'warn').split()
            comments.append(count + ' ' + style(comment, fg='yellow'))
        if stats.get(ResultOutcome.ERROR):
            count, comment = fmf.utils.listed(stats[ResultOutcome.ERROR], 'error').split()
            comments.append(count + ' ' + style(comment, fg='magenta'))
        if stats.get(ResultOutcome.PENDING):
            count, comment = str(stats[ResultOutcome.PENDING]), 'pending'
            comments.append(count + ' ' + style(comment, fg='cyan'))
        # FIXME: cast() - https://github.com/teemtee/fmf/issues/185
        return cast(str, fmf.utils.listed(comments or ['no results found']))

    def show(self, display_guest: bool = True) -> str:
        """
        Return a nicely colored result with test name (and note)
        """

        from tmt.steps.provision import format_guest_full_name

        result = 'errr' if self.result == ResultOutcome.ERROR else self.result.value

        components: list[str] = [
            style(result, fg=RESULT_OUTCOME_COLORS[self.result]),
            self.name,
        ]

        if display_guest and self.guest:
            assert self.guest.name  # narrow type

            components.append(f'(on {format_guest_full_name(self.guest.name, self.guest.role)})')

        if self.note:
            components.append(f'({self.printable_note})')

        return ' '.join(components)

    @property
    def failure_logs(self) -> list[Path]:
        """
        Return paths to all failure logs from the result
        """

        failure_logs = super().failure_logs
        for check in self.check:
            failure_logs += check.failure_logs
        return list(set(failure_logs))


def results_to_exit_code(results: list[Result], execute_enabled: bool = True) -> int:
    """
    Map results to a tmt exit code
    """

    from tmt.cli import TmtExitCode

    stats = Result.total(results)

    # Quoting the specification:

    # "No test results found."
    if sum(stats.values()) == 0:
        return TmtExitCode.NO_RESULTS_FOUND

    # "Errors occurred during test execution."
    if stats[ResultOutcome.ERROR]:
        return TmtExitCode.ERROR

    # "There was a fail or warn identified, but no error."
    if stats[ResultOutcome.FAIL] + stats[ResultOutcome.WARN]:
        return TmtExitCode.FAIL

    # "Tests were executed, and all reported the ``skip`` result."
    if sum(stats.values()) == stats[ResultOutcome.SKIP]:
        return TmtExitCode.ALL_TESTS_SKIPPED

    # "No errors or fails, but there are pending tests."
    if execute_enabled and stats[ResultOutcome.PENDING]:
        return TmtExitCode.ERROR

    # "At least one test passed, there was no fail, warn or error."
    if (
        sum(stats.values())
        == stats[ResultOutcome.PASS]
        + stats[ResultOutcome.INFO]
        + stats[ResultOutcome.SKIP]
        + stats[ResultOutcome.PENDING]
    ):
        return TmtExitCode.SUCCESS

    raise GeneralError("Unhandled combination of test result.")


def save_failures(
    invocation: 'tmt.steps.execute.TestInvocation', directory: Path, failures: list[str]
) -> Path:
    """
    Save test failures to a file.

    :param invocation: test invocation.
    :param directory: directory to save the file in.
    :param failures: list of failures to save.
    """

    path = directory / tmt.steps.execute.TEST_FAILURES_FILENAME

    try:
        existing_failures = tmt.utils.yaml_to_list(invocation.phase.read(path))
    except tmt.utils.FileError:
        existing_failures = []

    existing_failures += failures

    invocation.phase.write(path, tmt.utils.dict_to_yaml(existing_failures))
    assert invocation.phase.step.workdir is not None  # narrow type
    return path.relative_to(invocation.phase.step.workdir)
