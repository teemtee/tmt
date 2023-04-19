from textwrap import dedent

import pytest

from tmt.convert import extract_relevancy, filter_common_data
from tmt.utils import StructuredField


def test_extract_relevancy_field_has_priority():
    notes = dedent("""
    relevancy:
    distro == fedora: False

    [structured-field-start]
    This is StructuredField version 1. Please, edit with care.

    [relevancy]
    distro == rhel: False

    [structured-field-end]
  """)

    field = StructuredField(notes)
    relevancy = extract_relevancy(notes, field)
    assert relevancy == "distro == rhel: False\n"


@pytest.mark.parametrize(
    ('expected', 'individual'),
    [
        ({'common': {1: 1, 2: 2}, 'individual': [{}, {}]},
         [{1: 1, 2: 2}, {1: 1, 2: 2}]),
        ({'common': {1: 1}, 'individual': [{2: 2}, {3: 3}]},
         [{1: 1, 2: 2}, {1: 1, 3: 3}]),
        ({'common': {1: 1}, 'individual': [{2: 2}, {3: 3}, {}]},
         [{1: 1, 2: 2}, {1: 1, 3: 3}, {1: 1}]),
        ({'common': {}, 'individual': [{1: 1, 2: 2}, {3: 3}]},
         [{1: 1, 2: 2}, {3: 3}]),
        ({'common': {}, 'individual': [{1: 1, 2: 2}, {3: 3}, {3: 3, 4: 4}]},
         [{1: 1, 2: 2}, {3: 3}, {3: 3, 4: 4}]),
        ],
    ids=(
        'everything-common',
        'some-matches',
        'three-way-some-matches',
        'no-matches',
        'three-way-no-matches',
        )
    )
def test_filter_common_data(expected, individual):
    common = {}
    filter_common_data(common, individual)
    assert common == expected['common']
    assert individual == expected['individual']
