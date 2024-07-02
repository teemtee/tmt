import textwrap

import pytest

import tmt.utils
from tests.unit.test_hardware import FULL_HARDWARE_REQUIREMENTS
from tmt.hardware import (
    Hardware,
    Operator,
    _parse_cpu,
    _parse_disk,
    _parse_hostname,
    _parse_location,
    _parse_memory,
    _parse_system,
    _parse_tpm,
    _parse_virtualization,
    _parse_zcrypt,
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
    hw = Hardware.from_spec(tmt.utils.yaml_to_dict(textwrap.dedent(FULL_HARDWARE_REQUIREMENTS)))
    assert hw.constraint is not None

    result = constraint_to_beaker_filter(hw.constraint, root_logger)

    assert result.to_mrack() == {
        'and': [
            {'pool': {
                '_op': '!=',
                '_value': 'foo.*',
                },
             },
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
                            'processors': {
                                '_op': '>',
                                '_value': '8'
                                },
                            },
                        },
                    {
                        'or': [],
                        },
                    {
                        'cpu': {
                            'cores': {
                                '_op': '==',
                                '_value': '2'
                                },
                            },
                        },
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
                    {'or': []},
                    {
                        'not':
                            {
                                'cpu': {
                                    'model_name': {
                                        '_op': 'like',
                                        '_value': 'Haswell'
                                        }
                                    }
                                },
                        },
                    {
                        'cpu': {
                            'vendor': {
                                '_op': 'like',
                                '_value': 'Intel%',
                                },
                            },
                        },
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
                                },
                            ]
                        },
                    {
                        'cpu': {
                            'hyper': {
                                '_op': '==',
                                '_value': 'True'
                                }
                            }
                        },
                    ]
                },
            {
                'and': [
                    {'or': []},
                    {'or': []},
                    {'or': []},
                    {'or': []},
                    {'or': []}
                    ]
                },
            {
                'and': [
                    {'or': []},
                    {'or': []},
                    {'or': []},
                    {'or': []},
                    {'or': []}
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
                                    'phys_sector_size': {
                                        '_op': '==',
                                        '_value': '4096 B'
                                        }
                                    }
                                },
                            {
                                'disk': {
                                    'model': {
                                        '_op': 'like',
                                        '_value': 'WD 100G%'
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
                                'disk': {
                                    'sector_size': {
                                        '_op': '==',
                                        '_value': '512 B'
                                        }
                                    }
                                },
                            {
                                'key_value': {
                                    '_key': 'BOOTDISK',
                                    '_op': '==',
                                    '_value': 'virtblk'
                                    }
                                }
                            ]
                        },
                    ]
                },
            {
                'and': [
                    {
                        'and': [
                            {'or': []},
                            {'or': []},
                            {'or': []},
                            {'or': []},
                            {'or': []},
                            {'or': []}
                            ]
                        },
                    {'or': []}
                    ],
                },
            {
                'hostname': {
                    '_op': 'like',
                    '_value': '%.foo.redhat.com'
                    }
                },
            {
                'labcontroller': {
                    '_op': '!=',
                    '_value': 'lab-1.bar.redhat.com'
                    }
                },
            {
                'and': [
                    {'or': []},
                    {'or': []},
                    {'or': []},
                    {
                        'system': {
                            'numanodes': {
                                '_op': '<',
                                '_value': '4',
                                },
                            },
                        },
                    {'or': []},
                    ]
                },
            {
                'key_value': {
                    '_key': 'TPM',
                    '_op': '==',
                    '_value': '2.0',
                    },
                },

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
                    {
                        'or': []
                        },
                    {
                        'system': {
                            'hypervisor': {
                                '_op': 'like',
                                '_value': 'xen'
                                }
                            }
                        }
                    ]
                },
            {
                'and': [
                    {
                        'system': {
                            'key_value': {
                                '_key': 'ZCRYPT_MODEL',
                                '_op': '==',
                                '_value': 'CEX8C'
                                }
                            }
                        },
                    {
                        'system': {
                            'key_value': {
                                '_key': 'ZCRYPT_MODE',
                                '_op': '==',
                                '_value': 'CCA'
                                }
                            }
                        }
                    ]
                },

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
            'processors': {
                '_op': '==',
                '_value': '79'
                }
            }
        }


def test_cpu_cores(root_logger: Logger) -> None:
    result = _CONSTRAINT_TRANSFORMERS['cpu.cores'](
        _parse_cpu({'cores': '2'}), root_logger)

    assert result.to_mrack() == {
        'cpu': {
            'cores': {
                '_op': '==',
                '_value': '2'
                }
            }
        }


def test_cpu_vendor_name(root_logger: Logger) -> None:
    result = _CONSTRAINT_TRANSFORMERS['cpu.vendor_name'](
        _parse_cpu({'vendor-name': 'GenuineIntel'}), root_logger)

    assert result.to_mrack() == {
        'cpu': {
            'vendor': {
                '_op': '==',
                '_value': 'GenuineIntel'
                }
            }
        }

    result = _CONSTRAINT_TRANSFORMERS['cpu.vendor_name'](
        _parse_cpu({'vendor-name': '!= GenuineIntel'}), root_logger)

    assert result.to_mrack() == {
        'cpu': {
            'vendor': {
                '_op': '!=',
                '_value': 'GenuineIntel'
                }
            }
        }

    result = _CONSTRAINT_TRANSFORMERS['cpu.vendor_name'](
        _parse_cpu({'vendor-name': '~ .*Intel'}), root_logger)

    assert result.to_mrack() == {
        'cpu': {
            'vendor': {
                '_op': 'like',
                '_value': '%Intel'
                }
            }
        }

    result = _CONSTRAINT_TRANSFORMERS['cpu.vendor_name'](
        _parse_cpu({'vendor-name': '!~ .*Intel'}), root_logger)

    assert result.to_mrack() == {
        'not': {
            'cpu': {
                'vendor': {
                    '_op': 'like',
                    '_value': '%Intel'
                    }
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


def test_virtualization_hypervisor(root_logger: Logger) -> None:
    result = _CONSTRAINT_TRANSFORMERS['virtualization.hypervisor'](
        _parse_virtualization({"hypervisor": "~ kvm"}), root_logger)

    assert result.to_mrack() == {
        'system': {
            'hypervisor': {
                '_op': 'like',
                '_value': 'kvm'
                }
            }
        }

    result = _CONSTRAINT_TRANSFORMERS['virtualization.hypervisor'](
        _parse_virtualization({"hypervisor": "!~ kvm"}), root_logger)

    assert result.to_mrack() == {
        'not': {
            'system': {
                'hypervisor': {
                    '_op': 'like',
                    '_value': 'kvm'
                    }
                }
            }
        }

    result = _CONSTRAINT_TRANSFORMERS['virtualization.hypervisor'](
        _parse_virtualization({"hypervisor": "kvm"}), root_logger)

    assert result.to_mrack() == {
        'system': {
            'hypervisor': {
                '_op': '==',
                '_value': 'kvm'
                }
            }
        }

    result = _CONSTRAINT_TRANSFORMERS['virtualization.hypervisor'](
        _parse_virtualization({"hypervisor": "!= kvm"}), root_logger)

    assert result.to_mrack() == {
        'system': {
            'hypervisor': {
                '_op': '!=',
                '_value': 'kvm'
                }
            }
        }


def test_zcrypt_adapter(root_logger: Logger) -> None:
    result = _CONSTRAINT_TRANSFORMERS['zcrypt.adapter'](
        _parse_zcrypt({'adapter': 'CEX8C'}), root_logger)

    assert result.to_mrack() == {
        'system': {
            'key_value': {
                '_key': 'ZCRYPT_MODEL',
                '_op': '==',
                '_value': 'CEX8C'
                }
            }
        }

    result = _CONSTRAINT_TRANSFORMERS['zcrypt.adapter'](
        _parse_zcrypt({'adapter': '!= CEX8C'}), root_logger)

    assert result.to_mrack() == {
        'system': {
            'key_value': {
                '_key': 'ZCRYPT_MODEL',
                '_op': '!=',
                '_value': 'CEX8C'
                }
            }
        }

    result = _CONSTRAINT_TRANSFORMERS['zcrypt.adapter'](
        _parse_zcrypt({'adapter': '~ CEX.*'}), root_logger)

    assert result.to_mrack() == {
        'system': {
            'key_value': {
                '_key': 'ZCRYPT_MODEL',
                '_op': 'like',
                '_value': 'CEX%'
                }
            }
        }

    result = _CONSTRAINT_TRANSFORMERS['zcrypt.adapter'](
        _parse_zcrypt({'adapter': '!~ CEX.*'}), root_logger)

    assert result.to_mrack() == {
        'not': {
            'system': {
                'key_value': {
                    '_key': 'ZCRYPT_MODEL',
                    '_op': 'like',
                    '_value': 'CEX%'
                    }
                }
            }
        }


def test_zcrypt_mode(root_logger: Logger) -> None:
    result = _CONSTRAINT_TRANSFORMERS['zcrypt.mode'](
        _parse_zcrypt({'mode': 'CCA'}), root_logger)

    assert result.to_mrack() == {
        'system': {
            'key_value': {
                '_key': 'ZCRYPT_MODE',
                '_op': '==',
                '_value': 'CCA'
                }
            }
        }

    result = _CONSTRAINT_TRANSFORMERS['zcrypt.mode'](
        _parse_zcrypt({'mode': '!= CCA'}), root_logger)

    assert result.to_mrack() == {
        'system': {
            'key_value': {
                '_key': 'ZCRYPT_MODE',
                '_op': '!=',
                '_value': 'CCA'
                }
            }
        }

    result = _CONSTRAINT_TRANSFORMERS['zcrypt.mode'](
        _parse_zcrypt({'mode': '~ C.*A'}), root_logger)

    assert result.to_mrack() == {
        'system': {
            'key_value': {
                '_key': 'ZCRYPT_MODE',
                '_op': 'like',
                '_value': 'C%A'
                }
            }
        }

    result = _CONSTRAINT_TRANSFORMERS['zcrypt.mode'](
        _parse_zcrypt({'mode': '!~ C.*A'}), root_logger)

    assert result.to_mrack() == {
        'not': {
            'system': {
                'key_value': {
                    '_key': 'ZCRYPT_MODE',
                    '_op': 'like',
                    '_value': 'C%A'
                    }
                }
            }
        }


def test_location_lab_controller(root_logger: Logger) -> None:

    result = _CONSTRAINT_TRANSFORMERS['location.lab_controller'](
        _parse_location({"lab-controller": "lab-01.bar.redhat.com"}), root_logger)

    assert result.to_mrack() == {
        'labcontroller': {
            '_op': '==',
            '_value': 'lab-01.bar.redhat.com'
            }
        }

    result = _CONSTRAINT_TRANSFORMERS['location.lab_controller'](
        _parse_location({"lab-controller": "!= lab-01.bar.redhat.com"}), root_logger)

    assert result.to_mrack() == {
        'labcontroller': {
            '_op': '!=',
            '_value': 'lab-01.bar.redhat.com'
            }
        }


def test_tpm_version(root_logger: Logger) -> None:
    result = _CONSTRAINT_TRANSFORMERS['tpm.version'](
        _parse_tpm({'version': '2.0'}), root_logger)

    assert result.to_mrack() == {
        'key_value': {
            '_key': 'TPM',
            '_op': '==',
            '_value': '2.0'
            }
        }

    result = _CONSTRAINT_TRANSFORMERS['tpm.version'](
        _parse_tpm({'version': '!= 2.0'}), root_logger)

    assert result.to_mrack() == {
        'key_value': {
            '_key': 'TPM',
            '_op': '!=',
            '_value': '2.0'
            }
        }


def test_system_numa_nodes(root_logger: Logger) -> None:
    result = _CONSTRAINT_TRANSFORMERS['system.numa_nodes'](
        _parse_system({'numa-nodes': '2'}), root_logger)

    assert result.to_mrack() == {
        'system': {
            'numanodes': {
                '_op': '==',
                '_value': '2'
                }
            }
        }
