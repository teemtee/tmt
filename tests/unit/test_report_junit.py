import xml.dom
import xml.dom.minidom
from unittest.mock import MagicMock, PropertyMock

import pytest

from tmt.result import Result, ResultOutcome
from tmt.steps.report.junit import ReportJUnit, ReportJUnitData
from tmt.utils import Path


@pytest.fixture
def report_fix(tmppath: Path, root_logger):
    # need to provide genuine workdir paths - mock would break os.path.* calls
    step_mock = MagicMock(workdir=tmppath)
    plan_mock = MagicMock()
    name_property = PropertyMock(return_value='name')

    type(plan_mock).name = name_property
    type(step_mock).plan = plan_mock

    out_file_path = Path(tmppath / "out.xml")

    report = ReportJUnit(
        logger=root_logger,
        step=step_mock,
        data=ReportJUnitData(name='x', how='junit', file=out_file_path),
        workdir=tmppath / 'junit')
    report.info = MagicMock()

    results = []

    execute_mock = MagicMock()
    type(execute_mock).results = MagicMock(return_value=results)
    type(plan_mock).execute = execute_mock

    return report, results, out_file_path


# A simple way would be comparing XML nodes as strings, e.g. output of their
# .toprettyxml() methods. But that has been observed as not fully deterministic
# with Python 3.6, changing order or attributes from time to time. Therefore
# taking the longer, more verbose approach.
def _compare_xml_node(tree_path: list[str], expected: xml.dom.Node, actual: xml.dom.Node) -> None:
    """ Assert two XML nodes have the same content """

    # All of this would be doable in a much, much simpler, condensed manner,
    # but being more verbose allows for way more specific error message when
    # comparison fails.

    tree_path_joined = '.'.join(tree_path)

    # Make sure node names do match.
    assert expected.nodeName == actual.nodeName, \
        (f"Element name mismatch at {tree_path_joined}: "
         f"expected {expected.nodeName}, found {actual.nodeName}")

    # If nodes have the same tag, move on to attributes. Make sure both nodes
    # have the same set of attributes, with same respective values.
    #
    # Note: sometimes, node.attributes may be set to `None`, meaning "no attributes",
    # which is fine as long as the other node also has no attributes.
    expected_attributes = sorted((expected.attributes or {}).items())
    actual_attributes = sorted((actual.attributes or {}).items())

    assert len(expected_attributes) == len(actual_attributes), \
        (f"Attribute count mismatch at {tree_path_joined}: "
         f"expected {len(expected_attributes)}, found {len(actual_attributes)}")

    for (expected_name, expected_value), (actual_name, actual_value) in zip(
            expected_attributes, actual_attributes):
        assert expected_name == actual_name, (f'Attribute mismatch at {tree_path_joined}: '
                                              f'expected {expected_name}="{expected_value}"')
        assert expected_value == actual_value, (f'Attribute mismatch at {tree_path_joined}: '
                                                f'found {actual_name}="{actual_value}"')

    # Hooray, attributes match. Dig deeper, how about children?
    # To compare children, use this very function to compare each child with
    # a corresponding child of the other node.
    #
    # Note: skip empty text nodes. For the purpose of comparing XML structure of junit
    # XML, they are not important - in this case, they are spawned by indentation of
    # elements in the expected XML string, and they do not affect the semantics of those
    # nodes.
    def _valid_children(node: xml.dom.Node) -> list[xml.dom.Node]:
        return [
            child for child in node.childNodes
            if child.nodeType != xml.dom.Node.TEXT_NODE or child.data.strip()
            ]

    expected_children = _valid_children(expected)
    actual_children = _valid_children(actual)

    assert len(expected_children) == len(actual_children), \
        (f"Children count mismatch at {tree_path_joined}: "
         f"expected {len(expected_children)}, found {len(actual_children)}")

    return all(
        _compare_xml_node(
            [*tree_path, expected_child.nodeName],
            expected_child,
            actual_child) for expected_child,
        actual_child in zip(
            expected.childNodes,
            actual.childNodes))


def assert_xml(actual_filepath, expected):
    with open(actual_filepath) as f, xml.dom.minidom.parse(f) as actual_dom, \
            xml.dom.minidom.parseString(expected) as expected_dom:
        assert _compare_xml_node([expected_dom.nodeName], expected_dom, actual_dom)


@pytest.mark.skipif(pytest.__version__.startswith('3'),
                    reason="too old pytest")
class TestStateMapping:
    def test_pass(self, report_fix):
        report, results, out_file_path = report_fix
        results.append(Result(result=ResultOutcome.PASS, name="/pass", serial_number=1))

        report.go()

        assert_xml(out_file_path, """<?xml version='1.0' encoding='utf-8'?>
<testsuites disabled="0" errors="0" failures="0" tests="1" time="0.0">
  <testsuite name="name" disabled="0" errors="0" failures="0" skipped="0" tests="1" time="0.0">
    <testcase name="/pass">


                </testcase>
  </testsuite>
</testsuites>
""")

    def test_info(self, report_fix):
        report, results, out_file_path = report_fix
        results.append(Result(result=ResultOutcome.INFO, name="/info", serial_number=1))
        report.go()

        assert_xml(out_file_path, """<?xml version='1.0' encoding='utf-8'?>
<testsuites disabled="0" errors="0" failures="0" tests="1" time="0.0">
  <testsuite name="name" disabled="0" errors="0" failures="0" skipped="1" tests="1" time="0.0">
    <testcase name="/info">
      <skipped type="skipped" message="info"/>
    </testcase>
  </testsuite>
</testsuites>
""")

    def test_warn(self, report_fix):
        report, results, out_file_path = report_fix
        results.append(Result(result=ResultOutcome.WARN, name="/warn", serial_number=1))
        report.go()

        assert_xml(out_file_path, """<?xml version='1.0' encoding='utf-8'?>
<testsuites disabled="0" errors="1" failures="0" tests="1" time="0.0">
  <testsuite name="name" disabled="0" errors="1" failures="0" skipped="0" tests="1" time="0.0">
    <testcase name="/warn">
      <error type="error" message="warn"/>
    </testcase>
  </testsuite>
</testsuites>
""")

    def test_error(self, report_fix):
        report, results, out_file_path = report_fix
        results.append(Result(result=ResultOutcome.ERROR, name="/error", serial_number=1))
        report.go()

        assert_xml(out_file_path, """<?xml version='1.0' encoding='utf-8'?>
<testsuites disabled="0" errors="1" failures="0" tests="1" time="0.0">
  <testsuite name="name" disabled="0" errors="1" failures="0" skipped="0" tests="1" time="0.0">
    <testcase name="/error">
      <error type="error" message="error"/>
    </testcase>
  </testsuite>
</testsuites>
""")

    def test_fail(self, report_fix):
        report, results, out_file_path = report_fix
        results.append(Result(result=ResultOutcome.FAIL, name="/fail", serial_number=1))
        report.go()

        assert_xml(out_file_path, """<?xml version='1.0' encoding='utf-8'?>
<testsuites disabled="0" errors="0" failures="1" tests="1" time="0.0">
  <testsuite name="name" disabled="0" errors="0" failures="1" skipped="0" tests="1" time="0.0">
    <testcase name="/fail">
      <failure type="failure" message="fail"/>
    </testcase>
  </testsuite>
</testsuites>
""")
