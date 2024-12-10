from typing import Any

import pytest

import tmt.cli.trying


@pytest.mark.parametrize(
    ('params', 'expected'),
    [
        ({'image_and_how': ('fedora@virtual',), 'arch': None},
         {'image': 'fedora', 'how': 'virtual'}),
        ({'image_and_how': ('fedora@virtual',), 'arch': 'aarch64'},
         {'image': 'fedora', 'how': 'virtual', 'arch': 'aarch64'}),
        ({'image_and_how': (), 'arch': 'aarch64'},
         {'arch': 'aarch64'}),
        ]
    )
def test_options_arch(params: dict[str, Any], expected: dict[str, Any]):

    assert tmt.cli.trying._construct_trying_provision_options(params) == expected
