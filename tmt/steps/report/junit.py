import dataclasses
import os
from typing import TYPE_CHECKING, List, Optional, overload

import click

import tmt
import tmt.base
import tmt.options
import tmt.plugins
import tmt.result
import tmt.steps
import tmt.steps.report
from tmt.plugins import LazyModuleImporter

if TYPE_CHECKING:
    import junit_xml


DEFAULT_NAME = "junit.xml"


import_junit_xml: LazyModuleImporter['junit_xml'] = LazyModuleImporter(
    'junit_xml',
    tmt.utils.ReportError,
    "Missing 'junit-xml', fixable by 'pip install tmt[report-junit]'."
    )


@overload
def duration_to_seconds(duration: str) -> int: pass


@overload
def duration_to_seconds(duration: None) -> None: pass


def duration_to_seconds(duration: Optional[str]) -> Optional[int]:
    """ Convert valid duration string in to seconds """
    if duration is None:
        return None
    try:
        h, m, s = duration.split(':')
        return int(h) * 3600 + int(m) * 60 + int(s)
    except Exception as error:
        raise tmt.utils.ReportError(
            f"Malformed duration '{duration}' ({error}).")


def make_junit_xml(report: "tmt.steps.report.ReportPlugin") -> 'junit_xml.TestSuite':
    """ Create junit xml object """
    junit_xml = import_junit_xml()

    suite = junit_xml.TestSuite(report.step.plan.name)

    for result in report.step.plan.execute.results():
        try:
            main_log = report.step.plan.execute.read(result.log[0])
        except (IndexError, AttributeError):
            main_log = None
        case = junit_xml.TestCase(
            result.name,
            classname=None,
            elapsed_sec=duration_to_seconds(result.duration),
            stdout=main_log)
        # Map tmt OUTCOME to JUnit states
        if result.result == tmt.result.ResultOutcome.ERROR:
            case.add_error_info(result.result.value, output=result.failures(main_log))
        elif result.result == tmt.result.ResultOutcome.FAIL:
            case.add_failure_info(result.result.value, output=result.failures(main_log))
        elif result.result == tmt.result.ResultOutcome.INFO:
            case.add_skipped_info(result.result.value, output=result.failures(main_log))
        elif result.result == tmt.result.ResultOutcome.WARN:
            case.add_error_info(result.result.value, output=result.failures(main_log))
        # Passed state is the default
        suite.test_cases.append(case)

    return suite


@dataclasses.dataclass
class ReportJUnitData(tmt.steps.report.ReportStepData):
    file: Optional[str] = None


@tmt.steps.provides_method('junit')
class ReportJUnit(tmt.steps.report.ReportPlugin):
    """
    Write test results in JUnit format

    When FILE is not specified output is written to the 'junit.xml'
    located in the current workdir.
    """

    _data_class = ReportJUnitData

    @classmethod
    def options(cls, how: Optional[str] = None) -> List[tmt.options.ClickOptionDecoratorType]:
        """ Prepare command line options for connect """
        return [
            click.option(
                '--file', metavar='FILE',
                help='Path to the file to store junit to'),
            ] + super().options(how)

    def prune(self) -> None:
        """ Do not prune generated junit report """
        pass

    def go(self) -> None:
        """ Read executed tests and write junit """
        super().go()

        junit_xml = import_junit_xml()
        suite = make_junit_xml(self)

        assert self.workdir is not None
        f_path = self.get("file", os.path.join(self.workdir, DEFAULT_NAME))
        try:
            with open(f_path, 'w') as fw:
                if hasattr(junit_xml, 'to_xml_report_file'):
                    junit_xml.to_xml_report_file(fw, [suite])
                else:
                    # For older junit-xml
                    junit_xml.TestSuite.to_file(fw, [suite])
            self.info("output", f_path, 'yellow')
        except Exception as error:
            raise tmt.utils.ReportError(
                f"Failed to write the output '{f_path}' ({error}).")
