import pytest
from unittest.mock import MagicMock, PropertyMock, patch, call
import subprocess
import textwrap
import os

import tmt


@pytest.fixture(scope="function")
def change_test_dir(request, tmpdir):
    # Change to test case directory
    os.chdir(tmpdir)
    # Run the test
    yield
    # Change back to the calling directory to avoid side-effects
    os.chdir(request.config.invocation_dir)

class TestEnd2End:
    @patch('tmt.export.import_nitrate')
    def test_not_exist_no_create(self, mock_import_nitrate, tmpdir):
        # initialize fmf/tmt structure
        subprocess.check_call("fmf init".split(), cwd=str(tmpdir))

        # prepare main.fmf
        tmpdir.join('main.fmf').write(textwrap.dedent(
        """
        test: echo 'hooray'
        framework: shell
        summary: Fancy summary
        """))

        # Load singe test defined above
        test = tmt.Tree(str(tmpdir)).tests(names=['/'])[0]

        with pytest.raises(tmt.utils.ConvertError) as exc_info:
            tmt.export.export_to_nitrate(test, create=False, general=True)
        assert "Nitrate test case id not found." == str(exc_info.value)

        # TODO: Test invalid extra-nitrate (no prefix, not integer)

    def test_exists(self, change_test_dir, tmpdir):
        # initialize fmf/tmt structure
        subprocess.check_call("fmf init".split(), cwd=str(tmpdir))
        subprocess.check_call("git init".split(), cwd=str(tmpdir))
        subprocess.check_call(f"git remote add origin {tmpdir}/foo".split(), cwd=str(tmpdir))
        # prepare main.fmf
        tmpdir.join('main.fmf').write(textwrap.dedent(
        """
        test: echo 'hooray'
        framework: shell
        summary: Fancy summary
        extra-nitrate: TC#1234
        """))
        subprocess.check_call("git add .".split(), cwd=str(tmpdir))
        subprocess.check_call("git commit -m init".split(), cwd=str(tmpdir))

        # Load singe test defined above
        test = tmt.Tree(str(tmpdir)).tests(names=['/'])[0]

        def fake_import():
            pass

        class LocalCases:
            created = []
            def case_factory(*args, **kwargs):
                mock = MagicMock()
                LocalCases.created.append(mock)
                if args[0] == 1234:
                    type(mock).notes = "" #PropertyMock(return_value="")
                    type(mock).tags = Container()
                return mock

        class Container(object):
            def __init__(self, *args, **kwargs):
                self._data = []
            def add(self, value):
                self._data.append(value)
            def clear(self):
                self._data = []

        tmt.export.import_nitrate = fake_import
        tmt.export.nitrate = MagicMock
        tmt.export.nitrate.Tag = str
        tmt.export.nitrate.CaseStatus = str
        tmt.export.nitrate.TestCase = MagicMock(side_effect=LocalCases.case_factory)
        tmt.export.nitrate.NitrateError = tmt.utils.GeneralError
        tmt.export.gssapi = MagicMock
        tmt.export.gssapi.raw = MagicMock
        tmt.export.gssapi.raw.misc = MagicMock
        tmt.export.gssapi.raw.misc.GSSError = tmt.utils.GeneralError

        tmt.export.export_to_nitrate(test, create=False, general=True)
        assert len(LocalCases.created) == 1
        case = LocalCases.created[0]
        assert case.tags._data == [['fmf-export']]
        assert case.summary == "Fancy summary"

        assert "[fmf]" in case.notes
        assert "name: /" in case.notes
        assert f"url: {tmpdir}/foo" in case.notes

        test_after = tmt.Tree(str(tmpdir)).tests(names=['/'])[0]

        assert test._metadata == test_after._metadata


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