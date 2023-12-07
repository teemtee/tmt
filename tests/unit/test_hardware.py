import textwrap
from typing import Any

import pytest

import tmt.hardware
import tmt.utils
from tmt.hardware import Hardware


def parse_hw(text: str) -> Hardware:
    return Hardware.from_spec(tmt.utils.yaml_to_dict(textwrap.dedent(text)))


_constraint_value_pattern_inputs = [
    ('10', (None, '10')),
    ('10 GiB', (None, '10 GiB')),
    ('10GiB', (None, '10GiB')),
    ] + [
    (f'{operator.value} 10', (operator.value, '10'))
    for operator in tmt.hardware.INPUTABLE_OPERATORS
    ] + [
    (f'{operator.value} 10 GiB', (operator.value, '10 GiB'))
    for operator in tmt.hardware.INPUTABLE_OPERATORS
    ] + [
    (f'{operator.value}10GiB', (operator.value, '10GiB'))
    for operator in tmt.hardware.INPUTABLE_OPERATORS
    ]


@pytest.mark.parametrize(
    ('value', 'expected'),
    _constraint_value_pattern_inputs,
    ids=[
        f'{input} => ({expected[0]}, {expected[1]})'
        for input, expected in _constraint_value_pattern_inputs
        ]
    )
def test_constraint_value_pattern(value: str, expected: tuple[Any, Any]) -> None:
    match = tmt.hardware.CONSTRAINT_VALUE_PATTERN.match(value)

    assert match is not None
    assert match.groups() == expected


_constraint_name_pattern_input = [
    ('memory', ('memory', None, None)),
    ('cpu.processors', ('cpu', None, 'processors')),
    ('disk[1].size', ('disk', '1', 'size'))
    ]


@pytest.mark.parametrize(
    ('value', 'expected'),
    _constraint_name_pattern_input,
    ids=[
        f'{input} => ({expected[0]}, {expected[1]}, {expected[2]})'
        for input, expected in _constraint_name_pattern_input
        ]
    )
def test_constraint_name_pattern(value: str, expected: tuple[Any, Any]) -> None:
    match = tmt.hardware.CONSTRAINT_NAME_PATTERN.match(value)

    assert match is not None
    assert match.groups() == expected


_constraint_components_pattern_input = [
    ('memory 10 GiB', ('memory', None, None, None, '10 GiB')),
    ('cpu.processors != 4 ', ('cpu', None, 'processors', '!=', '4')),
    ('disk[1].size <= 1 TiB', ('disk', '1', 'size', '<=', '1 TiB'))
    ]


@pytest.mark.parametrize(
    ('value', 'expected'),
    _constraint_components_pattern_input,
    ids=[
        f'{input} => ({expected[0]}, {expected[1]}, {expected[2]}, {expected[3]}, {expected[4]})'
        for input, expected in _constraint_components_pattern_input
        ]
    )
def test_constraint_components_pattern(value: str, expected: tuple[Any, Any]) -> None:
    match = tmt.hardware.CONSTRAINT_COMPONENTS_PATTERN.match(value)

    assert match is not None
    assert match.groups() == expected


def test_parse_maximal_constraint() -> None:
    hw_spec = """
        boot:
            method: bios
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
            flag:
              - avx
              - "= avx2"
              - "!= smep"
        disk:
            - size: 40 GiB
            - size: 120 GiB
        gpu:
            device-name: G86 [Quadro NVS 290]
        hostname: "~ .*.foo.redhat.com"
        memory: 8 GiB
        network:
            - type: eth
            - type: eth
        tpm:
            version: "2.0"
        virtualization:
            is-supported: true
            is-virtualized: false
            hypervisor: "~ xen"
    """

    hw = parse_hw(hw_spec)

    assert hw.constraint is not None

    print(tmt.utils.dict_to_yaml(hw.constraint.to_spec()))

    assert hw.to_spec() == tmt.utils.yaml_to_dict(hw_spec)
