import textwrap

import pytest

import tmt.utils
from tmt.hardware import (
    Hardware,
    Operator,
    _parse_cpu,
    _parse_disk,
    _parse_hostname,
    _parse_memory,
    _parse_virtualization,
    )
from tmt.log import Logger
from tmt.steps.provision.mrack import (
    _CONSTRAINT_TRANSFORMERS,
    constraint_to_beaker_filter,
    operator_to_beaker_op,
    )


@pytest.mark.parametrize(
    ('operator', 'value', 'expected'),
    [
        (Operator.EQ, 'foo', ('==', 'foo', False)),
        (Operator.NEQ, 'foo', ('!=', 'foo', False)),
        (Operator.GT, 'foo', ('>', 'foo', False)),
        (Operator.GTE, 'foo', ('>=', 'foo', False)),
        (Operator.LT, 'foo', ('<', 'foo', False)),
        (Operator.LTE, 'foo', ('<=', 'foo', False)),
        (Operator.MATCH, 'f.+o.*o', ('like', 'f%o%o', False)),
        (Operator.NOTMATCH, 'f.+o.*o', ('like', 'f%o%o', True))
        ]
    )
def test_operator_to_beaker_op(
        operator: Operator,
        value: str,
        expected: tuple[str, str, bool]) -> None:
    assert operator_to_beaker_op(operator, value) == expected


def test_maximal_constraint(root_logger: Logger) -> None:
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
              model-name: "PERC H310"
            - size: 120 GiB
              driver: mpt3sas
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

    hw = Hardware.from_spec(tmt.utils.yaml_to_dict(textwrap.dedent(hw_spec)))
    assert hw.constraint is not None

    result = constraint_to_beaker_filter(hw.constraint, root_logger)

    assert result.to_mrack() == {
        'and': [
            {'or': []},
            {
                'and': [
                    {'or': []},
                    {'or': []}
                    ]
                },
            {
                'and': [
                    {
                        'cpu': {
                            'cpu_count': {
                                '_op': '>',
                                '_value': '8'
                                }
                            }
                        },
                    {'or': []},
                    {'or': []},
                    {'or': []},
                    {'or': []},
                    {'or': []},
                    {
                        'cpu': {
                            'model': {
                                '_op': '==',
                                '_value': '62'
                                }
                            }
                        },
                    {'or': []},
                    {'or': []},
                    {'or': []},
                    {
                        'and': [
                            {
                                'cpu': {
                                    'flag': {
                                        '_op': '==',
                                        '_value': 'avx'
                                        }
                                    }
                                },
                            {
                                'cpu': {
                                    'flag': {
                                        '_op': '==',
                                        '_value': 'avx2'
                                        }
                                    }
                                },
                            {
                                'cpu': {
                                    'flag': {
                                        '_op': '!=',
                                        '_value': 'smep'
                                        }
                                    }
                                }
                            ]
                        }
                    ]
                },
            {
                'system': {
                    'memory': {
                        '_op': '==',
                        '_value': '8192'
                        }
                    }
                },
            {
                'and': [
                    {
                        'and': [
                            {
                                'disk': {
                                    'size': {
                                        '_op': '==',
                                        '_value': '42949672960'
                                        }
                                    }
                                },
                            {
                                'disk': {
                                    'model': {
                                        '_op': '==',
                                        '_value': 'PERC H310'
                                        }
                                    }
                                }
                            ]
                        },
                    {
                        'and': [
                            {
                                'disk': {
                                    'size': {
                                        '_op': '==',
                                        '_value': '128849018880'
                                        }
                                    }
                                },
                            {
                                'key_value': {
                                    '_key': 'BOOTDISK',
                                    '_op': '==',
                                    '_value': 'mpt3sas'
                                    }
                                }
                            ]
                        },
                    ]
                },
            {
                'and': [
                    {'or': []},
                    {'or': []}
                    ]
                },
            {
                'hostname': {
                    '_op': 'like',
                    '_value': '%.foo.redhat.com'
                    }
                },
            {'or': []},
            {
                'and': [
                    {
                        'system': {
                            'hypervisor': {
                                '_op': '==',
                                '_value': ''
                                }
                            }
                        },
                    {'or': []},
                    {'or': []}
                    ]
                }
            ]
        }


def test_cpu_model(root_logger: Logger) -> None:
    result = _CONSTRAINT_TRANSFORMERS['cpu.model'](_parse_cpu({'model': '79'}), root_logger)

    assert result.to_mrack() == {
        'cpu': {
            'model': {
                '_op': '==',
                '_value': '79'
                }
            }
        }


def test_cpu_processors(root_logger: Logger) -> None:
    result = _CONSTRAINT_TRANSFORMERS['cpu.processors'](
        _parse_cpu({'processors': '79'}), root_logger)

    assert result.to_mrack() == {
        'cpu': {
            'cpu_count': {
                '_op': '==',
                '_value': '79'
                }
            }
        }


def test_disk_driver(root_logger: Logger) -> None:
    result = _CONSTRAINT_TRANSFORMERS['disk.driver'](
        _parse_disk({'driver': 'mpt3sas'}, 1), root_logger)

    assert result.to_mrack() == {
        'key_value': {
            '_key': 'BOOTDISK',
            '_op': '==',
            '_value': 'mpt3sas'
            }
        }

    result = _CONSTRAINT_TRANSFORMERS['disk.driver'](
        _parse_disk({'driver': '!= mpt3sas'}, 1), root_logger)

    assert result.to_mrack() == {
        'key_value': {
            '_key': 'BOOTDISK',
            '_op': '!=',
            '_value': 'mpt3sas'
            }
        }

    result = _CONSTRAINT_TRANSFORMERS['disk.driver'](
        _parse_disk({'driver': '~ mpt3.*'}, 1), root_logger)

    assert result.to_mrack() == {
        'key_value': {
            '_key': 'BOOTDISK',
            '_op': 'like',
            '_value': 'mpt3%'
            }
        }

    result = _CONSTRAINT_TRANSFORMERS['disk.driver'](
        _parse_disk({'driver': '!~ mpt3.*'}, 1), root_logger)

    assert result.to_mrack() == {
        'not': {
            'key_value': {
                '_key': 'BOOTDISK',
                '_op': 'like',
                '_value': 'mpt3%'
                }
            }
        }


def test_disk_size(root_logger: Logger) -> None:
    result = _CONSTRAINT_TRANSFORMERS['disk.size'](
        _parse_disk({'size': '>= 40 GiB'}, 1), root_logger)

    assert result.to_mrack() == {
        'disk': {
            'size': {
                '_op': '>=',
                '_value': '42949672960'
                }
            }
        }


def test_disk_model_name(root_logger: Logger) -> None:
    result = _CONSTRAINT_TRANSFORMERS['disk.model_name'](
        _parse_disk({'model-name': 'PERC H310'}, 1), root_logger)

    assert result.to_mrack() == {
        'disk': {
            'model': {
                '_op': '==',
                '_value': 'PERC H310'
                }
            }
        }

    result = _CONSTRAINT_TRANSFORMERS['disk.model_name'](
        _parse_disk({'model-name': '!= PERC H310'}, 1), root_logger)

    assert result.to_mrack() == {
        'disk': {
            'model': {
                '_op': '!=',
                '_value': 'PERC H310'
                }
            }
        }

    result = _CONSTRAINT_TRANSFORMERS['disk.model_name'](
        _parse_disk({'model-name': '~ PERC.*'}, 1), root_logger)

    assert result.to_mrack() == {
        'disk': {
            'model': {
                '_op': 'like',
                '_value': 'PERC%'
                }
            }
        }

    result = _CONSTRAINT_TRANSFORMERS['disk.model_name'](
        _parse_disk({'model-name': '!~ PERC.*'}, 1), root_logger)

    assert result.to_mrack() == {
        'not': {
            'disk': {
                'model': {
                    '_op': 'like',
                    '_value': 'PERC%'
                    }
                }
            }
        }


def test_memory(root_logger: Logger) -> None:
    result = _CONSTRAINT_TRANSFORMERS['memory'](_parse_memory({'memory': '>= 4 GiB'}), root_logger)

    assert result.to_mrack() == {
        'system': {
            'memory': {
                '_op': '>=',
                '_value': '4096'
                }
            }
        }


def test_hostname(root_logger: Logger) -> None:
    result = _CONSTRAINT_TRANSFORMERS['hostname'](
        _parse_hostname({'hostname': 'foo.dot.com'}), root_logger)

    assert result.to_mrack() == {
        'hostname': {
            '_op': '==',
            '_value': 'foo.dot.com'
            }
        }

    result = _CONSTRAINT_TRANSFORMERS['hostname'](
        _parse_hostname({'hostname': '~ foo.*.dot.+.com'}), root_logger)

    assert result.to_mrack() == {
        'hostname': {
            '_op': 'like',
            '_value': 'foo%.dot%.com'
            }
        }

    result = _CONSTRAINT_TRANSFORMERS['hostname'](
        _parse_hostname({'hostname': '!~ foo.*.dot.+.com'}), root_logger)

    assert result.to_mrack() == {
        'not': {
            'hostname': {
                '_op': 'like',
                '_value': 'foo%.dot%.com'
                }
            }
        }


def test_virtualization_is_virtualized(root_logger: Logger) -> None:
    result = _CONSTRAINT_TRANSFORMERS['virtualization.is_virtualized'](
        _parse_virtualization({'is-virtualized': True}), root_logger)

    assert result.to_mrack() == {
        'system': {
            'hypervisor': {
                '_op': '!=',
                '_value': ''
                }
            }
        }

    result = _CONSTRAINT_TRANSFORMERS['virtualization.is_virtualized'](
        _parse_virtualization({'is-virtualized': False}), root_logger)

    assert result.to_mrack() == {
        'system': {
            'hypervisor': {
                '_op': '==',
                '_value': ''
                }
            }
        }
