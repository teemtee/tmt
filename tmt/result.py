import dataclasses
import enum
import re
from typing import TYPE_CHECKING, Dict, List, Optional, cast

import click
import fmf

import tmt.utils
from tmt.checks import CheckEvent
from tmt.utils import Path, field

if TYPE_CHECKING:
    import tmt.base
    import tmt.steps.provision

# Extra keys used for identification in Result class
EXTRA_RESULT_IDENTIFICATION_KEYS = ['extra-nitrate', 'extra-task']


class ResultOutcome(enum.Enum):
    PASS = 'pass'
    FAIL = 'fail'
    INFO = 'info'
    WARN = 'warn'
    ERROR = 'error'
    SKIP = 'skip'

    @classmethod
    def from_spec(cls, spec: str) -> 'ResultOutcome':
        try:
            return ResultOutcome(spec)
        except ValueError:
            raise tmt.utils.SpecificationError(f"Invalid partial custom result '{spec}'.")


# Cannot subclass enums :/
# https://docs.python.org/3/library/enum.html#restricted-enum-subclassing
class ResultInterpret(enum.Enum):
    # These are "inherited" from ResultOutcome
    PASS = 'pass'
    FAIL = 'fail'
    INFO = 'info'
    WARN = 'warn'
    ERROR = 'error'
    SKIP = 'skip'

    # Special interpret values
    RESPECT = 'respect'
    CUSTOM = 'custom'
    XFAIL = 'xfail'

    @classmethod
    def is_result_outcome(cls, value: 'ResultInterpret') -> bool:
        return value.name in list(ResultOutcome.__members__.keys())


RESULT_OUTCOME_COLORS: Dict[ResultOutcome, str] = {
    ResultOutcome.PASS: 'green',
    ResultOutcome.FAIL: 'red',
    ResultOutcome.INFO: 'blue',
    ResultOutcome.WARN: 'yellow',
    ResultOutcome.ERROR: 'magenta',
    # TODO (happz) make sure the color is visible for all terminals
    ResultOutcome.SKIP: 'bright_black',
    }


@dataclasses.dataclass
class ResultGuestData(tmt.utils.SerializableContainer):
    """ Describes what tmt knows about a guest the result was produced on """

    name: str = f'{tmt.utils.DEFAULT_NAME}-0'
    role: Optional[str] = None


# This needs to be a stand-alone function because of the import of `tmt.base`.
# It cannot be imported on module level because of circular dependency.
def _unserialize_fmf_id(serialized: 'tmt.base._RawFmfId') -> 'tmt.base.FmfId':
    from tmt.base import FmfId

    return FmfId.from_spec(serialized)


@dataclasses.dataclass
class BaseResult(tmt.utils.SerializableContainer):
    """ Describes what tmt knows about a result """

    name: str
    result: ResultOutcome = field(
        default=ResultOutcome.PASS,
        serialize=lambda result: result.value,
        unserialize=ResultOutcome.from_spec
        )
    note: Optional[str] = None
    log: List[Path] = field(
        default_factory=list,
        serialize=lambda logs: [str(log) for log in logs],
        unserialize=lambda value: [Path(log) for log in value])

    starttime: Optional[str] = None
    endtime: Optional[str] = None
    duration: Optional[str] = None

    def show(self) -> str:
        """ Return a nicely colored result with test name (and note) """

        result = 'errr' if self.result == ResultOutcome.ERROR else self.result.value

        components: List[str] = [
            click.style(result, fg=RESULT_OUTCOME_COLORS[self.result]),
            self.name
            ]

        if self.note:
            components.append(f'({self.note})')

        return ' '.join(components)


@dataclasses.dataclass
class CheckResult(BaseResult):
    """ Describes what tmt knows about a single test check result """

    event: CheckEvent = field(
        default=CheckEvent.BEFORE_TEST,
        serialize=lambda event: event.value,
        unserialize=CheckEvent.from_spec)


@dataclasses.dataclass
class Result(BaseResult):
    """ Describes what tmt knows about a single test result """

    serialnumber: int = 0
    fmf_id: Optional['tmt.base.FmfId'] = field(
        default=cast(Optional['tmt.base.FmfId'], None),
        serialize=lambda fmf_id: fmf_id.to_minimal_spec() if fmf_id is not None else {},
        unserialize=_unserialize_fmf_id
        )
    ids: Dict[str, Optional[str]] = field(default_factory=dict)
    guest: ResultGuestData = field(
        default_factory=ResultGuestData,
        serialize=lambda value: value.to_serialized(),  # type: ignore[attr-defined]
        unserialize=lambda serialized: ResultGuestData.from_serialized(serialized)
        )

    check: List[CheckResult] = field(
        default_factory=list,
        serialize=lambda results: [result.to_serialized() for result in results],
        unserialize=lambda serialized: [
            CheckResult.from_serialized(check) for check in serialized]
        )
    data_path: Optional[Path] = field(
        default=None,
        serialize=lambda path: None if path is None else str(path),
        unserialize=lambda value: None if value is None else Path(value)
        )

    @classmethod
    def from_test(
            cls,
            *,
            test: 'tmt.base.Test',
            result: ResultOutcome,
            note: Optional[str] = None,
            ids: Optional[Dict[str, Optional[str]]] = None,
            log: Optional[List[Path]] = None,
            guest: Optional['tmt.steps.provision.Guest'] = None) -> 'Result':
        """
        Create a result from a test instance.

        A simple helper for extracting interesting data from a given test. While
        it's perfectly possible to go directly through ``Result(...)``, when
        holding a :py:class:`tmt.base.Test` instance, this method would
        initialize the ``Result`` instance with the following:

        * test name
        * test identifier (``id`` key) and ``extra-*`` IDs

        Result would be interpreted according to test's ``result`` key
        (see https://tmt.readthedocs.io/en/stable/spec/tests.html#result).
        """

        from tmt.base import Test

        if not isinstance(test, Test):
            raise tmt.utils.SpecificationError(f"Invalid test '{test}'.")

        # Saving identifiable information for each test case so we can match them
        # to Polarion/Nitrate/other cases and report run results there
        # TODO: would an exception be better? Can test.id be None?
        ids = ids or {}
        default_ids = {
            tmt.identifier.ID_KEY: test.id
            }

        for key in EXTRA_RESULT_IDENTIFICATION_KEYS:
            default_ids[key] = test.node.get(key)

        default_ids.update(ids)
        ids = default_ids

        guest_data = ResultGuestData(name=guest.name, role=guest.role) if guest is not None \
            else ResultGuestData()

        _result = Result(
            name=test.name,
            serialnumber=test.serialnumber,
            fmf_id=test.fmf_id,
            result=result,
            note=note,
            starttime=test.starttime,
            endtime=test.endtime,
            duration=test.real_duration,
            ids=ids,
            log=log or [],
            guest=guest_data,
            data_path=test.data_path)

        return _result.interpret_result(
            ResultInterpret(test.result) if test.result else ResultInterpret.RESPECT)

    def interpret_result(self, interpret: ResultInterpret) -> 'Result':
        """
        Interpret result according to a given interpretation instruction.

        Inspect and possibly modify :py:attr:`result` and :py:attr:`note`
        attributes, following the ``interpret`` value.

        :param interpret: how to interpret current result.
        :returns: :py:class:`Result` instance containing the updated result.
        """

        if interpret in (ResultInterpret.RESPECT, ResultInterpret.CUSTOM):
            return self

        # Extend existing note or set a new one
        if self.note and isinstance(self.note, str):
            self.note += f', original result: {self.result.value}'

        elif self.note is None:
            self.note = f'original result: {self.result.value}'

        else:
            raise tmt.utils.SpecificationError(
                f"Test result note '{self.note}' must be a string.")

        if interpret == ResultInterpret.XFAIL:
            # Swap just fail<-->pass, keep the rest as is (info, warn,
            # error)
            self.result = {
                ResultOutcome.FAIL: ResultOutcome.PASS,
                ResultOutcome.PASS: ResultOutcome.FAIL
                }.get(self.result, self.result)

        elif ResultInterpret.is_result_outcome(interpret):
            self.result = ResultOutcome(interpret.value)

        else:
            raise tmt.utils.SpecificationError(
                f"Invalid result '{interpret.value}' in test '{self.name}'.")

        return self

    @staticmethod
    def total(results: List['Result']) -> Dict[ResultOutcome, int]:
        """ Return dictionary with total stats for given results """
        stats = {result: 0 for result in RESULT_OUTCOME_COLORS}

        for result in results:
            stats[result.result] += 1
        return stats

    @staticmethod
    def summary(results: List['Result']) -> str:
        """ Prepare a nice human summary of provided results """
        stats = Result.total(results)
        comments = []
        if stats.get(ResultOutcome.PASS):
            passed = ' ' + click.style('passed', fg='green')
            comments.append(fmf.utils.listed(stats[ResultOutcome.PASS], 'test') + passed)
        if stats.get(ResultOutcome.FAIL):
            failed = ' ' + click.style('failed', fg='red')
            comments.append(fmf.utils.listed(stats[ResultOutcome.FAIL], 'test') + failed)
        if stats.get(ResultOutcome.SKIP):
            skipped = ' ' + click.style('skipped', fg='bright_black')
            comments.append(fmf.utils.listed(stats[ResultOutcome.SKIP], 'test') + skipped)
        if stats.get(ResultOutcome.INFO):
            count, comment = fmf.utils.listed(stats[ResultOutcome.INFO], 'info').split()
            comments.append(count + ' ' + click.style(comment, fg='blue'))
        if stats.get(ResultOutcome.WARN):
            count, comment = fmf.utils.listed(stats[ResultOutcome.WARN], 'warn').split()
            comments.append(count + ' ' + click.style(comment, fg='yellow'))
        if stats.get(ResultOutcome.ERROR):
            count, comment = fmf.utils.listed(stats[ResultOutcome.ERROR], 'error').split()
            comments.append(count + ' ' + click.style(comment, fg='magenta'))
        # FIXME: cast() - https://github.com/teemtee/fmf/issues/185
        return cast(str, fmf.utils.listed(comments or ['no results found']))

    def show(self, display_guest: bool = True) -> str:
        """ Return a nicely colored result with test name (and note) """

        from tmt.steps.provision import format_guest_full_name

        result = 'errr' if self.result == ResultOutcome.ERROR else self.result.value

        components: List[str] = [
            click.style(result, fg=RESULT_OUTCOME_COLORS[self.result]),
            self.name
            ]

        if display_guest and self.guest:
            assert self.guest.name  # narrow type

            components.append(f'(on {format_guest_full_name(self.guest.name, self.guest.role)})')

        if self.note:
            components.append(f'({self.note})')

        return ' '.join(components)

    @staticmethod
    def failures(log: Optional[str], msg_type: str = 'FAIL') -> str:
        """ Filter stdout and get only messages with certain type """
        if not log:
            return ''
        filtered = ''

        # Filter beakerlib style logs in the following way:
        # 1. Reverse the log string by lines
        # 2. Search for each FAIL and extract every associated line.
        # 3. For failed phases also extract phase name so the log is easier to understand
        # 4. Reverse extracted lines back into correct order.
        if re.search(':: \\[   FAIL   \\] ::', log):  # dumb check for a beakerlib log
            copy_line = False
            copy_phase_name = False
            failure_log = []
            # we will be processing log lines in a reversed order
            iterator = iter(reversed(log.split("\n")))
            for line in iterator:
                # found FAIL enables log extraction
                if re.search(':: \\[   FAIL   \\] ::', line):
                    copy_line = True
                    copy_phase_name = True
                # BEGIN of rlRun block or previous command or beginning of a test section
                # disables extraction
                elif re.search('(:: \\[.{10}\\] ::|[:]{80})', line):
                    copy_line = False
                # extract line from the log
                if copy_line:
                    failure_log.append(line)
                # Add beakerlib phase name to a failure log, in order to properly match the phase
                # name we need to do this in two steps.
                if copy_phase_name and re.search('[:]{80}', line):
                    # read the next line containing phase name
                    line = next(iterator)
                    failure_log.append(f'\n{line}')
                    copy_phase_name = False
            # reverse extracted lines to restore previous order
            failure_log.reverse()
            return '\n'.join(failure_log).strip()

        # Check for other failures and errors when not using beakerlib
        for m in re.findall(
                fr'.*\b(?=error|fail|{msg_type})\b.*', log, re.IGNORECASE | re.MULTILINE):
            filtered += m + '\n'

        return filtered or log
