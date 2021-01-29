import pytest
from unittest.mock import MagicMock, PropertyMock, patch, call

import tmt

def test_find_general_plan():
    # correct first attempt
    with patch('nitrate.TestPlan') as mock:
        mock.search.return_value = ["Found_Plan"]
        value = tmt.export.find_general_plan('foo')
    mock.search.assert_called_once_with(type__name='General', is_active=True, component__name='foo')
    assert value == "Found_Plan"

    # found on second attempt
    with patch('nitrate.TestPlan') as mock:
        mock.search = MagicMock(side_effect=[False, ["Found_Plan"]])
        value = tmt.export.find_general_plan('bar')
    mock.search.assert_has_calls([
        call(type__name='General', is_active=True, component__name='bar'),
        call(type__name='General', is_active=True, name='bar / General'),
    ])
    assert value == "Found_Plan"

@patch('nitrate.Product')
@patch('nitrate.Category')
@patch('nitrate.TestCase')
def test_create_nitrate_case(mock_testcase, mock_category, mock_product):
    mock_category.return_value = "CATEGORY"

    test = tmt.Test({'test': 'test.sh', 'extra-summary': 'EXTRA_SUMMARY'}, name="/demo")
    testcase = tmt.export.create_nitrate_case(test)
    mock_testcase.assert_called_once_with(summary='EXTRA_SUMMARY', category='CATEGORY')

    mock_testcase.reset_mock()
    mock_category.reset_mock()
    mock_product.reset_mock()
    test = tmt.Test({'test': 'test.sh'}, name="/demo")
    testcase = tmt.export.create_nitrate_case(test)
    mock_testcase.assert_called_once_with(summary='EXTRA_SUMMARY', category='CATEGORY')