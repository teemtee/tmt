"""
Guest hardware requirements specification and helpers.

tmt metadata allow to describe various HW requirements a guest needs to satisfy.
This package provides useful functions and classes for core functionality and
shared across provision plugins.

Parsing of HW requirements
==========================

Set of HW requirements, as given by test or plan metadata, is represented by
Python structures - lists, mappings, primitive types - when loaded from fmf
files. Part of the code below converts this representation to a tree of objects
that provide helpful operations for easier evaluation and processing of HW
requirements.

Each HW requirement "rule" in original metadata is a constraint, a condition
the eventual guest HW must satisfy. Each node of the tree created from HW
requirements is therefore called "a constraint", and represents either a single
condition ("trivial" constraints), or a set of such conditions plus a function
reducing their individual outcomes to one final answer for the whole set (think
:py:func:`any` and :py:func:`all` built-in functions) ("compound" constraints).
Components of each constraint - dimension, operator, value, units - are
decoupled from the rest, and made available for inspection.

[1] https://tmt.readthedocs.io/en/stable/spec/hardware.html
"""

import dataclasses
import enum
import functools
import itertools
import operator
import re
from collections.abc import Iterable, Iterator
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Generic,
    NamedTuple,
    Optional,
    TypeVar,
    Union,
    cast,
    )

import pint

import tmt.log
import tmt.utils
from tmt.utils import SpecBasedContainer, SpecificationError

if TYPE_CHECKING:
    from pint import Quantity

    from tmt._compat.typing import TypeAlias

    #: A type of values describing sizes of things like storage or RAM.
    # Note: type-hinting is a bit wonky with pyright
    # https://github.com/hgrecco/pint/issues/1166
    Size: TypeAlias = Quantity

#: Unit registry, used and shared by all code.
UNITS = pint.UnitRegistry()

# The default formatting should use unit symbols rather than full names.
UNITS.default_format = '~'


# Special type variable, used in `Constraint.from_specification` - we bound this return value to
# always be a subclass of `Constraint` class, instead of just any class in general.
# ignore[type-arg]: `Constraint` is a generic type, and making typevar bound by a generic type
# is hard. It's easier to silence mypy for now, and maybe pyright would serve us better.
T = TypeVar('T', bound='Constraint')  # type: ignore[type-arg]


class Operator(enum.Enum):
    """ Binary operators defined by specification """

    EQ = '=='
    NEQ = '!='
    MATCH = '~'
    NOTMATCH = '!~'
    _NOTMATCH_LEGACY = '=~'
    _TRIVIAL_EQ = '='
    GTE = '>='
    GT = '>'
    LTE = '<='
    LT = '<'

    CONTAINS = 'contains'
    NOTCONTAINS = 'not contains'


INPUTABLE_OPERATORS = [
    operator
    for operator in Operator.__members__.values()
    if operator not in (Operator.CONTAINS, Operator.NOTCONTAINS)
    ]


_OPERATOR_PATTERN = '|'.join(operator.value for operator in INPUTABLE_OPERATORS)

#: Regular expression to match and split the ``value`` part of a key:value pair.
#: The input consists of an (optional) operator, the actual value of the
#: constraint, and (optional) units. As a result, pattern yields two groups,
#: ``operator`` and ``value``, the latter containing both the value and units.
CONSTRAINT_VALUE_PATTERN = re.compile(rf"""
    ^                                   # must match the whole string
    (?P<operator>{_OPERATOR_PATTERN})?  # optional operator
    \s*                                 # operator might be separated by white space
    (?P<value>.+?)                      # actual value of the constraint
    \s*                                 # there might be trailing white space
    $                                   # must match the whole string, I said :)
    """, re.VERBOSE)

#: Regular expression to match and split a HW constraint name into its
#: components. The input consists of a constraint name, (optional) index
#: of the constraint among its peers, and (optional) child constraint name:
#:
#: * ``memory`` => ``memory``, ``None``, ``None``
#: * ``cpu.processors`` => ``cpu``, ``None``, ``processors``
#: * ``disk[1].size`` => ``disk``, ``1``, ``size``
CONSTRAINT_NAME_PATTERN = re.compile(r"""
    (?P<name>[a-z_+]+)                   # constraint name is mandatory
    (?:\[(?P<peer_index>[+-]?\d+)\])?    # index is optional
    (?:\.(?P<child_name>[a-z_]+))?       # child constraint name is also optional'
    """, re.VERBOSE)

#: Regular expression to match and split a HW constraint into its components.
#: The input consists of a constraint name, (optional) index of the constraint
#: among its peers, (optional) child constraint name, (optional) operator, and
#: value.
#:
#: * ``memory 10 GiB`` => ``memory``, ``None``, ``None``, ``None``, ``10 GiB``
#: * ``cpu.processors != 4`` => ``cpu``, ``None``, ``processors``, ``!=``, ``4``
#: * ``disk[1].size <= 1 TiB`` => ``disk``, ``1``, ``size``, ``<=``, ``1 TiB``
CONSTRAINT_COMPONENTS_PATTERN = re.compile(rf"""
    ^                                   # must match the whole string
    (?P<name>[a-z_+]+)                  # constraint name is mandatory
    (?:\[(?P<peer_index>[+-]?\d+)\])?   # index is optional
    (?:\.(?P<child_name>[a-z_\-]+))?    # child constraint name is optional
    \s*                                 # optional whitespace between constraint name and operator
    (?P<operator>{_OPERATOR_PATTERN})?  # optional operator
    \s*                                 # optional whitespace between operator and value
    (?P<value>.+?)                      # value is mandatory
    \s*                                 # trailing white space is allowed
    $                                   # must match the whole string
    """, re.VERBOSE)


#: A list of constraint names that operate over sequence of entities.
INDEXABLE_CONSTRAINTS: tuple[str, ...] = (
    'disk',
    'network'
    )

#: A list of constraint names that do not have child properties.
CHILDLESS_CONSTRAINTS: tuple[str, ...] = (
    'arch',
    'memory',
    'hostname'
    )


# Type of the operator callable. The operators accept two arguments, and return
# a boolean evaluation of relationship of their two inputs.
OperatorHandlerType = Callable[[Any, Any], bool]

# Type describing raw requirements as Python lists and mappings.
#
# mypy does not support cyclic definition, it would be much easier to just define this:
#
#   Spec = Dict[str, Union[int, float, str, 'Spec', List['Spec']]]
#
# Instead of resorting to ``Any``, we'll keep the type tracked by giving it its own name.
#
# See https://github.com/python/mypy/issues/731 for details.
Spec = Any

#: A type of constraint values.
ConstraintValue = Union[int, 'Size', str, bool, float]
ConstraintValueT = TypeVar('ConstraintValueT', int, 'Size', str, bool, float)

# TODO: this was ported from Artemis but it's not used as of now. That should
# change with future support for flavors aka instance types.
#
#: A type of values that can be measured, and may or may not have units.
#: A subset of :py:member:`ConstraintValue`.
# MeasurableConstraintValueType = Union[int, 'Size']


class ConstraintNameComponents(NamedTuple):
    """ Components of a constraint name """

    #: ``disk`` of ``disk[1].size``
    name: str
    #: ``1`` of ``disk[1].size``
    peer_index: Optional[int]
    #: ``size`` of ``disk[1].size``
    child_name: Optional[str]


@dataclasses.dataclass
class ConstraintComponents:
    """ Components of a constraint """

    name: str
    peer_index: Optional[int]
    child_name: Optional[str]
    operator: Optional[str]
    value: str

    @classmethod
    def from_spec(cls, spec: str) -> 'ConstraintComponents':
        match = CONSTRAINT_COMPONENTS_PATTERN.match(spec)

        if match is None:
            raise tmt.utils.SpecificationError('foo')

        groups = match.groupdict()

        return ConstraintComponents(
            name=groups['name'],
            peer_index=int(groups['peer_index']) if groups['peer_index'] is not None else None,
            child_name=groups['child_name'],
            operator=groups['operator'],
            value=groups['value']
            )


def match(text: str, pattern: str) -> bool:
    """
    Match a text against a given regular expression.

    :param text: string to examine.
    :param pattern: regular expression.
    :returns: ``True`` if pattern matches the string.
    """

    return re.match(pattern, text) is not None


def not_match(text: str, pattern: str) -> bool:
    """
    Match a text against a given regular expression.

    :param text: string to examine.
    :param pattern: regular expression.
    :returns: ``True`` if pattern does not matche the string.
    """

    return re.match(pattern, text) is None


def not_contains(haystack: list[str], needle: str) -> bool:
    """
    Find out whether an item is in the given list.

    .. note::

       Opposite of :py:func:`operator.contains`.

    :param haystack: container to examine.
    :param needle: item to look for in ``haystack``.
    :returns: ``True`` if ``needle`` is **not** in ``haystack``.
    """

    return needle not in haystack


OPERATOR_SIGN_TO_OPERATOR = {
    '=': Operator.EQ,
    '==': Operator.EQ,
    '!=': Operator.NEQ,
    '>': Operator.GT,
    '>=': Operator.GTE,
    '<': Operator.LT,
    '<=': Operator.LTE,
    '~': Operator.MATCH,
    '!~': Operator.NOTMATCH,
    'contains': Operator.CONTAINS,
    'not contains': Operator.NOTCONTAINS,
    # Legacy operators
    '=~': Operator.MATCH
    }


OPERATOR_TO_HANDLER: dict[Operator, OperatorHandlerType] = {
    Operator.EQ: operator.eq,
    Operator.NEQ: operator.ne,
    Operator.GT: operator.gt,
    Operator.GTE: operator.ge,
    Operator.LT: operator.lt,
    Operator.LTE: operator.le,
    Operator.MATCH: match,
    Operator.NOTMATCH: not_match,
    Operator.CONTAINS: operator.contains,
    Operator.NOTCONTAINS: not_contains
    }


#: A callable reducing a sequence of booleans to a single one. Think
#: :py:func:`any` or :py:func:`all`.
ReducerType = Callable[[Iterable[bool]], bool]


class ParseError(tmt.utils.MetadataError):
    """ Raised when HW requirement parsing fails """

    def __init__(self, constraint_name: str, raw_value: str,
                 message: Optional[str] = None) -> None:
        """
        Raise when HW requirement parsing fails.

        :param constraint_name: name of the constraint that caused issues.
        :param raw_value: original raw value.
        :param message: optional error message.
        """

        super().__init__(message or 'Failed to parse a hardware constraint.')

        self.constraint_name = constraint_name
        self.raw_value = raw_value


#
# Constraint classes
#

@dataclasses.dataclass(repr=False)
class BaseConstraint(SpecBasedContainer[Spec, Spec]):
    """ Base class for all classes representing one or more constraints """

    @classmethod
    def from_spec(cls, spec: Any) -> 'BaseConstraint':
        return parse_hw_requirements(spec)

    def to_spec(self) -> Spec:
        raise NotImplementedError

    def to_minimal_spec(self) -> Spec:
        return self.to_spec()

    def uses_constraint(self, constraint_name: str, logger: tmt.log.Logger) -> bool:
        """
        Inspect constraint whether the constraint or one of its children use a constraint of
        a given name.

        :param constraint_name: constraint name to look for.
        :param logger: logger to use for logging.
        :raises NotImplementedError: method is left for child classes to implement.
        """

        raise NotImplementedError

    def variants(
            self,
            members: Optional[list['Constraint[Any]']] = None
            ) -> Iterator[list['Constraint[Any]']]:
        """
        Generate all distinct variants of constraints covered by this one.

        For a trivial constraint, there is only one variant, and that is the
        constraint itself. In the case of compound constraints, the number of
        variants would be bigger, depending on the constraint's ``reducer``.

        :param members: if specified, each variant generated by this method is
            prepended with this list.
        :yields: iterator over all variants.
        """

        raise NotImplementedError

    def variant(self) -> list['Constraint[Any]']:
        """
        Pick one of the available variants of this constraints.

        As the constraint can yield many variants, often there's an interest in
        just one. There can be many different ways for picking the best one,
        whatever that may mean depending on the context, as a starting point
        this method is provided. In the future, provision plugins would probably
        use their own guessing to pick the most suitable variant.
        """

        variants = list(self.variants())

        if not variants:
            raise tmt.utils.GeneralError("Cannot pick a variant from an empty set.")

        return variants[0]


@dataclasses.dataclass(repr=False)
class CompoundConstraint(BaseConstraint):
    """ Base class for all *compound* constraints """

    def __init__(
            self,
            reducer: ReducerType = any,
            constraints: Optional[list[BaseConstraint]] = None
            ) -> None:
        """
        Construct a compound constraint, constraint imposed to more than one dimension.

        :param reducer: a callable reducing a list of results from child constraints into the final
            answer.
        :param constraints: child constraints.
        """

        self.reducer = reducer
        self.constraints = constraints or []

    @property
    def size(self) -> int:
        return len(self.constraints)

    def to_spec(self) -> Spec:
        return {
            self.__class__.__name__.lower(): [
                constraint.to_spec() for constraint in self.constraints
                ]
            }

    def uses_constraint(self, constraint_name: str, logger: tmt.log.Logger) -> bool:
        """
        Inspect constraint whether it or its children use a constraint of a given name.

        :param constraint_name: constraint name to look for.
        :param logger: logger to use for logging.
        :returns: ``True`` if the given constraint or its children use given constraint name.
        """

        # Using "any" on purpose: we cannot use the reducer belonging to this constraint,
        # because that one may yield result based on validity of all child constraints.
        # But we want to answer the question "is *any* of child constraints using the given
        # constraint?", not "are all using it?".
        return any(
            constraint.uses_constraint(constraint_name, logger)
            for constraint in self.constraints
            )

    def variants(
            self,
            members: Optional[list['Constraint[Any]']] = None
            ) -> Iterator[list['Constraint[Any]']]:
        """
        Generate all distinct variants of constraints covered by this one.

        Since the ``and`` reducer demands all child constraints must be
        satisfied, and some of these constraints can also be compound
        constraints, we need to construct a cartesian product of variants
        yielded by child constraints to include all possible combinations.

        :param members: if specified, each variant generated by this method is
            prepended with this list.
        :yields: iterator over all variants.
        :raises NotImplementedError: default implementation is left undefined for compound
            constraints.
        """

        raise NotImplementedError


@dataclasses.dataclass(repr=False)
class Constraint(BaseConstraint, Generic[ConstraintValueT]):
    """ A constraint imposing a particular limit to one of the guest properties """

    # Name of the constraint. Used for logging purposes, usually matches the
    # name of the system property.
    name: str

    # A binary operation to use for comparing the constraint value and the
    # value connected with a potential guest, guest flavor, instance type or
    # guest template.
    operator: Operator

    # A callable comparing the flavor value and the constraint value.
    operator_handler: OperatorHandlerType

    # Constraint value.
    value: ConstraintValueT

    # Stored for possible inspection by more advanced processing.
    raw_value: str

    # If set, it is a raw unit specified by the constraint.
    default_unit: Optional[str] = None

    # If set, it is a "bigger" constraint, to which this constraint logically
    # belongs as one of its aspects.
    original_constraint: Optional['Constraint[Any]'] = None

    @classmethod
    def _from_specification(
            cls: type[T],
            name: str,
            raw_value: str,
            as_quantity: bool = True,
            as_cast: Optional[Callable[[str], ConstraintValueT]] = None,
            original_constraint: Optional['Constraint[Any]'] = None,
            allowed_operators: Optional[list[Operator]] = None,
            default_unit: Optional[Any] = "bytes"
            ) -> T:
        """
        Parse raw constraint specification into our internal representation.

        :param name: name of the constraint.
        :param raw_value: raw value of the constraint.
        :param as_quantity: if set, value is treated as a quantity containing also unit, and as
            such the raw value is converted to :py:class`pint.Quantity` instance.
        :param as_cast: if specified, this callable is used to convert raw value to its final type.
        :param original_constraint: when specified, new constraint logically belongs to
            ``original_constraint``, possibly representing one of its aspects.
        :param allowed_operators: if specified, only operators on this list are accepted.
        :param default_unit: if raw_value contains no unit, this unit will be appended.
        :raises ParseError: when parsing fails, or the operator is now allowed.
        :returns: a :py:class:`Constraint` representing the given specification.
        """

        allowed_operators = allowed_operators or INPUTABLE_OPERATORS

        parsed_value = CONSTRAINT_VALUE_PATTERN.match(raw_value)

        if not parsed_value:
            raise ParseError(constraint_name=name, raw_value=raw_value)

        groups = parsed_value.groupdict()

        if groups['operator']:
            operator = OPERATOR_SIGN_TO_OPERATOR[groups['operator']]

        else:
            operator = Operator.EQ

        if operator not in allowed_operators:
            raise ParseError(
                constraint_name=name,
                raw_value=raw_value,
                message=f"Operator '{operator} is not allowed.")

        raw_value = groups['value']

        if as_quantity:
            value: ConstraintValue = UNITS(raw_value)

            # Number-like raw_value, without units, get converted into
            # pure `int` or `float`. Force `Quantity` for quantities by
            # explicitly wrapping built-in types with `Quantity`.
            #
            # reportUnnecessaryIsInstance: pyright cannot infere this
            # little trick Pint plays with us, and considers the `isinstance`
            # call to be pointless. But it's not. mypy does not care...
            if not isinstance(
                    value,
                    pint.Quantity):  # type: ignore[reportUnnecessaryIsInstance,unused-ignore]
                value = pint.Quantity(value, default_unit)

        elif as_cast is not None:
            value = as_cast(raw_value)

        else:
            value = raw_value

        return cls(
            name=name,
            operator=operator,
            operator_handler=OPERATOR_TO_HANDLER[operator],
            value=value,
            raw_value=raw_value,
            original_constraint=original_constraint
            )

    def __repr__(self) -> str:
        return f'{self.printable_name}: {self.operator.value} {self.value}'

    def to_spec(self) -> Spec:
        return {
            self.name.replace('_', '-'): f'{self.operator.value} {self.value}'
            }

    def expand_name(self) -> ConstraintNameComponents:
        """
        Expand constraint name into its components.

        :returns: tuple consisting of constraint name components: name, optional indices, child
            properties, etc.
        """

        match = CONSTRAINT_NAME_PATTERN.match(self.name)

        # Cannot happen as long as we test our pattern well...
        assert match is not None

        groups = match.groupdict()

        return ConstraintNameComponents(
            name=groups['name'],
            peer_index=int(groups['peer_index']) if groups['peer_index'] is not None else None,
            child_name=groups['child_name']
            )

    @property
    def printable_name(self) -> str:
        components = self.expand_name()

        names: list[str] = []

        if components.peer_index is not None:
            names.append(f'{components.name.replace("_", "-")}[{components.peer_index}]')

        else:
            names.append(components.name)

        if components.child_name:
            names.append(components.child_name.replace("_", "-"))

        return '.'.join(names)

    def change_operator(self, operator: Operator) -> None:
        """
        Change operator of this constraint to a given one.

        :param operator: new operator.
        """

        self.operator = operator
        self.operator_handler = OPERATOR_TO_HANDLER[operator]

    def uses_constraint(self, constraint_name: str, logger: tmt.log.Logger) -> bool:
        """
        Inspect constraint whether it or its children use a constraint of a given name.

        :param constraint_name: constraint name to look for.
        :param logger: logger to use for logging.
        :returns: ``True`` if the given constraint or its children use given constraint name.
        """

        return self.expand_name().name == constraint_name

    def variants(
            self,
            members: Optional[list['Constraint[ConstraintValueT]']] = None
            ) -> Iterator[list['Constraint[ConstraintValueT]']]:
        """
        Generate all distinct variants of constraints covered by this one.

        For a trivial constraint, there is only one variant, and that is the
        constraint itself. In the case of compound constraints, the number of
        variants would be bigger, depending on the constraint's ``reducer``.

        :param members: if specified, each variant generated by this method is
            prepended with this list.
        :yields: iterator over all variants.
        """

        yield (members or []) + [self]


class SizeConstraint(Constraint['Size']):
    """ A constraint representing a size of resource, usually a storage """

    @classmethod
    def from_specification(
            cls: type[T],
            name: str,
            raw_value: str,
            original_constraint: Optional['Constraint[Any]'] = None,
            allowed_operators: Optional[list[Operator]] = None,
            default_unit: Optional[Any] = 'bytes'
            ) -> T:
        return cls._from_specification(
            name,
            raw_value,
            as_quantity=True,
            original_constraint=original_constraint,
            allowed_operators=allowed_operators,
            default_unit=default_unit
            )


class FlagConstraint(Constraint[bool]):
    """ A constraint representing a boolean flag, enabled/disabled, has/has not, etc. """

    @classmethod
    def from_specification(
            cls: type[T],
            name: str,
            raw_value: bool,
            original_constraint: Optional['Constraint[Any]'] = None,
            allowed_operators: Optional[list[Operator]] = None
            ) -> T:
        return cls._from_specification(
            name,
            str(raw_value),
            as_quantity=False,
            as_cast=lambda x: x.lower() == 'true',
            original_constraint=original_constraint,
            allowed_operators=allowed_operators
            )


class IntegerConstraint(Constraint[int]):
    """ A constraint representing a dimension-less int number """

    @classmethod
    def from_specification(
            cls: type[T],
            name: str,
            raw_value: str,
            original_constraint: Optional['Constraint[Any]'] = None,
            allowed_operators: Optional[list[Operator]] = None
            ) -> T:

        def _cast_int(raw_value: Any) -> int:
            if isinstance(raw_value, int):
                return raw_value

            if isinstance(raw_value, str):
                raw_value = raw_value.strip()

                if raw_value.startswith('0x'):
                    return int(raw_value, base=16)

                return int(raw_value)

            raise SpecificationError(f"Could not convert '{raw_value}' to a number.")

        return cls._from_specification(
            name,
            raw_value,
            as_quantity=False,
            as_cast=_cast_int,
            original_constraint=original_constraint,
            allowed_operators=allowed_operators
            )


class NumberConstraint(Constraint['Quantity']):
    """ A constraint representing a float number """

    @classmethod
    def from_specification(
            cls: type[T],
            name: str,
            raw_value: str,
            original_constraint: Optional['Constraint[Any]'] = None,
            allowed_operators: Optional[list[Operator]] = None,
            default_unit: Optional[Any] = None
            ) -> T:

        def _cast_number(raw_value: Any) -> float:
            if isinstance(raw_value, float):
                return raw_value

            if isinstance(raw_value, str):
                raw_value = raw_value.strip()
                return float(raw_value)

            raise SpecificationError(f"Could not convert '{raw_value}' to a number.")

        return cls._from_specification(
            name,
            raw_value,
            as_quantity=True,
            as_cast=_cast_number,
            original_constraint=original_constraint,
            allowed_operators=allowed_operators,
            default_unit=default_unit
            )


class TextConstraint(Constraint[str]):
    """ A constraint representing a string, e.g. a name """

    @classmethod
    def from_specification(
            cls: type[T],
            name: str,
            raw_value: str,
            original_constraint: Optional['Constraint[Any]'] = None,
            allowed_operators: Optional[list[Operator]] = None
            ) -> T:
        return cls._from_specification(
            name,
            raw_value,
            as_quantity=False,
            original_constraint=original_constraint,
            allowed_operators=allowed_operators
            )


@dataclasses.dataclass(repr=False)
class And(CompoundConstraint):
    """ Represents constraints that are grouped in ``and`` fashion """

    def __init__(self, constraints: Optional[list[BaseConstraint]] = None) -> None:
        """
        Hold constraints that are grouped in ``and`` fashion.

        :param constraints: list of constraints to group.
        """

        super().__init__(all, constraints=constraints)

    def variants(
            self,
            members: Optional[list[Constraint[Any]]] = None
            ) -> Iterator[list[Constraint[Any]]]:
        """
        Generate all distinct variants of constraints covered by this one.

        Since the ``and`` reducer demands all child constraints must be
        satisfied, and some of these constraints can also be compound
        constraints, we need to construct a cartesian product of variants
        yielded by child constraints to include all possible combinations.

        :param members: if specified, each variant generated by this method is
            prepended with this list.
        :yields: iterator over all variants.
        """

        members = members or []

        # List of non-compound constraints - we just slap these into every combination we generate
        simple_constraints: list[Constraint[Any]] = [
            constraint
            for constraint in self.constraints
            if isinstance(constraint, Constraint)
            ]

        # Compound constraints - these we will ask to generate their variants, and we produce
        # cartesian product from the output.
        compound_constraints = [
            constraint
            for constraint in self.constraints
            if isinstance(constraint, CompoundConstraint)
            ]

        for compounds in itertools.product(*[constraint.variants()
                                           for constraint in compound_constraints]):
            # Note that `product` returns an item for each iterable, and those items are lists,
            # because that's what `variants()` returns. Use `sum` to linearize the list of lists.
            yield members \
                + sum(compounds, cast(list[Constraint[Any]], [])) \
                + simple_constraints


@dataclasses.dataclass(repr=False)
class Or(CompoundConstraint):
    """ Represents constraints that are grouped in ``or`` fashion """

    def __init__(self, constraints: Optional[list[BaseConstraint]] = None) -> None:
        """
        Hold constraints that are grouped in ``or`` fashion.

        :param constraints: list of constraints to group.
        """

        super().__init__(any, constraints=constraints)

    def variants(
            self,
            members: Optional[list[Constraint[Any]]] = None
            ) -> Iterator[list[Constraint[Any]]]:
        """
        Generate all distinct variants of constraints covered by this one.

        Since the ``any`` reducer allows any child constraints to be satisfied
        for the whole group to evaluate as ``True``, it is trivial to generate
        variants - each child constraint shall provide its own "branch", and
        there is no need for products or joins of any kind.

        :param members: if specified, each variant generated by this method is
            prepended with this list.
        :yields: iterator over all variants.
        """

        members = members or []

        for constraint in self.constraints:
            for variant in constraint.variants():
                yield members + variant


#
# Constraint parsing
#

def ungroupify(fn: Callable[[Spec], BaseConstraint]) -> Callable[[Spec], BaseConstraint]:
    """
    Swap returned single-child compound constraint and that child.

    Helps reduce the number of levels in the constraint tree: if the return value
    is a compound constraint which contains just a single child, return the
    child instead of the compound constraint.

    Meant for constraints that do not have an index, e.g. ``memory`` or ``cpu``.
    For indexable constraints, see :py:func:`ungroupify_indexed`.
    """

    @functools.wraps(fn)
    def wrapper(spec: Spec) -> BaseConstraint:
        constraint = fn(spec)

        if isinstance(constraint, CompoundConstraint) and len(constraint.constraints) == 1:
            return constraint.constraints[0]

        return constraint

    return wrapper


def ungroupify_indexed(
        fn: Callable[[Spec, int], BaseConstraint]
        ) -> Callable[[Spec, int], BaseConstraint]:
    """
    Swap returned single-child compound constraint and that child.

    Helps reduce the number of levels in the constraint tree: if the return value
    is a compound constraint which contains just a single child, return the
    child instead of the compound constraint.

    Meant for constraints that have an index, e.g. ``disk`` or ``network``. For
    non-indexable constraints, see :py:func:`ungroupify`.
    """

    @functools.wraps(fn)
    def wrapper(spec: Spec, index: int) -> BaseConstraint:
        constraint = fn(spec, index)

        if isinstance(constraint, CompoundConstraint) and len(constraint.constraints) == 1:
            return constraint.constraints[0]

        return constraint

    return wrapper


def _parse_int_constraints(
        spec: Spec,
        prefix: str,
        constraint_keys: tuple[str, ...]) -> list[BaseConstraint]:
    """ Parse number-like constraints defined by a given set of keys, to int """

    return [
        IntegerConstraint.from_specification(
            f'{prefix}.{constraint_name.replace("-", "_")}',
            str(spec[constraint_name]),
            allowed_operators=[
                Operator.EQ, Operator.NEQ, Operator.LT, Operator.LTE, Operator.GT, Operator.GTE])
        for constraint_name in constraint_keys
        if constraint_name in spec
        ]


def _parse_number_constraints(
        spec: Spec,
        prefix: str,
        constraint_keys: tuple[str, ...],
        default_unit: Optional[Any] = None) -> list[BaseConstraint]:
    """ Parse number-like constraints defined by a given set of keys, to float """

    return [
        NumberConstraint.from_specification(
            f'{prefix}.{constraint_name.replace("-", "_")}',
            str(spec[constraint_name]),
            allowed_operators=[
                Operator.EQ, Operator.NEQ, Operator.LT, Operator.LTE, Operator.GT, Operator.GTE],
            default_unit=default_unit)
        for constraint_name in constraint_keys
        if constraint_name in spec
        ]


def _parse_size_constraints(
        spec: Spec,
        prefix: str,
        constraint_keys: tuple[str, ...]) -> list[BaseConstraint]:
    """ Parse size-like constraints defined by a given set of keys """

    return [
        SizeConstraint.from_specification(
            f'{prefix}.{constraint_name.replace("-", "_")}',
            str(spec[constraint_name]),
            allowed_operators=[
                Operator.EQ, Operator.NEQ, Operator.LT, Operator.LTE, Operator.GT, Operator.GTE])
        for constraint_name in constraint_keys
        if constraint_name in spec
        ]


def _parse_text_constraints(
        spec: Spec,
        prefix: str,
        constraint_keys: tuple[str, ...],
        allowed_operators: Optional[tuple[Operator, ...]] = None) -> list[BaseConstraint]:
    """ Parse text-like constraints defined by a given set of keys """

    allowed_operators = allowed_operators or (
        Operator.EQ, Operator.NEQ, Operator.MATCH, Operator.NOTMATCH)

    return [
        TextConstraint.from_specification(
            f'{prefix}.{constraint_name.replace("-", "_")}',
            str(spec[constraint_name]),
            allowed_operators=list(allowed_operators))
        for constraint_name in constraint_keys
        if constraint_name in spec
        ]


def _parse_flag_constraints(
        spec: Spec,
        prefix: str,
        constraint_keys: tuple[str, ...]) -> list[BaseConstraint]:
    """ Parse flag-like constraints defined by a given set of keys """

    return [
        FlagConstraint.from_specification(
            f'{prefix}.{constraint_name.replace("-", "_")}',
            spec[constraint_name],
            allowed_operators=[Operator.EQ, Operator.NEQ])
        for constraint_name in constraint_keys
        if constraint_name in spec
        ]


def _parse_device_core(
        spec: Spec,
        device_prefix: str = 'device',
        include_driver: bool = True,
        include_device: bool = True) -> And:
    """
    Parse constraints shared across device classes.

    :param spec: raw constraint block specification.
    :returns: block representation as :py:class:`BaseConstraint` or one of its subclasses.
    """

    group = And()

    number_constraints: tuple[str, ...] = ('vendor',)
    text_constraints: tuple[str, ...] = ('vendor-name',)

    if include_device:
        number_constraints = (*number_constraints, 'device')
        text_constraints = (*text_constraints, 'device-name')

    if include_driver:
        text_constraints = (*text_constraints, 'driver')

    group.constraints += _parse_int_constraints(spec, device_prefix, number_constraints)
    group.constraints += _parse_text_constraints(spec, device_prefix, text_constraints)

    return group


@ungroupify
def _parse_boot(spec: Spec) -> BaseConstraint:
    """
    Parse a boot-related constraints.

    :param spec: raw constraint block specification.
    :returns: block representation as :py:class:`BaseConstraint` or one of its subclasses.
    """

    group = And()

    if 'method' in spec:
        constraint = TextConstraint.from_specification(
            'boot.method',
            spec["method"],
            allowed_operators=[Operator.EQ, Operator.NEQ])

        if constraint.operator == Operator.EQ:
            constraint.change_operator(Operator.CONTAINS)

        elif constraint.operator == Operator.NEQ:
            constraint.change_operator(Operator.NOTCONTAINS)

        group.constraints += [constraint]

    return group


@ungroupify
def _parse_virtualization(spec: Spec) -> BaseConstraint:
    """
    Parse a virtualization-related constraints.

    :param spec: raw constraint block specification.
    :returns: block representation as :py:class:`BaseConstraint` or one of its subclasses.
    """

    group = And()

    group.constraints += _parse_flag_constraints(spec,
                                                 'virtualization',
                                                 ('is-virtualized',
                                                  'is-supported'))
    group.constraints += _parse_text_constraints(spec, 'virtualization', ('hypervisor',))

    return group


@ungroupify
def _parse_compatible(spec: Spec) -> BaseConstraint:
    """
    Parse constraints related to the compatible distro parameter.

    :param spec: raw constraint block specification.
    :returns: block representation as :py:class:`BaseConstraint` or one of its subclasses.
    """

    group = And()

    for distro in spec.get('distro', []):
        constraint = TextConstraint.from_specification('compatible.distro', distro)

        constraint.change_operator(Operator.CONTAINS)

        group.constraints += [constraint]

    return group


@ungroupify
def _parse_cpu(spec: Spec) -> BaseConstraint:
    """
    Parse a cpu-related constraints.

    :param spec: raw constraint block specification.
    :returns: block representation as :py:class:`BaseConstraint` or one of its subclasses.
    """

    group = And()

    group.constraints += _parse_int_constraints(
        spec,
        'cpu',
        (
            'processors',
            'sockets',
            'cores',
            'threads',
            'cores-per-socket',
            'threads-per-core',
            'model',
            'family',
            'vendor',
            'stepping',
            )
        )

    group.constraints += _parse_number_constraints(
        spec,
        'cpu',
        (
            'frequency',
            ),
        default_unit='MHz'
        )

    group.constraints += _parse_text_constraints(
        spec,
        'cpu',
        (
            'family-name',
            'model-name',
            'vendor-name'
            )
        )

    if 'flag' in spec:
        flag_group = And()

        for flag_spec in spec['flag']:
            constraint = TextConstraint.from_specification('cpu.flag', flag_spec)

            if constraint.operator == Operator.EQ:
                constraint.change_operator(Operator.CONTAINS)

            elif constraint.operator == Operator.NEQ:
                constraint.change_operator(Operator.NOTCONTAINS)

            flag_group.constraints += [constraint]

        group.constraints += [flag_group]

    if 'hyper-threading' in spec:
        group.constraints += [
            FlagConstraint.from_specification(
                'cpu.hyper_threading',
                spec['hyper-threading'],
                allowed_operators=[Operator.EQ, Operator.NEQ])
            ]

    return group


@ungroupify
def _parse_device(spec: Spec) -> BaseConstraint:
    """
    Parse a device-related constraints.

    :param spec: raw constraint block specification.
    :returns: block representation as :py:class:`BaseConstraint` or one of its subclasses.
    """

    return _parse_device_core(spec)


@ungroupify_indexed
def _parse_disk(spec: Spec, disk_index: int) -> BaseConstraint:
    """
    Parse a disk-related constraints.

    :param spec: raw constraint block specification.
    :param disk_index: index of this disk among its peers in specification.
    :returns: block representation as :py:class:`BaseConstraint` or one of its subclasses.
    """

    group = And()

    group.constraints += _parse_size_constraints(spec,
                                                 f'disk[{disk_index}]',
                                                 ('size',
                                                  'physical-sector-size',
                                                  'logical-sector-size'))
    group.constraints += _parse_text_constraints(spec,
                                                 f'disk[{disk_index}]', ('model-name', 'driver'))

    return group


@ungroupify
def _parse_disks(spec: Spec) -> BaseConstraint:
    """
    Parse a storage-related constraints.

    :param spec: raw constraint block specification.
    :returns: block representation as :py:class:`BaseConstraint` or one of its subclasses.
    """

    # The old-style constraint when `disk` was a mapping. Remove once v0.0.26 is gone.
    if isinstance(spec, dict):
        return _parse_disk(spec, 0)

    group = And()

    group.constraints += [
        _parse_disk(disk_spec, disk_index)
        for disk_index, disk_spec in enumerate(spec)
        ]

    return group


@ungroupify
def _parse_gpu(spec: Spec) -> BaseConstraint:
    """
    Parse a gpu-related constraints.

    :param spec: raw constraint block specification.
    :returns: block representation as :py:class:`BaseConstraint` or one of its subclasses.
    """

    return _parse_device_core(spec, device_prefix='gpu')


@ungroupify_indexed
def _parse_network(spec: Spec, network_index: int) -> BaseConstraint:
    """
    Parse a network-related constraints.

    :param spec: raw constraint block specification.
    :param network_index: index of this network among its peers in specification.
    :returns: block representation as :py:class:`BaseConstraint` or one of its subclasses.
    """

    group = _parse_device_core(spec, f'network[{network_index}]')
    group.constraints += _parse_text_constraints(spec, f'network[{network_index}]', ('type',))

    return group


@ungroupify
def _parse_networks(spec: Spec) -> BaseConstraint:
    """
    Parse a network-related constraints.

    :param spec: raw constraint block specification.
    :returns: block representation as :py:class:`BaseConstraint` or one of its subclasses.
    """

    group = And()

    group.constraints += [
        _parse_network(network_spec, network_index)
        for network_index, network_spec in enumerate(spec)
        ]

    return group


@ungroupify
def _parse_system(spec: Spec) -> BaseConstraint:
    """
    Parse constraints related to the ``system`` HW requirement.

    :param spec: raw constraint block specification.
    :returns: block representation as :py:class:`BaseConstraint` or one of its subclasses.
    """

    group = _parse_device_core(
        spec,
        device_prefix='system',
        include_driver=False,
        include_device=False)

    group.constraints += _parse_int_constraints(spec, 'system', ('model', 'numa-nodes'))
    group.constraints += _parse_text_constraints(spec, 'system', ('model-name',))

    return group


TPM_VERSION_ALLOWED_OPERATORS: tuple[Operator, ...] = (
    Operator.EQ, Operator.NEQ, Operator.LT, Operator.LTE, Operator.GT, Operator.GTE)


@ungroupify
def _parse_tpm(spec: Spec) -> BaseConstraint:
    """
    Parse constraints related to the ``tpm`` HW requirement.

    :param spec: raw constraint block specification.
    :returns: block representation as :py:class:`BaseConstraint` or one of its subclasses.
    """

    group = And()

    group.constraints += _parse_text_constraints(spec,
                                                 'tpm',
                                                 ('version',
                                                  ),
                                                 allowed_operators=TPM_VERSION_ALLOWED_OPERATORS)

    return group


def _parse_memory(spec: Spec) -> BaseConstraint:
    """
    Parse constraints related to the ``memory`` HW requirement.

    :param spec: raw constraint block specification.
    :returns: block representation as :py:class:`BaseConstraint` or one of its subclasses.
    """

    return SizeConstraint.from_specification(
        'memory',
        str(spec['memory']),
        allowed_operators=[
            Operator.EQ, Operator.NEQ, Operator.LT, Operator.LTE, Operator.GT, Operator.GTE])


def _parse_hostname(spec: Spec) -> BaseConstraint:
    """
    Parse constraints related to the ``hostname`` HW requirement.

    :param spec: raw constraint block specification.
    :returns: block representation as :py:class:`BaseConstraint` or one of its subclasses.
    """

    return TextConstraint.from_specification(
        'hostname',
        spec['hostname'],
        allowed_operators=[Operator.EQ, Operator.NEQ, Operator.MATCH, Operator.NOTMATCH])


@ungroupify
def _parse_zcrypt(spec: Spec) -> BaseConstraint:
    """
    Parse constraints related to the ``zcrypt`` HW requirement.

    :param spec: raw constraint block specification.
    :returns: block representation as :py:class:`BaseConstraint` or one of its subclasses.
    """

    group = And()

    group.constraints += _parse_text_constraints(spec, 'zcrypt', ('adapter', 'mode'))

    return group


@ungroupify
def _parse_iommu(spec: Spec) -> BaseConstraint:
    """
    Parse constraints related to the ``iommu`` HW requirement.

    :param spec: raw constraint block specification.
    :returns: block representation as :py:class:`BaseConstraint` or one of its subclasses.
    """

    group = And()

    group.constraints += _parse_flag_constraints(spec,
                                                 'iommu',
                                                 ('is-supported',))
    group.constraints += _parse_text_constraints(spec, 'iommu', ('model-name',))

    return group


@ungroupify
def _parse_location(spec: Spec) -> BaseConstraint:
    """
    Parse constraints related to the ``location`` HW requirement.

    :param spec: raw constraint block specification.
    :returns: block representation as :py:class:`BaseConstraint` or one of its subclasses.
    """

    group = And()

    group.constraints += _parse_text_constraints(spec, 'location', ('lab-controller',))

    return group


@ungroupify
def _parse_beaker(spec: Spec) -> BaseConstraint:
    """
    Parse constraints related to the ``beaker`` HW requirement.

    :param spec: raw constraint block specification.
    :returns: block representation as :py:class:`BaseConstraint` or one of its subclasses.
    """

    group = And()

    group.constraints += _parse_text_constraints(spec, 'beaker', ('pool',),
                                                 allowed_operators=(Operator.EQ, Operator.NEQ))

    return group


@ungroupify
def _parse_generic_spec(spec: Spec) -> BaseConstraint:
    """
    Parse actual constraints.

    :param spec: raw constraint block specification.
    :returns: block representation as :py:class:`BaseConstraint` or one of its subclasses.
    """

    group = And()

    if 'arch' in spec:
        group.constraints += [
            TextConstraint.from_specification(
                'arch',
                spec['arch'])
            ]

    if 'beaker' in spec:
        group.constraints += [_parse_beaker(spec['beaker'])]

    if 'boot' in spec:
        group.constraints += [_parse_boot(spec['boot'])]

    if 'compatible' in spec:
        group.constraints += [_parse_compatible(spec['compatible'])]

    if 'cpu' in spec:
        group.constraints += [_parse_cpu(spec['cpu'])]

    if 'device' in spec:
        group.constraints += [_parse_device(spec['device'])]

    if 'gpu' in spec:
        group.constraints += [_parse_gpu(spec['gpu'])]

    if 'memory' in spec:
        group.constraints += [_parse_memory(spec)]

    if 'disk' in spec:
        group.constraints += [_parse_disks(spec['disk'])]

    if 'network' in spec:
        group.constraints += [_parse_networks(spec['network'])]

    if 'hostname' in spec:
        group.constraints += [_parse_hostname(spec)]

    if 'location' in spec:
        group.constraints += [_parse_location(spec['location'])]

    if 'system' in spec:
        group.constraints += [_parse_system(spec['system'])]

    if 'tpm' in spec:
        group.constraints += [_parse_tpm(spec['tpm'])]

    if 'virtualization' in spec:
        group.constraints += [_parse_virtualization(spec['virtualization'])]

    if 'zcrypt' in spec:
        group.constraints += [_parse_zcrypt(spec['zcrypt'])]

    if 'iommu' in spec:
        group.constraints += [_parse_iommu(spec['iommu'])]

    return group


@ungroupify
def _parse_and(spec: Spec) -> BaseConstraint:
    """
    Parse an ``and`` clause holding one or more subblocks or constraints.

    :param spec: raw constraint block specification.
    :returns: block representation as :py:class:`BaseConstraint` or one of its subclasses.
    """

    group = And()

    group.constraints += [
        _parse_block(member)
        for member in spec
        ]

    return group


@ungroupify
def _parse_or(spec: Spec) -> BaseConstraint:
    """
    Parse an ``or`` clause holding one or more subblocks or constraints.

    :param spec: raw constraint block specification.
    :returns: block representation as :py:class:`BaseConstraint` or one of its subclasses.
    """

    group = Or()

    group.constraints += [
        _parse_block(member)
        for member in spec
        ]

    return group


@ungroupify
def _parse_block(spec: Spec) -> BaseConstraint:
    """
    Parse a generic block of HW constraints - may contain ``and`` and ``or``
    subblocks and actual constraints.

    :param spec: raw constraint block specification.
    :returns: block representation as :py:class:`BaseConstraint` or one of its
    subclasses.
    """

    if 'and' in spec:
        return _parse_and(spec['and'])

    if 'or' in spec:
        return _parse_or(spec['or'])

    return _parse_generic_spec(spec)


def parse_hw_requirements(spec: Spec) -> BaseConstraint:
    """
    Convert raw specification of HW constraints to our internal representation.

    :param spec: raw constraints specification as stored in an environment.
    :returns: root of HW constraints tree.
    """

    return _parse_block(spec)


@dataclasses.dataclass
class Hardware(SpecBasedContainer[Spec, Spec]):
    constraint: Optional[BaseConstraint]
    spec: Spec

    @classmethod
    def from_spec(cls: type['Hardware'], spec: Spec) -> 'Hardware':
        if not spec:
            return Hardware(constraint=None, spec=spec)

        return Hardware(
            constraint=parse_hw_requirements(spec),
            spec=spec
            )

    def to_spec(self) -> Spec:
        return self.spec

    def to_minimal_spec(self) -> Spec:
        return self.spec

    def and_(self, constraint: BaseConstraint) -> None:
        if self.constraint:
            group = And()

            group.constraints = [
                self.constraint,
                constraint
                ]

            self.constraint = group

        else:
            self.constraint = constraint

        self.spec = self.constraint.to_spec()

    def report_support(
            self,
            *,
            names: Optional[list[str]] = None,
            check: Optional[Callable[[Constraint[Any]], bool]] = None,
            logger: tmt.log.Logger) -> None:
        """
        Report all unsupported constraints.

        A helper method for plugins: plugin provides a callback which checks
        whether a given constraint is or is not supported by the plugin, and
        method calls the callback for each constraint stored in this container.

        Both ``names`` and ``check`` are optional, and both can be used and
        combined. First, the ``names`` list is checked, if a constraint is not
        found, ``check`` is called if it's defined.

        :param names: a list of constraint names. If a constraint name is on
            this list, it is considered to be supported by the ``report_support``
            caller. Caller may list both full constraint name, e.g. ``cpu.cores``,
            or just the subsystem name, ``cpu``, indicating all child constraints
            are supported.
        :param check: a callback to call for each constraint in this container.
            Accepts a single parameter, a constraint to check, and if its return
            value is true-ish, the constraint is considered to be supported
            by the ``report_support`` caller.
        """

        if not self.constraint:
            return

        names = names or []
        check = check or (lambda _: False)

        for variant in self.constraint.variants():
            for constraint in variant:
                name, _, child_name = constraint.expand_name()

                if name in names \
                        or f'{name}.{child_name}' in names \
                        or check(constraint):
                    continue

                logger.warning(
                    f"Hardware requirement '{constraint.printable_name}' is not supported.")

    def format_variants(self) -> Iterator[str]:
        """
        Format variants of constraints.

        :yields: for each variant, which is nothing but a list of constraints,
            method yields a string variant's serial number and formatted
            constraints.
        """

        if self.constraint is None:
            return

        for i, constraints in enumerate(self.constraint.variants(), start=1):
            for constraint in constraints:
                yield f'variant #{i}: {constraint!s}'
