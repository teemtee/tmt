import pytest

from tmt.plugins.plan_shapers.matrix import (
    MatrixCombination,
    combination_name,
    compute_combinations,
    filter_combinations,
    parse_matrix,
)


class TestComputeCombinations:
    def test_single_variable(self):
        result = compute_combinations({'mode': ['debug', 'release']})
        assert result == [
            {'mode': 'debug'},
            {'mode': 'release'},
        ]

    def test_two_variables(self):
        result = compute_combinations({
            'mode': ['debug', 'release'],
            'distro': ['fedora', 'ubuntu'],
        })
        assert result == [
            {'mode': 'debug', 'distro': 'fedora'},
            {'mode': 'debug', 'distro': 'ubuntu'},
            {'mode': 'release', 'distro': 'fedora'},
            {'mode': 'release', 'distro': 'ubuntu'},
        ]

    def test_three_variables(self):
        result = compute_combinations({
            'a': ['1', '2'],
            'b': ['x', 'y'],
            'c': ['p'],
        })
        assert result == [
            {'a': '1', 'b': 'x', 'c': 'p'},
            {'a': '1', 'b': 'y', 'c': 'p'},
            {'a': '2', 'b': 'x', 'c': 'p'},
            {'a': '2', 'b': 'y', 'c': 'p'},
        ]

    def test_single_value_per_variable(self):
        result = compute_combinations({
            'mode': ['debug'],
            'distro': ['fedora'],
        })
        assert result == [{'mode': 'debug', 'distro': 'fedora'}]

    def test_empty_variables(self):
        result = compute_combinations({})
        assert result == [{}]

    def test_empty_value_list(self):
        result = compute_combinations({'mode': []})
        assert result == []

    def test_preserves_variable_order(self):
        result = compute_combinations({
            'z_last': ['1'],
            'a_first': ['2'],
        })
        assert list(result[0].keys()) == ['z_last', 'a_first']


class TestParseMatrix:
    def test_basic(self):
        node_data = {
            'matrix': {
                'mode': ['debug', 'release'],
            },
        }
        result = parse_matrix(node_data)
        assert result == {'mode': ['debug', 'release']}

    def test_stringifies_numeric_values(self):
        node_data = {
            'matrix': {
                'python': [3.9, 3.11],
            },
        }
        result = parse_matrix(node_data)
        assert result == {'python': ['3.9', '3.11']}

    def test_scalar_value_wrapped_in_list(self):
        node_data = {
            'matrix': {
                'mode': 'debug',
            },
        }
        result = parse_matrix(node_data)
        assert result == {'mode': ['debug']}

    def test_missing_matrix_key(self):
        result = parse_matrix({})
        assert result == {}

    def test_boolean_values_lowercase(self):
        node_data = {
            'matrix': {
                'flag': [True, False],
            },
        }
        result = parse_matrix(node_data)
        assert result == {'flag': ['true', 'false']}

    def test_integer_values(self):
        node_data = {
            'matrix': {
                'count': [1, 2, 3],
            },
        }
        result = parse_matrix(node_data)
        assert result == {'count': ['1', '2', '3']}

    def test_does_not_mutate_node_data(self):
        node_data = {
            'matrix': {
                'mode': ['debug', 'release'],
            },
        }
        parse_matrix(node_data)
        assert node_data == {
            'matrix': {
                'mode': ['debug', 'release'],
            },
        }


class TestCombinationName:
    def test_single_value(self):
        assert combination_name({'mode': 'debug'}) == 'debug'

    def test_multiple_values(self):
        assert combination_name({'mode': 'debug', 'distro': 'fedora'}) == 'debug-fedora'

    def test_preserves_order(self):
        combo: MatrixCombination = {'z': '1', 'a': '2'}
        assert combination_name(combo) == '1-2'

    def test_empty_combination(self):
        assert combination_name({}) == ''


class TestFilterCombinations:
    @pytest.fixture()
    def combinations(self) -> list[MatrixCombination]:
        return [
            {'mode': 'debug', 'distro': 'fedora'},
            {'mode': 'debug', 'distro': 'ubuntu'},
            {'mode': 'release', 'distro': 'fedora'},
            {'mode': 'release', 'distro': 'ubuntu'},
        ]

    def test_single_filter(self, combinations: list[MatrixCombination]):
        result = filter_combinations(combinations, ('mode=debug',))
        assert result == [
            {'mode': 'debug', 'distro': 'fedora'},
            {'mode': 'debug', 'distro': 'ubuntu'},
        ]

    def test_multiple_filters_and(self, combinations: list[MatrixCombination]):
        result = filter_combinations(combinations, ('mode=debug', 'distro=fedora'))
        assert result == [{'mode': 'debug', 'distro': 'fedora'}]

    def test_no_match(self, combinations: list[MatrixCombination]):
        result = filter_combinations(combinations, ('mode=profile',))
        assert result == []

    def test_nonexistent_key(self, combinations: list[MatrixCombination]):
        result = filter_combinations(combinations, ('arch=x86_64',))
        assert result == []

    def test_filter_value_containing_equals(self, combinations: list[MatrixCombination]):
        combos = [{'expr': 'x=1'}, {'expr': 'x=2'}]
        result = filter_combinations(combos, ('expr=x=1',))
        assert result == [{'expr': 'x=1'}]

    def test_empty_filters(self, combinations: list[MatrixCombination]):
        result = filter_combinations(combinations, ())
        assert result == combinations
