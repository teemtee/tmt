import dataclasses
import enum
import re
from typing import TYPE_CHECKING, Dict, List, Optional, cast

import click
import fmf

import tmt.utils
from tmt.utils import Path, field

if TYPE_CHECKING:
    import tmt.base

# Extra keys used for identification in Result class
EXTRA_RESULT_IDENTIFICATION_KEYS = ['extra-nitrate', 'extra-task']


# TODO: this should become a more strict data class, with an enum or two to handle
# allowed values, etc. See https://github.com/teemtee/tmt/issues/1456.
# Defining a type alias so we can follow where the package is used.
class ResultOutcome(enum.Enum):
    PASS = 'pass'
    FAIL = 'fail'
    INFO = 'info'
    WARN = 'warn'
    ERROR = 'error'

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
    ResultOutcome.ERROR: 'magenta'
    }


@dataclasses.dataclass
class ResultGuestData(tmt.utils.SerializableContainer):
    """ Describes what tmt knows about a guest the result was produced on """

    name: Optional[str] = None
    role: Optional[str] = None


@dataclasses.dataclass
class Result(tmt.utils.SerializableContainer):
    """ Describes what tmt knows about a single test result """

    name: str
    serialnumber: int = 0
    result: ResultOutcome = field(
        default=ResultOutcome.PASS,
        serialize=lambda result: result.value,
        unserialize=ResultOutcome.from_spec
        )
    note: Optional[str] = None
    duration: Optional[str] = None
    ids: Dict[str, Optional[str]] = field(default_factory=dict)
    log: List[Path] = field(
        default_factory=list,
        serialize=lambda logs: [str(log) for log in logs],
        unserialize=lambda value: [Path(log) for log in value])
    guest: ResultGuestData = field(
        default_factory=ResultGuestData,
        serialize=lambda value: value.to_serialized(),  # type: ignore[attr-defined]
        unserialize=lambda serialized: ResultGuestData.from_serialized(serialized)
        )

    @classmethod
    def from_test(
            cls,
            *,
            test: 'tmt.base.Test',
            result: ResultOutcome,
            note: Optional[str] = None,
            duration: Optional[str] = None,
            ids: Optional[Dict[str, Optional[str]]] = None,
            log: Optional[List[Path]] = None,
            guest: Optional[ResultGuestData] = None) -> 'Result':
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

        _result = Result(
            name=test.name,
            serialnumber=test.serialnumber,
            result=result,
            note=note,
            duration=duration,
            ids=ids,
            log=log or [],
            guest=guest or ResultGuestData()
            )

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

    def show(self) -> str:
        """ Return a nicely colored result with test name (and note) """
        result = 'errr' if self.result == ResultOutcome.ERROR else self.result.value
        colored = click.style(result, fg=RESULT_OUTCOME_COLORS[self.result])
        note = f" ({self.note})" if self.note else ''
        return f"{colored} {self.name}{note}"

    @staticmethod
    def failures(log: Optional[str], msg_type: str = 'FAIL') -> str:
        """ Filter stdout and get only messages with certain type """
        if not log:
            return ''
        filtered = ''

        # Filter beakerlib style logs, reverse the log string by lines, search for each FAIL
        # and every associated line, then reverse the picked lines back into correct order
        for m in re.findall(
                fr'(^.*\[\s*{msg_type}\s*\][\S\s]*?)(?:^::\s+\[[0-9: ]+|:{{80}})',
                '\n'.join(log.split('\n')[::-1]), re.MULTILINE):
            filtered += m.strip() + '\n'
        if filtered:
            return '\n'.join(filtered.strip().split('\n')[::-1])

        # Check for other failures and errors when not using beakerlib
        for m in re.findall(
                fr'.*\b(?=error|fail|{msg_type})\b.*', log, re.IGNORECASE | re.MULTILINE):
            filtered += m + '\n'

        return filtered or log
