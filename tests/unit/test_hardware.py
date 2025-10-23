import logging
import textwrap
from typing import Any

import _pytest.logging
import fmf
import pytest

import tmt.hardware
import tmt.steps
import tmt.steps.provision
import tmt.utils
from tmt.hardware import Hardware
from tmt.log import Logger

from . import MATCH, assert_log


def parse_hw(text: str) -> Hardware:
    return Hardware.from_spec(tmt.utils.yaml_to_dict(textwrap.dedent(text)))


_constraint_value_pattern_inputs = (
    [
        ('10', (None, '10')),
        ('10 GiB', (None, '10 GiB')),
        ('10GiB', (None, '10GiB')),
    ]
    + [
        (f'{operator.value} 10', (operator.value, '10'))
        for operator in tmt.hardware.INPUTABLE_OPERATORS
    ]
    + [
        (f'{operator.value} 10 GiB', (operator.value, '10 GiB'))
        for operator in tmt.hardware.INPUTABLE_OPERATORS
    ]
    + [
        (f'{operator.value}10GiB', (operator.value, '10GiB'))
        for operator in tmt.hardware.INPUTABLE_OPERATORS
    ]
)


@pytest.mark.parametrize(
    ('value', 'expected'),
    _constraint_value_pattern_inputs,
    ids=[
        f'{input} => ({expected[0]}, {expected[1]})'
        for input, expected in _constraint_value_pattern_inputs
    ],
)
def test_constraint_value_pattern(value: str, expected: tuple[Any, Any]) -> None:
    match = tmt.hardware.CONSTRAINT_VALUE_PATTERN.match(value)

    assert match is not None
    assert match.groups() == expected


_constraint_name_pattern_input = [
    ('memory', ('memory', None, None)),
    ('cpu.processors', ('cpu', None, 'processors')),
    ('disk[1].size', ('disk', '1', 'size')),
]


@pytest.mark.parametrize(
    ('value', 'expected'),
    _constraint_name_pattern_input,
    ids=[
        f'{input} => ({expected[0]}, {expected[1]}, {expected[2]})'
        for input, expected in _constraint_name_pattern_input
    ],
)
def test_constraint_name_pattern(value: str, expected: tuple[Any, Any]) -> None:
    match = tmt.hardware.CONSTRAINT_NAME_PATTERN.match(value)

    assert match is not None
    assert match.groups() == expected


_size_constraint_pattern_input = [
    (
        {'name': 'num_with_default', 'raw_value': '10', 'default_unit': 'GiB'},
        'num_with_default: == 10 gibibyte',
    ),
    ({'name': 'num_without_default', 'raw_value': '1024'}, 'num_without_default: == 1024 byte'),
    (
        {'name': 'num_with_unit', 'raw_value': '10 GiB', 'default_unit': 'MiB'},
        'num_with_unit: == 10 GiB',
    ),
]


@pytest.mark.parametrize(
    ('value', 'expected'),
    _size_constraint_pattern_input,
)
def test_constraint_default_unit(value: dict, expected: tuple[Any, Any]) -> None:
    constraint_out = tmt.hardware.SizeConstraint.from_specification(**value)

    assert constraint_out is not None
    assert str(constraint_out) == expected


_constraint_components_pattern_input = [
    ('memory 10 GiB', ('memory', None, None, None, '10 GiB')),
    ('cpu.processors != 4 ', ('cpu', None, 'processors', '!=', '4')),
    ('disk[1].size <= 1 TiB', ('disk', '1', 'size', '<=', '1 TiB')),
]


@pytest.mark.parametrize(
    ('value', 'expected'),
    _constraint_components_pattern_input,
    ids=[
        f'{input} => ({expected[0]}, {expected[1]}, {expected[2]}, {expected[3]}, {expected[4]})'
        for input, expected in _constraint_components_pattern_input
    ],
)
def test_constraint_components_pattern(value: str, expected: tuple[Any, Any]) -> None:
    match = tmt.hardware.CONSTRAINT_COMPONENTS_PATTERN.match(value)

    assert match is not None
    assert match.groups() == expected


def test_normalize_hardware(root_logger) -> None:
    # All major classes of requirements:
    spec = (
        # Simple name.child_name=value
        'cpu.processors=1',
        # The same but with cpu.flags which have special handling
        'cpu.flag!=avc',
        # name[peer_index].child_name=value
        'disk[1].size=1',
    )

    tmt.steps.provision.normalize_hardware('', spec, root_logger)


@pytest.mark.parametrize(
    ('spec', 'expected_exc', 'expected_message'),
    [
        (
            ('disk[1].size=15GB', 'disk.size=20GB'),
            tmt.utils.SpecificationError,
            r"^Hardware requirement 'disk\.size=20GB' lacks entry index \(disk\[N\]\)\.$",
        ),
        (
            ('network[1].type=eth', 'network.type=eth'),
            tmt.utils.SpecificationError,
            r"^Hardware requirement 'network\.type=eth' lacks entry index \(network\[N\]\)\.$",
        ),
        (
            ('disk=20GB',),
            tmt.utils.SpecificationError,
            r"^Hardware requirement 'disk=20GB' lacks child property \(disk\[N\].M\)\.$",
        ),
        (
            ('network=eth',),
            tmt.utils.SpecificationError,
            r"^Hardware requirement 'network=eth' lacks child property \(network\[N\].M\)\.$",
        ),
    ],
    ids=[
        'disk.size lacks index',
        'network.size lacks index',
        'disk lacks child property',
        'network lacks child property',
    ],
)
def test_normalize_invalid_hardware(
    spec: tmt.hardware.Spec, expected_exc: type[Exception], expected_message: str, root_logger
) -> None:
    with pytest.raises(expected_exc, match=expected_message):
        tmt.steps.provision.normalize_hardware('', spec, root_logger)


FULL_HARDWARE_REQUIREMENTS = """
    beaker:
        pool: "!= foo.*"
        panic-watchdog: True
    boot:
        method: "!= bios"
    compatible:
        distro:
            - rhel-7
            - rhel-8
    cpu:
        sockets: "<= 1"
        cores: 2
        threads: ">= 8"
        cores-per-socket: "= 2"
        threads-per-core: "== 4"
        processors: "> 8"
        model: 62
        model-name: "!~ Haswell"
        family: "< 6"
        family-name: Skylake
        vendor-name: "~ Intel.*"
        vendor: == 0x8086
        stepping: "!= 10"
        flag:
            - avx
            - "= avx2"
            - "!= smep"
        hyper-threading: true
        frequency: ">= 2300.0"
    device:
      device-name: '~ .*Thunderbolt.*'
      device: 79
      vendor-name: '!= Intel'
      vendor: "> 97"
      driver: mc
    disk:
        - size: 40 GiB
          model-name: "~ WD 100G.*"
          physical-sector-size: "4096 byte"
        - size: 120 GiB
          driver: virtblk
          logical-sector-size: "512 byte"
    gpu:
        device-name: G86 [Quadro NVS 290]
        device: "97"
        vendor-name: 'Nvidia'
        vendor: 0x10de
        driver: "~radeon"
    hostname: "~ .*.foo.redhat.com"
    location:
        lab-controller: "!= lab-1.bar.redhat.com"
    memory: 8 GiB
    network:
        - type: eth
          vendor: "!= 0x79"
          vendor-name: ~ ^Broadcom
          device-name: ~ ^NetXtreme II BCM
          device: 1657
          driver: iwlwifi
        - type: eth
    system:
        vendor: 0x413C
        vendor-name: "~ Dell.*"
        model: 79
        model-name: "~ PowerEdge R750"
        numa-nodes: "< 4"
        type: "!= Machine"
    tpm:
        version: "2.0"
    virtualization:
        is-supported: true
        is-virtualized: false
        hypervisor: "~ xen"
    zcrypt:
        adapter: "CEX8C"
        mode: "CCA"
"""

OR_HARDWARE_REQUIREMENTS = """
    or:
      - hostname: == dummy1.redhat.com
      - or:
        - hostname: == dummy2.redhat.com
        - or:
          - hostname: == dummy3.redhat.com
          - hostname: == dummy4.redhat.com
"""


@pytest.mark.parametrize(
    'requirements',
    [
        FULL_HARDWARE_REQUIREMENTS,
        OR_HARDWARE_REQUIREMENTS,
    ],
    ids=('Full requirements', 'OR-ed requirements'),
)
def test_validate_requirements(requirements: str, root_logger: Logger) -> None:
    node = fmf.Tree({'hardware': tmt.utils.yaml_to_dict(requirements)})

    errors = tmt.utils.validate_fmf_node(node, 'hardware.yaml', root_logger)

    if errors:
        for error, message in errors:
            print(f"""* {message}

Detailed validation error:

{textwrap.indent(str(error), '  ')}
""")

        pytest.fail("Requirement example fails schema validation")


def test_parse_maximal_constraint() -> None:
    hw_spec_out = """
        and:
          - and:
              - beaker.pool: '!= foo.*'
              - beaker.panic-watchdog: == True
          - boot.method: not contains exclusive bios
          - and:
              - compatible.distro: contains rhel-7
              - compatible.distro: contains rhel-8
          - and:
              - cpu.processors: '> 8'
              - cpu.sockets: <= 1
              - cpu.cores: == 2
              - cpu.threads: '>= 8'
              - cpu.cores-per-socket: == 2
              - cpu.threads-per-core: == 4
              - cpu.model: == 62
              - cpu.family: < 6
              - cpu.vendor: == 32902
              - cpu.stepping: '!= 10'
              - cpu.frequency: '>= 2300.0 megahertz'
              - cpu.family-name: == Skylake
              - cpu.model-name: '!~ Haswell'
              - cpu.vendor-name: ~ Intel.*
              - and:
                  - cpu.flag: contains avx
                  - cpu.flag: contains avx2
                  - cpu.flag: not contains smep
              - cpu.hyper-threading: == True
          - and:
              - device.vendor: '> 97'
              - device.device: == 79
              - device.vendor-name: '!= Intel'
              - device.device-name: ~ .*Thunderbolt.*
              - device.driver: == mc
          - and:
              - gpu.vendor: == 4318
              - gpu.device: == 97
              - gpu.vendor-name: == Nvidia
              - gpu.device-name: == G86 [Quadro NVS 290]
              - gpu.driver: ~ radeon
          - memory: == 8 GiB
          - and:
              - and:
                  - disk[0].size: == 40 GiB
                  - disk[0].physical-sector-size: == 4096 B
                  - disk[0].model-name: ~ WD 100G.*
              - and:
                  - disk[1].size: == 120 GiB
                  - disk[1].logical-sector-size: == 512 B
                  - disk[1].driver: == virtblk
          - and:
              - and:
                  - network[0].vendor: '!= 121'
                  - network[0].device: == 1657
                  - network[0].vendor-name: ~ ^Broadcom
                  - network[0].device-name: ~ ^NetXtreme II BCM
                  - network[0].driver: == iwlwifi
                  - network[0].type: == eth
              - network[1].type: == eth
          - hostname: ~ .*.foo.redhat.com
          - location.lab-controller: '!= lab-1.bar.redhat.com'
          - and:
              - system.vendor: == 16700
              - system.vendor-name: ~ Dell.*
              - system.model: == 79
              - system.numa-nodes: < 4
              - system.model-name: ~ PowerEdge R750
              - system.type: '!= Machine'
          - tpm.version: == 2.0
          - and:
              - virtualization.is-virtualized: == False
              - virtualization.is-supported: == True
              - virtualization.hypervisor: ~ xen
          - and:
              - zcrypt.adapter: == CEX8C
              - zcrypt.mode: == CCA
    """

    hw = parse_hw(FULL_HARDWARE_REQUIREMENTS)

    assert hw.constraint is not None

    print(hw.to_spec())
    print(tmt.utils.dict_to_yaml(hw.constraint.to_spec()))
    print(textwrap.dedent(hw_spec_out))

    assert tmt.utils.dict_to_yaml(hw.constraint.to_spec()) == textwrap.dedent(hw_spec_out).lstrip()


def test_parse_or_constraint() -> None:
    hw_spec_out = """
     or:
       - hostname: == dummy1.redhat.com
       - or:
           - hostname: == dummy2.redhat.com
           - or:
               - hostname: == dummy3.redhat.com
               - hostname: == dummy4.redhat.com
    """

    hw = parse_hw(OR_HARDWARE_REQUIREMENTS)
    assert tmt.utils.dict_to_yaml(hw.constraint.to_spec()) == textwrap.dedent(hw_spec_out).lstrip()


def test_report_support(
    root_logger: Logger,
    caplog: _pytest.logging.LogCaptureFixture,
) -> None:
    # Spec to test against
    hw = parse_hw("""
     or:
       - memory: '>= 4 GB'
       - memory: '!= 4 GB'
    """)

    # For testing purposes we are saying ">=" is the only valid operator.
    def _test_check(constraint: tmt.hardware.Constraint) -> bool:
        if constraint.operator == tmt.hardware.Operator.GTE:
            return True
        return False

    # "!=" should trigger a warning in def report_support
    hw.report_support(names=[], check=_test_check, logger=root_logger)
    assert_log(
        caplog,
        message=MATCH(r"warn: Hardware requirement 'memory: != 4 GB' is not supported."),
        levelno=logging.WARNING,
    )


@pytest.mark.parametrize(
    ('operator', 'left', 'right', 'expected'),
    [
        (tmt.hardware.not_contains, ['foo'], 'foo', False),
        (tmt.hardware.not_contains, ['foo', 'bar'], 'foo', False),
        (tmt.hardware.not_contains, ['foo'], 'bar', True),
        (tmt.hardware.not_contains_exclusive, ['foo'], 'foo', False),
        (tmt.hardware.not_contains_exclusive, ['foo', 'bar'], 'foo', True),
        (tmt.hardware.not_contains_exclusive, ['foo'], 'bar', True),
    ],
)
def test_operators(
    operator: tmt.hardware.OperatorHandlerType, left: Any, right: Any, expected: bool
) -> None:
    assert operator(left, right) is expected
