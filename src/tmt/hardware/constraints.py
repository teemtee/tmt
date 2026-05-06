import abc
import enum
import itertools
import operator
import re
from collections.abc import Iterable, Iterator
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    NamedTuple,
    Optional,
    Union,
    cast,
)

import pint

import tmt.log
import tmt.utils

from ..container import SpecBasedContainer, container
from ..utils import SpecificationError

if TYPE_CHECKING:
    from pint import Quantity

    from .._compat.typing import TypeAlias

    #: A type of values describing sizes of things like storage or RAM.
    # Note: type-hinting is a bit wonky with pyright
    # https://github.com/hgrecco/pint/issues/1166
    Size: TypeAlias = Quantity

#: Unit registry, used and shared by all code.
UNITS = pint.UnitRegistry()

# The default formatting should use unit symbols rather than full names.
# reportDeprecated: in some Pint versions, this method is deprecated.
UNITS.default_format = '~'  # type: ignore[reportDeprecated,unused-ignore]


class Operator(enum.Enum):
    """
    Binary operators defined by specification
    """

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

    #: Needle must be present in the haystack.
    CONTAINS = 'contains'
    #: Needle must not be present in the haystack.
    NOTCONTAINS = 'not contains'
    #: Needle may be present in the haystack as long it is not the only item.
    NOTCONTAINS_EXCLUSIVE = 'not contains exclusive'


INPUTABLE_OPERATORS = [
    operator
    for operator in Operator.__members__.values()
    if operator not in (Operator.CONTAINS, Operator.NOTCONTAINS, Operator.NOTCONTAINS_EXCLUSIVE)
]


_OPERATOR_PATTERN = '|'.join(operator.value for operator in INPUTABLE_OPERATORS)

#: Regular expression to match and split the ``value`` part of a key:value pair.
#: The input consists of an (optional) operator, the actual value of the
#: constraint, and (optional) units. As a result, pattern yields two groups,
#: ``operator`` and ``value``, the latter containing both the value and units.
CONSTRAINT_VALUE_PATTERN = re.compile(
    rf"""
    ^                                   # must match the whole string
    (?P<operator>{_OPERATOR_PATTERN})?  # optional operator
    \s*                                 # operator might be separated by white space
    (?P<value>.+?)                      # actual value of the constraint
    \s*                                 # there might be trailing white space
    $                                   # must match the whole string, I said :)
    """,
    re.VERBOSE,
)

#: Regular expression to match and split a HW constraint name into its
#: components. The input consists of a constraint name, (optional) index
#: of the constraint among its peers, and (optional) child constraint name:
#:
#: * ``memory`` => ``memory``, ``None``, ``None``
#: * ``cpu.processors`` => ``cpu``, ``None``, ``processors``
#: * ``disk[1].size`` => ``disk``, ``1``, ``size``
CONSTRAINT_NAME_PATTERN = re.compile(
    r"""
    (?P<name>[a-z_+]+)                   # constraint name is mandatory
    (?:\[(?P<peer_index>[+-]?\d+)\])?    # index is optional
    (?:\.(?P<child_name>[a-z_]+))?       # child constraint name is also optional'
    """,
    re.VERBOSE,
)

#: Regular expression to match and split a HW constraint into its components.
#: The input consists of a constraint name, (optional) index of the constraint
#: among its peers, (optional) child constraint name, (optional) operator, and
#: value.
#:
#: * ``memory 10 GiB`` => ``memory``, ``None``, ``None``, ``None``, ``10 GiB``
#: * ``cpu.processors != 4`` => ``cpu``, ``None``, ``processors``, ``!=``, ``4``
#: * ``disk[1].size <= 1 TiB`` => ``disk``, ``1``, ``size``, ``<=``, ``1 TiB``
CONSTRAINT_COMPONENTS_PATTERN = re.compile(
    rf"""
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
    """,
    re.VERBOSE,
)


#: A list of constraint names that operate over sequence of entities.
INDEXABLE_CONSTRAINTS: tuple[str, ...] = (
    'disk',
    'network',
)

#: A list of constraint names that do not have child properties.
CHILDLESS_CONSTRAINTS: tuple[str, ...] = (
    'arch',
    'memory',
    'hostname',
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

# TODO: this was ported from Artemis but it's not used as of now. That should
# change with future support for flavors aka instance types.
#
#: A type of values that can be measured, and may or may not have units.
#: A subset of :py:member:`ConstraintValue`.
# MeasurableConstraintValueType = Union[int, 'Size']


class ConstraintNameComponents(NamedTuple):
    """
    Components of a constraint name
    """

    #: ``disk`` of ``disk[1].size``
    name: str
    #: ``1`` of ``disk[1].size``
    peer_index: Optional[int]
    #: ``size`` of ``disk[1].size``
    child_name: Optional[str]


@container
class ConstraintComponents:
    """
    Components of a constraint
    """

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
            value=groups['value'],
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


def not_contains_exclusive(haystack: list[str], needle: str) -> bool:
    """
    Find out whether an item is in the given list.

    .. note::

       A variant of :py:func:`not_contains`: an item may be present,
       as long as other items are present.

    :param haystack: container to examine.
    :param needle: item to look for in ``haystack``.
    :returns: ``True`` if ``needle`` is **not** in ``haystack`` or if
        ``needle`` is in ``haystack`` but other items are there as well.
    """

    return haystack != [needle]


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
    '=~': Operator.MATCH,
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
    Operator.NOTCONTAINS: not_contains,
    Operator.NOTCONTAINS_EXCLUSIVE: not_contains_exclusive,
}


#: A callable reducing a sequence of booleans to a single one. Think
#: :py:func:`any` or :py:func:`all`.
ReducerType = Callable[[Iterable[bool]], bool]


class ParseError(tmt.utils.MetadataError):
    """
    Raised when HW requirement parsing fails
    """

    def __init__(
        self, constraint_name: str, raw_value: str, message: Optional[str] = None
    ) -> None:
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


@container(repr=False)
class BaseConstraint(SpecBasedContainer[Spec, Spec]):
    """
    Base class for all classes representing one or more constraints
    """

    @classmethod
    def from_spec(cls, spec: Any) -> 'BaseConstraint':
        import tmt.hardware.requirements

        return tmt.hardware.requirements.parse_hw_requirements(spec)

    @abc.abstractmethod
    def to_spec(self) -> Spec:
        raise NotImplementedError

    def to_minimal_spec(self) -> Spec:
        return self.to_spec()

    @abc.abstractmethod
    def uses_constraint(self, constraint_name: str, logger: tmt.log.Logger) -> bool:
        """
        Inspect constraint whether the constraint or one of its children use a constraint of
        a given name.

        :param constraint_name: constraint name to look for.
        :param logger: logger to use for logging.
        :raises NotImplementedError: method is left for child classes to implement.
        """

        raise NotImplementedError

    @abc.abstractmethod
    def variants(
        self, members: Optional[list['Constraint']] = None
    ) -> Iterator[list['Constraint']]:
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

    def variant(self) -> list['Constraint']:
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


@container(repr=False)
class CompoundConstraint(BaseConstraint):
    """
    Base class for all *compound* constraints
    """

    def __init__(
        self, reducer: ReducerType = any, constraints: Optional[list[BaseConstraint]] = None
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
            constraint.uses_constraint(constraint_name, logger) for constraint in self.constraints
        )

    @abc.abstractmethod
    def variants(
        self, members: Optional[list['Constraint']] = None
    ) -> Iterator[list['Constraint']]:
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


@container(repr=False)
class Constraint(BaseConstraint):
    """
    A constraint imposing a particular limit to one of the guest properties
    """

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
    value: Any  # Subclasses will specialize further

    # Stored for possible inspection by more advanced processing.
    raw_value: str

    # If set, it is a raw unit specified by the constraint.
    default_unit: Optional[str] = None

    # If set, it is a "bigger" constraint, to which this constraint logically
    # belongs as one of its aspects.
    original_constraint: Optional['Constraint'] = None

    @classmethod
    def _from_specification(
        cls,
        name: str,
        raw_value: str,
        as_quantity: bool = True,
        as_cast: Optional[Callable[[str], ConstraintValue]] = None,
        original_constraint: Optional['Constraint'] = None,
        allowed_operators: Optional[list[Operator]] = None,
        default_unit: Optional[Any] = "bytes",
    ) -> 'Constraint':
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
                message=f"Operator '{operator} is not allowed.",
            )

        raw_value = groups['value']

        if as_quantity:
            value = UNITS(raw_value)

            # pint < 0.25.3:
            # Number-like raw_value, without units, get converted into
            # pure `int` or `float`. Force `Quantity` for quantities by
            # explicitly wrapping built-in types with `Quantity`.
            if not isinstance(value, pint.Quantity):
                value = pint.Quantity(value, default_unit)

            # Make sure the value has appropriate units if it was not provided
            if value.unitless and default_unit:
                value *= UNITS(default_unit)

        elif as_cast is not None:
            # Type depends on the `as_cast` function; subclasses handle the specific type.
            value = as_cast(raw_value)  # type: ignore[assignment]

        else:
            # Type depends on `as_quantity`; subclasses handle the specific type.
            value = raw_value  # type: ignore[assignment]

        return cls(
            name=name,
            operator=operator,
            operator_handler=OPERATOR_TO_HANDLER[operator],
            value=value,
            raw_value=raw_value,
            original_constraint=original_constraint,
        )

    def __repr__(self) -> str:
        return f'{self.printable_name}: {self.operator.value} {self.value}'

    def to_spec(self) -> Spec:
        return {self.name.replace('_', '-'): f'{self.operator.value} {self.value}'}

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
            child_name=groups['child_name'],
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
        self, members: Optional[list['Constraint']] = None
    ) -> Iterator[list['Constraint']]:
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


class SizeConstraint(Constraint):
    """
    A constraint representing a size of resource, usually a storage
    """

    value: 'Size'

    @classmethod
    def from_specification(
        cls,
        name: str,
        raw_value: str,
        original_constraint: Optional['Constraint'] = None,
        allowed_operators: Optional[list[Operator]] = None,
        default_unit: Optional[Any] = 'bytes',
    ) -> 'SizeConstraint':
        constraint = cast(
            SizeConstraint,
            cls._from_specification(
                name,
                raw_value,
                as_quantity=True,
                original_constraint=original_constraint,
                allowed_operators=allowed_operators,
                default_unit=default_unit,
            ),
        )
        # Validate that the unit is compatible with the expected dimensionality
        # For size constraints (like memory, disk size), validate conversion to bytes
        try:
            constraint.value.to('bytes')

        except Exception as exc:
            raise ParseError(
                constraint_name=name,
                raw_value=raw_value,
                message="Invalid unit: expected a data size unit (e.g., MB, MiB, GB)",
            ) from exc

        return constraint


class FlagConstraint(Constraint):
    """
    A constraint representing a boolean flag, enabled/disabled, has/has not, etc.
    """

    value: bool

    @classmethod
    def from_specification(
        cls,
        name: str,
        raw_value: bool,
        original_constraint: Optional['Constraint'] = None,
        allowed_operators: Optional[list[Operator]] = None,
    ) -> 'FlagConstraint':
        return cast(
            FlagConstraint,
            cls._from_specification(
                name,
                str(raw_value),
                as_quantity=False,
                as_cast=lambda x: x.lower() == 'true',
                original_constraint=original_constraint,
                allowed_operators=allowed_operators,
            ),
        )


class IntegerConstraint(Constraint):
    """
    A constraint representing a dimension-less int number
    """

    value: int

    @classmethod
    def from_specification(
        cls,
        name: str,
        raw_value: str,
        original_constraint: Optional['Constraint'] = None,
        allowed_operators: Optional[list[Operator]] = None,
    ) -> 'IntegerConstraint':
        def _cast_int(raw_value: Any) -> int:
            if isinstance(raw_value, int):
                return raw_value

            if isinstance(raw_value, str):
                raw_value = raw_value.strip()

                if raw_value.startswith('0x'):
                    return int(raw_value, base=16)

                return int(raw_value)

            raise SpecificationError(f"Could not convert '{raw_value}' to a number.")

        return cast(
            IntegerConstraint,
            cls._from_specification(
                name,
                raw_value,
                as_quantity=False,
                as_cast=_cast_int,
                original_constraint=original_constraint,
                allowed_operators=allowed_operators,
            ),
        )


class NumberConstraint(Constraint):
    """
    A constraint representing a float number
    """

    value: 'Quantity'

    @classmethod
    def from_specification(
        cls,
        name: str,
        raw_value: str,
        original_constraint: Optional['Constraint'] = None,
        allowed_operators: Optional[list[Operator]] = None,
        default_unit: Optional[Any] = None,
    ) -> 'NumberConstraint':
        def _cast_number(raw_value: Any) -> float:
            if isinstance(raw_value, float):
                return raw_value

            if isinstance(raw_value, str):
                raw_value = raw_value.strip()
                return float(raw_value)

            raise SpecificationError(f"Could not convert '{raw_value}' to a number.")

        return cast(
            NumberConstraint,
            cls._from_specification(
                name,
                raw_value,
                as_quantity=True,
                as_cast=_cast_number,
                original_constraint=original_constraint,
                allowed_operators=allowed_operators,
                default_unit=default_unit,
            ),
        )


class TextConstraint(Constraint):
    """
    A constraint representing a string, e.g. a name
    """

    value: str

    @classmethod
    def from_specification(
        cls,
        name: str,
        raw_value: str,
        original_constraint: Optional['Constraint'] = None,
        allowed_operators: Optional[list[Operator]] = None,
    ) -> 'TextConstraint':
        return cast(
            TextConstraint,
            cls._from_specification(
                name,
                raw_value,
                as_quantity=False,
                original_constraint=original_constraint,
                allowed_operators=allowed_operators,
            ),
        )


@container(repr=False)
class And(CompoundConstraint):
    """
    Represents constraints that are grouped in ``and`` fashion
    """

    def __init__(self, constraints: Optional[list[BaseConstraint]] = None) -> None:
        """
        Hold constraints that are grouped in ``and`` fashion.

        :param constraints: list of constraints to group.
        """

        super().__init__(all, constraints=constraints)

    def variants(
        self, members: Optional[list['Constraint']] = None
    ) -> Iterator[list['Constraint']]:
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
        simple_constraints: list[Constraint] = [
            constraint for constraint in self.constraints if isinstance(constraint, Constraint)
        ]

        # Compound constraints - these we will ask to generate their variants, and we produce
        # cartesian product from the output.
        compound_constraints = [
            constraint
            for constraint in self.constraints
            if isinstance(constraint, CompoundConstraint)
        ]

        for compounds in itertools.product(
            *[constraint.variants() for constraint in compound_constraints]
        ):
            # Note that `product` returns an item for each iterable, and those items are lists,
            # because that's what `variants()` returns. Use `sum` to linearize the list of lists.
            yield members + sum(compounds, cast(list['Constraint'], [])) + simple_constraints


@container(repr=False)
class Or(CompoundConstraint):
    """
    Represents constraints that are grouped in ``or`` fashion
    """

    def __init__(self, constraints: Optional[list[BaseConstraint]] = None) -> None:
        """
        Hold constraints that are grouped in ``or`` fashion.

        :param constraints: list of constraints to group.
        """

        super().__init__(any, constraints=constraints)

    def variants(
        self, members: Optional[list['Constraint']] = None
    ) -> Iterator[list['Constraint']]:
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
