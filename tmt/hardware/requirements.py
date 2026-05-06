import functools
from collections.abc import Iterator
from typing import Any, Callable, Optional

import tmt.log

from ..container import SpecBasedContainer, container
from .constraints import (
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
    fn: Callable[[Spec, int], BaseConstraint],
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
    constraint_keys: tuple[str, ...],
) -> list[BaseConstraint]:
    """
    Parse number-like constraints defined by a given set of keys, to int
    """

    return [
        IntegerConstraint.from_specification(
            f'{prefix}.{constraint_name.replace("-", "_")}',
            str(spec[constraint_name]),
            allowed_operators=[
                Operator.EQ,
                Operator.NEQ,
                Operator.LT,
                Operator.LTE,
                Operator.GT,
                Operator.GTE,
            ],
        )
        for constraint_name in constraint_keys
        if constraint_name in spec
    ]


def _parse_number_constraints(
    spec: Spec,
    prefix: str,
    constraint_keys: tuple[str, ...],
    default_unit: Optional[Any] = None,
) -> list[BaseConstraint]:
    """
    Parse number-like constraints defined by a given set of keys, to float
    """

    return [
        NumberConstraint.from_specification(
            f'{prefix}.{constraint_name.replace("-", "_")}',
            str(spec[constraint_name]),
            allowed_operators=[
                Operator.EQ,
                Operator.NEQ,
                Operator.LT,
                Operator.LTE,
                Operator.GT,
                Operator.GTE,
            ],
            default_unit=default_unit,
        )
        for constraint_name in constraint_keys
        if constraint_name in spec
    ]


def _parse_size_constraints(
    spec: Spec,
    prefix: str,
    constraint_keys: tuple[str, ...],
) -> list[BaseConstraint]:
    """
    Parse size-like constraints defined by a given set of keys
    """

    return [
        SizeConstraint.from_specification(
            f'{prefix}.{constraint_name.replace("-", "_")}',
            str(spec[constraint_name]),
            allowed_operators=[
                Operator.EQ,
                Operator.NEQ,
                Operator.LT,
                Operator.LTE,
                Operator.GT,
                Operator.GTE,
            ],
        )
        for constraint_name in constraint_keys
        if constraint_name in spec
    ]


def _parse_text_constraints(
    spec: Spec,
    prefix: str,
    constraint_keys: tuple[str, ...],
    allowed_operators: Optional[tuple[Operator, ...]] = None,
) -> list[BaseConstraint]:
    """
    Parse text-like constraints defined by a given set of keys
    """

    allowed_operators = allowed_operators or (
        Operator.EQ,
        Operator.NEQ,
        Operator.MATCH,
        Operator.NOTMATCH,
    )

    return [
        TextConstraint.from_specification(
            f'{prefix}.{constraint_name.replace("-", "_")}',
            str(spec[constraint_name]),
            allowed_operators=list(allowed_operators),
        )
        for constraint_name in constraint_keys
        if constraint_name in spec
    ]


def _parse_flag_constraints(
    spec: Spec,
    prefix: str,
    constraint_keys: tuple[str, ...],
) -> list[BaseConstraint]:
    """
    Parse flag-like constraints defined by a given set of keys
    """

    return [
        FlagConstraint.from_specification(
            f'{prefix}.{constraint_name.replace("-", "_")}',
            spec[constraint_name],
            allowed_operators=[Operator.EQ, Operator.NEQ],
        )
        for constraint_name in constraint_keys
        if constraint_name in spec
    ]


def _parse_device_core(
    spec: Spec,
    device_prefix: str = 'device',
    include_driver: bool = True,
    include_device: bool = True,
) -> And:
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

    group.constraints += _parse_int_constraints(
        spec,
        device_prefix,
        number_constraints,
    )
    group.constraints += _parse_text_constraints(
        spec,
        device_prefix,
        text_constraints,
    )

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
            'boot.method', spec["method"], allowed_operators=[Operator.EQ, Operator.NEQ]
        )

        if constraint.operator == Operator.EQ:
            constraint.change_operator(Operator.CONTAINS)

        elif constraint.operator == Operator.NEQ:
            constraint.change_operator(Operator.NOTCONTAINS_EXCLUSIVE)

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

    group.constraints += _parse_flag_constraints(
        spec,
        'virtualization',
        ('is-virtualized', 'is-supported', 'confidential'),
    )
    group.constraints += _parse_text_constraints(
        spec,
        'virtualization',
        ('hypervisor',),
    )

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
        ),
    )

    group.constraints += _parse_number_constraints(
        spec,
        'cpu',
        ('frequency',),
        default_unit='MHz',
    )

    group.constraints += _parse_text_constraints(
        spec,
        'cpu',
        (
            'family-name',
            'model-name',
            'vendor-name',
        ),
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
                allowed_operators=[Operator.EQ, Operator.NEQ],
            )
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

    group.constraints += _parse_size_constraints(
        spec,
        f'disk[{disk_index}]',
        ('size', 'physical-sector-size', 'logical-sector-size'),
    )
    group.constraints += _parse_text_constraints(
        spec,
        f'disk[{disk_index}]',
        ('model-name', 'driver'),
    )

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
        _parse_disk(disk_spec, disk_index) for disk_index, disk_spec in enumerate(spec)
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
    group.constraints += _parse_text_constraints(
        spec,
        f'network[{network_index}]',
        ('type',),
    )

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
        spec, device_prefix='system', include_driver=False, include_device=False
    )

    group.constraints += _parse_int_constraints(
        spec,
        'system',
        ('model', 'numa-nodes'),
    )
    group.constraints += _parse_text_constraints(
        spec,
        'system',
        ('model-name', 'type'),
    )

    return group


TPM_VERSION_ALLOWED_OPERATORS: tuple[Operator, ...] = (
    Operator.EQ,
    Operator.NEQ,
    Operator.LT,
    Operator.LTE,
    Operator.GT,
    Operator.GTE,
)


@ungroupify
def _parse_tpm(spec: Spec) -> BaseConstraint:
    """
    Parse constraints related to the ``tpm`` HW requirement.

    :param spec: raw constraint block specification.
    :returns: block representation as :py:class:`BaseConstraint` or one of its subclasses.
    """

    group = And()

    group.constraints += _parse_text_constraints(
        spec,
        'tpm',
        ('version',),
        allowed_operators=TPM_VERSION_ALLOWED_OPERATORS,
    )

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
            Operator.EQ,
            Operator.NEQ,
            Operator.LT,
            Operator.LTE,
            Operator.GT,
            Operator.GTE,
        ],
        default_unit='MiB',
    )


def _parse_hostname(spec: Spec) -> BaseConstraint:
    """
    Parse constraints related to the ``hostname`` HW requirement.

    :param spec: raw constraint block specification.
    :returns: block representation as :py:class:`BaseConstraint` or one of its subclasses.
    """

    return TextConstraint.from_specification(
        'hostname',
        spec['hostname'],
        allowed_operators=[Operator.EQ, Operator.NEQ, Operator.MATCH, Operator.NOTMATCH],
    )


@ungroupify
def _parse_zcrypt(spec: Spec) -> BaseConstraint:
    """
    Parse constraints related to the ``zcrypt`` HW requirement.

    :param spec: raw constraint block specification.
    :returns: block representation as :py:class:`BaseConstraint` or one of its subclasses.
    """

    group = And()

    group.constraints += _parse_text_constraints(
        spec,
        'zcrypt',
        ('adapter', 'mode'),
    )

    return group


@ungroupify
def _parse_iommu(spec: Spec) -> BaseConstraint:
    """
    Parse constraints related to the ``iommu`` HW requirement.

    :param spec: raw constraint block specification.
    :returns: block representation as :py:class:`BaseConstraint` or one of its subclasses.
    """

    group = And()

    group.constraints += _parse_flag_constraints(
        spec,
        'iommu',
        ('is-supported',),
    )
    group.constraints += _parse_text_constraints(
        spec,
        'iommu',
        ('model-name',),
    )

    return group


@ungroupify
def _parse_location(spec: Spec) -> BaseConstraint:
    """
    Parse constraints related to the ``location`` HW requirement.

    :param spec: raw constraint block specification.
    :returns: block representation as :py:class:`BaseConstraint` or one of its subclasses.
    """

    group = And()

    group.constraints += _parse_text_constraints(
        spec,
        'location',
        ('lab-controller',),
    )

    return group


@ungroupify
def _parse_beaker(spec: Spec) -> BaseConstraint:
    """
    Parse constraints related to the ``beaker`` HW requirement.

    :param spec: raw constraint block specification.
    :returns: block representation as :py:class:`BaseConstraint` or one of its subclasses.
    """

    group = And()

    group.constraints += _parse_text_constraints(
        spec,
        'beaker',
        ('pool',),
        allowed_operators=(Operator.EQ, Operator.NEQ),
    )

    group.constraints += _parse_flag_constraints(
        spec,
        'beaker',
        ('panic-watchdog',),
    )

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
        group.constraints += [TextConstraint.from_specification('arch', spec['arch'])]

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

    group.constraints += [_parse_block(member) for member in spec]

    return group


@ungroupify
def _parse_or(spec: Spec) -> BaseConstraint:
    """
    Parse an ``or`` clause holding one or more subblocks or constraints.

    :param spec: raw constraint block specification.
    :returns: block representation as :py:class:`BaseConstraint` or one of its subclasses.
    """

    group = Or()

    group.constraints += [_parse_block(member) for member in spec]

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
