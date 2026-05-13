import functools
from collections.abc import Iterator
from typing import Any, Callable, Generic, Optional, Protocol, TypeVar, Union, cast

import tmt.log
from tmt.container import SpecBasedContainer, container, simple_field
from tmt.hardware.constraints import (
    And,
    BaseConstraint,
    CompoundConstraint,
    Constraint,
    FlagConstraint,
    IntegerConstraint,
    NumberConstraint,
    Operator,
    Or,
    SizeConstraint,
    Spec,
    TextConstraint,
)

BaseConstraintT = TypeVar('BaseConstraintT', bound=BaseConstraint, covariant=True)  # noqa: PLC0105
ConstraintT = TypeVar('ConstraintT', bound=Constraint, covariant=True)  # noqa: PLC0105


#: Type of a requirement parser.
class RequirementParser(Protocol, Generic[BaseConstraintT]):
    def __call__(self, spec: Spec, peer_index: Optional[int] = None) -> BaseConstraintT:
        raise NotImplementedError


def _flatten(constraint: BaseConstraint) -> BaseConstraint:
    """
    Replace a single-child compound constraint with that child.

    Effectively "flattens" the compound constraint when it contains only
    a single child.
    """

    if isinstance(constraint, CompoundConstraint) and len(constraint.constraints) == 1:
        return constraint.constraints[0]

    return constraint


def flatten(fn: Callable[[Spec], BaseConstraint]) -> Callable[[Spec], BaseConstraint]:
    """
    Replace a returned single-child compound constraint with that child.

    Effectively "flattens" the compound constraint when it contains only
    a single child.
    """

    @functools.wraps(fn)
    def wrapper(spec: Spec) -> BaseConstraint:
        return _flatten(fn(spec))

    return wrapper


@container
class _Parser(Generic[BaseConstraintT]):
    """
    Base class for requirement parser description.
    """

    #: Requirement the parser would process: ``hostname``,
    #: ``compatible.distro``, ``disk[].size``, and so on.
    requirement: str


@container
class _TrivialParser(_Parser[ConstraintT]):
    """
    Base class for simple parser that can be statically defined.
    """

    #: Constraint class whose :py:meth:`Constraint.from_specification`
    #: method would be used to parse the requirement.
    constraint_class: type[ConstraintT]

    #: Optional keyword arguments to pass to
    #: :py:meth:`Constraint.from_specification` method.
    kwargs: dict[str, Any] = simple_field(default_factory=dict[str, Any])


@container
class SingleLevelParser(_TrivialParser[ConstraintT]):
    """
    A single-level parser for requirements that have no child keys.
    """

    def parse(self, spec: Spec, peer_index: Optional[int] = None) -> ConstraintT:
        return self.constraint_class.from_specification(
            self.requirement,
            str(spec[self.requirement]),
            **self.kwargs,
        )


@container
class DoubleLevelParser(_TrivialParser[ConstraintT]):
    """
    A double-level parser for requirements that do have child keys.
    """

    @functools.cached_property
    def constraint_name(self) -> str:
        return self.requirement.split('.', 1)[0]

    @functools.cached_property
    def child_constraint_name(self) -> str:
        return self.requirement.split('.', 1)[1]

    def parse(self, spec: Spec, peer_index: Optional[int] = None) -> ConstraintT:
        return self.constraint_class.from_specification(
            self.requirement,
            str(spec[self.child_constraint_name]),
            **self.kwargs,
        )


@container
class IndexedDoubleLevelParser(DoubleLevelParser[ConstraintT]):
    """
    A double-level parser for requirements that do have child keys and peers.
    """

    def parse(self, spec: Spec, peer_index: Optional[int] = None) -> ConstraintT:
        return self.constraint_class.from_specification(
            f'{self.constraint_name}[{peer_index}].{self.child_constraint_name}',
            str(spec[self.child_constraint_name]),
            **self.kwargs,
        )


@container
class CustomParser(_Parser[BaseConstraintT]):
    """
    A parser with custom code that cannot be statically defined.
    """

    requirement: str
    parse: RequirementParser[BaseConstraintT]


SLP = SingleLevelParser
DLP = DoubleLevelParser
IDLP = IndexedDoubleLevelParser


def generate_device_parsers(
    device_prefix: str = 'device',
    include_driver: bool = True,
    include_device: bool = True,
    parser_class: Union[type[DLP[Constraint]], type[IDLP[Constraint]]] = DLP,
) -> Iterator[Union[DLP[Constraint], IDLP[Constraint]]]:
    yield parser_class(f'{device_prefix}.vendor', IntegerConstraint)
    yield parser_class(f'{device_prefix}.vendor-name', TextConstraint)

    if include_device:
        yield parser_class(f'{device_prefix}.device', IntegerConstraint)
        yield parser_class(f'{device_prefix}.device-name', TextConstraint)

    if include_driver:
        yield parser_class(f'{device_prefix}.driver', TextConstraint)


def custom_parser(fn: RequirementParser[BaseConstraint]) -> RequirementParser[BaseConstraint]:
    """
    A decorator marking a function as a hardware requirement parser.

    Function name is expected to provide the hardware requirement name it
    parses:

    * the initial ``parser_`` prefix is stripped away,
    * the first ``_`` is replaced with ``.``,
    * ``_`` characters are relaced with ``-``.

    .. code-block::

        parse_beaker_pool => beaker.pool
        parse_memory => memory
        parse_virtualization_is_supported => virtualization.is-supported

    :param fn: function to decorate.
    """

    global _REQUIREMENT_PARSERS

    # Being a mere callable, special care is needed to get its name. We
    # *know* it will have a name, as we use functions and methods only,
    # but in general, not all callables have `__name__`, and linter
    # cannot tell.
    fn_name: Optional[str] = getattr(fn, '__name__')  # noqa: B009

    assert isinstance(fn_name, str)  # narrow type

    _REQUIREMENT_PARSERS.append(
        CustomParser(
            requirement=fn_name.replace('parse_', '').replace('_', '.', 1).replace('_', '-'),
            parse=fn,
        )
    )

    @functools.wraps(fn)
    def _parse(spec: Spec, peer_index: Optional[int] = None) -> BaseConstraint:
        return _flatten(fn(spec, peer_index=peer_index))

    return _parse


TPM_VERSION_ALLOWED_OPERATORS = (
    Operator.EQ,
    Operator.NEQ,
    Operator.LT,
    Operator.LTE,
    Operator.GT,
    Operator.GTE,
)


#: Registered hardware requirement parsers.
#:
#: .. note::
#:
#:    The list is kept sorted by the hardware requirement name. This is not
#:    needed for tmt to work correctly, but it makes testing easier as
#:    the YAML representation of parsed hardware requirements have predictable
#:    order of keys.
_REQUIREMENT_PARSERS: list[Union[CustomParser[Any], SLP[Any], DLP[Any], IDLP[Any]]] = [
    # arch
    SLP('arch', TextConstraint),
    # beaker
    DLP('beaker.panic-watchdog', FlagConstraint),
    DLP('beaker.pool', TextConstraint, {'allowed_operators': (Operator.EQ, Operator.NEQ)}),
    # cpu
    DLP('cpu.cores', IntegerConstraint),
    DLP('cpu.cores-per-socket', IntegerConstraint),
    DLP('cpu.family', IntegerConstraint),
    DLP('cpu.hyper-threading', FlagConstraint, {'allowed_operators': (Operator.EQ, Operator.NEQ)}),
    DLP('cpu.model', IntegerConstraint),
    DLP('cpu.processors', IntegerConstraint),
    DLP('cpu.sockets', IntegerConstraint),
    DLP('cpu.threads', IntegerConstraint),
    DLP('cpu.threads-per-core', IntegerConstraint),
    DLP('cpu.vendor', IntegerConstraint),
    DLP('cpu.stepping', IntegerConstraint),
    DLP('cpu.frequency', NumberConstraint, {'default_unit': 'MHz'}),
    DLP('cpu.family-name', TextConstraint),
    DLP('cpu.model-name', TextConstraint),
    DLP('cpu.vendor-name', TextConstraint),
    # device
    *generate_device_parsers(),
    # disk
    IDLP('disk.size', SizeConstraint),
    IDLP('disk.logical-sector-size', SizeConstraint),
    IDLP('disk.physical-sector-size', SizeConstraint),
    IDLP('disk.model-name', TextConstraint),
    IDLP('disk.driver', TextConstraint),
    # gpu
    *generate_device_parsers(device_prefix='gpu'),
    # hostname
    SLP('hostname', TextConstraint),
    # iommu
    DLP('iommu.is-supported', FlagConstraint),
    DLP('iommu.model-name', TextConstraint),
    # location
    DLP('location.lab-controller', TextConstraint),
    # memory
    SLP('memory', SizeConstraint, {'default_unit': 'MiB'}),
    # network
    *generate_device_parsers(device_prefix='network', parser_class=IDLP),
    IDLP('network.type', TextConstraint),
    # system
    *generate_device_parsers(device_prefix='system', include_driver=False, include_device=False),
    DLP('system.model', IntegerConstraint),
    DLP('system.numa-nodes', IntegerConstraint),
    DLP('system.model-name', TextConstraint),
    DLP('system.type', TextConstraint),
    # tpm
    DLP(
        'tpm.version',
        TextConstraint,
        {'allowed_operators': TPM_VERSION_ALLOWED_OPERATORS},
    ),
    # virtualization
    DLP('virtualization.is-virtualized', FlagConstraint),
    DLP('virtualization.is-supported', FlagConstraint),
    DLP('virtualization.confidential', FlagConstraint),
    DLP('virtualization.hypervisor', TextConstraint),
    # zcrypt
    DLP('zcrypt.adapter', TextConstraint),
    DLP('zcrypt.mode', TextConstraint),
]


@custom_parser
def parse_boot_method(spec: Spec, peer_index: Optional[int] = None) -> TextConstraint:
    constraint = TextConstraint.from_specification(
        'boot.method', spec['method'], allowed_operators=(Operator.EQ, Operator.NEQ)
    )

    if constraint.operator == Operator.EQ:
        constraint.change_operator(Operator.CONTAINS)

    elif constraint.operator == Operator.NEQ:
        constraint.change_operator(Operator.NOTCONTAINS_EXCLUSIVE)

    return constraint


@custom_parser
def parse_compatible_distro(spec: Spec, peer_index: Optional[int] = None) -> And:
    group = And()

    for distro in cast(list[str], (spec['distro'] or [])):
        constraint = TextConstraint.from_specification('compatible.distro', distro)

        constraint.change_operator(Operator.CONTAINS)

        group.constraints.append(constraint)

    return group


@custom_parser
def parse_cpu_flag(spec: Spec, peer_index: Optional[int] = None) -> And:
    group = And()

    for flag_spec in spec['flag']:
        constraint = TextConstraint.from_specification('cpu.flag', flag_spec)

        if constraint.operator == Operator.EQ:
            constraint.change_operator(Operator.CONTAINS)

        elif constraint.operator == Operator.NEQ:
            constraint.change_operator(Operator.NOTCONTAINS)

        group.constraints.append(constraint)

    return group


@flatten
def _parse_requirements(spec: Spec) -> BaseConstraint:
    """
    Parse a block of hardware requirements.

    A block is a mapping that contains one or more hardware requirements
    as keys and their values. It cannot contain neither ``and`` nor ``or``
    keys.
    """

    group = And()

    # Iterate over keys of the ``spec`` mapping. When the corresponding
    # value is:
    #
    # * a mapping: a double-level requirement, like ``cpu`` or ``tpm``.
    #   We dive into this mapping and convert each key into a distinct
    #   constraint - ``cpu.cores``, ``tpm.version``, and so on.
    # * a list:  a double-level requirement multiple peers, like ``disk``
    #   and ``network``. We dive into individual mappings, and convert
    #   each into a bunch of distinct constraints with proper peer index
    #   marking their position in the parent constraint - ``disk[1].size``,
    #   ``network[0].type``.
    # * otherwise, a single-level requirement is expected, like ``memory``
    #   or ``hostname``.

    def _parse(requirement: str, spec: Spec, peer_index: Optional[int] = None) -> None:
        for parser in _REQUIREMENT_PARSERS:
            if parser.requirement != requirement:
                continue

            group.constraints.append(_flatten(parser.parse(spec, peer_index=peer_index)))

            return

        raise Exception(f"Unhandled requirement '{requirement}'.")

    for l1_name in sorted(spec.keys()):
        l1_value = spec[l1_name]

        if isinstance(l1_value, dict):
            l1_value = cast(dict[str, Any], l1_value)

            for l2_name in sorted(l1_value.keys()):
                _parse(f'{l1_name}.{l2_name}', l1_value)

        elif isinstance(l1_value, list):
            l1_value = cast(list[dict[str, Any]], l1_value)

            for peer_index, l2_value in enumerate(l1_value):
                for l2_name in sorted(l2_value.keys()):
                    _parse(f'{l1_name}.{l2_name}', l2_value, peer_index=peer_index)

        else:
            _parse(l1_name, spec)

    return group


@flatten
def _parse_and(spec: Spec) -> BaseConstraint:
    """
    Parse an ``and`` clause holding one or more blocks or requirements.
    """

    group = And()

    group.constraints += [_parse_block(member) for member in spec]

    return group


@flatten
def _parse_or(spec: Spec) -> BaseConstraint:
    """
    Parse an ``or`` clause holding one or more blocks or requirements.
    """

    group = Or()

    group.constraints += [_parse_block(member) for member in spec]

    return group


@flatten
def _parse_block(spec: Spec) -> BaseConstraint:
    """
    Parse a generic block of hardware requirements.

    A block may contain either ``and`` or ``or`` clause, or a block
    of hardware requirements.
    """

    if 'and' in spec:
        return _parse_and(spec['and'])

    if 'or' in spec:
        return _parse_or(spec['or'])

    return _parse_requirements(spec)


def parse_hw_requirements(spec: Spec) -> BaseConstraint:
    """
    Convert raw specification of hardware requirements into constraints.
    """

    return _parse_block(spec)


@container
class Hardware(SpecBasedContainer[Spec, Spec]):
    constraint: Optional[BaseConstraint]
    spec: Spec

    @classmethod
    def from_spec(cls: type['Hardware'], spec: Spec) -> 'Hardware':
        if not spec:
            return Hardware(constraint=None, spec=spec)

        return Hardware(constraint=parse_hw_requirements(spec), spec=spec)

    def to_spec(self) -> Spec:
        return self.spec

    def to_minimal_spec(self) -> Spec:
        return self.spec

    def and_(self, constraint: BaseConstraint) -> None:
        if self.constraint:
            group = And()

            group.constraints = [self.constraint, constraint]

            self.constraint = group

        else:
            self.constraint = constraint

        self.spec = self.constraint.to_spec()

    def report_support(
        self,
        *,
        names: Optional[list[str]] = None,
        check: Optional[Callable[['Constraint'], bool]] = None,
        logger: tmt.log.Logger,
    ) -> None:
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

                if name in names or f'{name}.{child_name}' in names or check(constraint):
                    continue

                logger.warning(f"Hardware requirement '{constraint}' is not supported.")

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
