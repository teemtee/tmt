
"""
Metadata linting.

Internal APIs, classes, shared functionality and helpers for test, plan and
story metadata linting.

A mixin class, :py:class:`Lintable`, provides the required functionality for
base classes. Namely, it takes care of linter discovery and provides
:py:meth:`Lintable.lint` method to run them.

Classes spiced with ``Lintable`` define their sets of linters. Consider the
following examples:

.. code-block:: python

   # Methods whose names start with ``lint_*`` prefix are considered *linters*,
   # and linters perform one or more *checks* users can enable or disable.
   def lint_path_exists(self) -> LinterReturn:
       # A linter must have a docstring which is then used to generate documentation,
       # e.g. when ``lint --list-checks`` is called. The docstring must begin with
       # a linter *id*. The id should match ``[CTPS]\\d\\d\\d`` regular expression:
       # ``C``ommon, ``T``est, ``P``lan, ``S``tory, plus a three-digit serial number
       # of the check among its peers.
       ''' T004: test directory path must exist '''

       # Linter implements a generator (see :py:member:`LinterReturn`) yielding
       # two item tuples of :py:class:`LinterOutcome` and string messages.

       if not self.path:
           yield LinterOutcome.FAIL, 'directory path is not set'
           return

       test_path = os.path.join(self.node.root, os.path.relpath(self.path.strip(), '/'))

       if not os.path.exists(test_path):
           yield LinterOutcome.FAIL, f'test path "{test_path}" does not exist'
           return

       yield LinterOutcome.PASS, f'test path "{test_path}" does exist'

   def lint_manual_valid_markdown(self) -> LinterReturn:
       ''' T008: manual test should be valid markdown '''

       # Linter should yield `SKIP` outcome when it does not apply, to announce
       # it did inspect the object but realized the object is out of scope of
       # the linter, and checks do not apply.
       if not self.manual:
            yield LinterOutcome.SKIP, 'not a manual test'
            return

       manual_test = os.path.join(self.node.root, self.path.strip())

       warnings = tmt.export.check_md_file_respects_spec(manual_test)

       if warnings:
           # Linter may yield as many tuples as it deems necessary. This allows
           # for linters iterating over more granular aspects of metadata,
           # providing more specific hints.
           for warning in warnings:
              yield LinterOutcome.WARN, warning

       ...
"""

import dataclasses
import enum
import re
import textwrap
from collections.abc import Iterable, Iterator
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    ClassVar,
    Generic,
    Optional,
    TypeVar,
    )

from click import style

import tmt
import tmt.utils

if TYPE_CHECKING:
    import tmt.base


# ignore[type-arg]: bound type vars cannot be generic, and it would create a loop anyway.
LintableT = TypeVar('LintableT', bound='Lintable')  # type: ignore[type-arg]


class LinterOutcome(enum.Enum):
    SKIP = 'skip'
    PASS = 'pass'
    FAIL = 'fail'
    WARN = 'warn'
    FIXED = 'fixed'


# TODO: these would be cool, but first we should get rid of Result
# adding color when it shouldn't have.
#
# _OUTCOME_TO_MARK = {
#     LinterOutcome.SKIP: '-',
#     LinterOutcome.PASS: '\N{heavy check mark}',
#     LinterOutcome.FAIL: '\N{heavy multiplication x}',
#     LinterOutcome.WARN: '\N{exclamation mark}',
#     LinterOutcome.FIXED: '\N{heavy check mark}'
# }

_OUTCOME_TO_MARK = {
    LinterOutcome.SKIP: 'skip',
    LinterOutcome.PASS: 'pass',
    LinterOutcome.FAIL: 'fail',
    LinterOutcome.WARN: 'warn',
    LinterOutcome.FIXED: 'fix '
    }

_OUTCOME_TO_COLOR = {
    LinterOutcome.SKIP: 'blue',
    LinterOutcome.PASS: 'green',
    LinterOutcome.FAIL: 'red',
    LinterOutcome.WARN: 'yellow',
    LinterOutcome.FIXED: 'green'
    }


#: Info on how a linter decided: linter itself, its outcome & the message.
LinterRuling = tuple['Linter', LinterOutcome, LinterOutcome, str]
#: A return value type of a single linter.
LinterReturn = Iterator[tuple[LinterOutcome, str]]
#: A linter itself, a callable method.
# TODO: ignore[type-arg]: `Lintable` is a generic type, and mypy starts
# reporting it since 1.7.1 or so. Adding the parameter here would require
# a bigger patch than a mere bump of mypy version. Leaving for later.
LinterCallback = Callable[['Lintable'], LinterReturn]  # type: ignore[type-arg]

_LINTER_DESCRIPTION_PATTERN = re.compile(r"""
    ^                      # must match the whole string
    (?P<id>[CTPS]\d\d\d):  # check ID, the class initials & a three-digit number
    \s*                    # optional white space
    (?P<short>.+)          # check description
    $                      # must match the whole string
    """, re.VERBOSE)


@dataclasses.dataclass(init=False)
class Linter:
    """ A single linter """

    callback: LinterCallback
    id: str

    help: str
    description: Optional[str] = None

    def __init__(self, callback: LinterCallback) -> None:
        self.callback = callback

        if not callback.__doc__:
            raise tmt.utils.GeneralError(f"Linter '{callback}' lacks docstring.")

        match = _LINTER_DESCRIPTION_PATTERN.match(textwrap.dedent(callback.__doc__).strip())

        if not match:
            raise tmt.utils.GeneralError(f"Linter '{callback}' docstring has wrong format.")

        components = match.groupdict()

        self.id = components['id'].strip()
        self.help = components['short'].strip()

    def format(self) -> list[str]:
        """
        Format the linter for printing or logging.

        :returns: a string description of the linter, suitable for
            logging or help texts, in the form of lines of text.
        """

        return [
            f'{self.id}: {self.help}'
            ]


class Lintable(Generic[LintableT]):
    """ Mixin class adding support for linting of class instances """

    # Declare linter registry as a class variable, but do not initialize it. If initialized
    # here, the mapping would be shared by all classes, which is not a desirable attribute.
    # Instead, mapping will be created by `get_linter_registry()`.
    _linter_registry: ClassVar[list[Linter]]

    # Keep this method around, to correctly support Python's method resolution order.
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

    # Cannot use @property as this must remain classmethod
    @classmethod
    def get_linter_registry(cls) -> list[Linter]:
        """ Return - or initialize - linter registry """

        if not hasattr(cls, '_linter_registry'):
            cls._linter_registry = []

        return cls._linter_registry

    @classmethod
    def discover_linters(cls) -> None:
        """
        Discover and register all linters implemented by this class.

        A linter is a method whose name starts with ``lint_`` prefix. It must
        have a docstring which serves as a hint for ``--list-checks`` output.
        """

        for name in dir(cls):
            if not name.startswith('lint_'):
                continue

            cls.get_linter_registry().append(tmt.lint.Linter(getattr(cls, name)))

    @classmethod
    def resolve_enabled_linters(
            cls,
            enable_checks: Optional[list[str]] = None,
            disable_checks: Optional[list[str]] = None
            ) -> list[Linter]:
        """
        Produce a list of enabled linters from all registered ones.

        Method combines three inputs:

        * registered linters, acquired from the class registry,
        * list of checks to enable, and
        * list of checks to disable

        into a single list of linters that are considered as enabled.

        :param enable_checks: if set, only linters providing the listed checks
            would be included in the output.
        :param disable_checks: if set, linters providing the listed checks would
            be removed from the output.
        :returns: list of linters that were registered, and whose checks were
            enabled and not disabled.
        """

        linters: list[Linter] = []

        if not enable_checks:
            linters = cls.get_linter_registry()

        else:
            linters = []

            for needle in enable_checks:
                linters += [
                    linter
                    for linter in cls.get_linter_registry()
                    if needle in linter.id
                    ]

        if disable_checks:
            linters = [
                linter for linter in linters
                if linter.id not in disable_checks
                ]

        return linters

    def lint(
            self,
            enable_checks: Optional[list[str]] = None,
            disable_checks: Optional[list[str]] = None,
            enforce_checks: Optional[list[str]] = None,
            linters: Optional[list[Linter]] = None) -> tuple[bool, list[LinterRuling]]:
        """
        Check the instance against a battery of linters and report results.

        :param enable_checks: if set, only linters providing the listed checks
            would be applied.
        :param disable_checks: if set, linters providing the listed checks would
            not be applied.
        :param enforce_checks: if set, listed checks would be marked as failed
            if their outcome is not ``pass``, i.e. even a warning would become
            a fail.
        :param linters: if set, only these linters would be applied. Providing
            ``linters`` makes ``enable_checks`` and ``disable_checks`` ignored.
        :returns: a tuple of two items: a boolean reporting whether the instance
            passed the test, and a list of :py:class:`LinterRuling` items, each
            describing one linter outcome. Note that linters may produce none or
            more than one outcome.
        """

        enforce_checks = enforce_checks or []

        linters = linters or self.resolve_enabled_linters(
            enable_checks=enable_checks,
            disable_checks=disable_checks)

        valid = True
        rulings: list[LinterRuling] = []

        for linter in sorted(linters, key=lambda x: x.id):
            for outcome, message in linter.callback(self):
                if outcome == LinterOutcome.FAIL:
                    rulings.append((linter, outcome, outcome, message))

                    valid = False

                elif outcome != LinterOutcome.PASS:
                    if linter.id in enforce_checks:
                        rulings.append((linter, outcome, LinterOutcome.FAIL, message))

                        valid = False

                    else:
                        rulings.append((linter, outcome, outcome, message))

                else:
                    rulings.append((linter, outcome, outcome, message))

        return valid, rulings

    @classmethod
    def format_linters(cls) -> str:
        """
        Format registered linters for printing or logging.

        :returns: a string description of registered linters, suitable for
            logging or help texts.
        """

        hints: list[str] = []

        for linter in sorted(cls.get_linter_registry(), key=lambda x: x.id):
            hints += linter.format()

        return '\n'.join(hints)


def filter_allowed_checks(
        rulings: Iterable[LinterRuling],
        outcomes: Optional[list[LinterOutcome]] = None) -> Iterator[LinterRuling]:
    """
    Filter only rulings whose outcomes are allowed.

    :param rulings: rulings to process.
    :param outcomes: a list of allowed ruling outcomes. If not set, all outcomes
        are allowed.
    :yields: rulings with allowed outcomes.
    """

    outcomes = outcomes or []

    for linter, actual_outcome, eventual_outcome, message in rulings:
        if outcomes and eventual_outcome not in outcomes:
            continue

        yield (linter, actual_outcome, eventual_outcome, message)


def format_rulings(rulings: Iterable[LinterRuling]) -> Iterator[str]:
    """
    Format rulings for printing or logging.

    :param rulings: rulings to format.
    :yields: rulings formatted as separate strings.
    """

    # Find out whether there is a ruling whose actual outcome is not the same
    # as its eventual outcome. That means the actual outcome has been overruled,
    # waived or turned into a failure - if there is any such ruling, we should
    # display the actual => eventual transition. If there's no such ruling, we
    # can display just one outcome, they are both same, and indentation and
    # padding would be simpler.
    display_eventual = any(
        actual_outcome != eventual_outcome for _, actual_outcome, eventual_outcome, _ in rulings)

    for linter, actual_outcome, eventual_outcome, message in rulings:
        assert actual_outcome in _OUTCOME_TO_MARK
        assert actual_outcome in _OUTCOME_TO_COLOR

        actual_status = style(
            _OUTCOME_TO_MARK[actual_outcome],
            fg=_OUTCOME_TO_COLOR[actual_outcome])

        if display_eventual:
            assert eventual_outcome in _OUTCOME_TO_MARK
            assert eventual_outcome in _OUTCOME_TO_COLOR

            eventual_status = style(
                _OUTCOME_TO_MARK[eventual_outcome],
                fg=_OUTCOME_TO_COLOR[eventual_outcome])

            eventual = ' ' * 8 if actual_outcome == eventual_outcome else f' -> {eventual_status}'

        else:
            eventual = ''

        yield f'{actual_status}{eventual} {linter.id} {message}'
