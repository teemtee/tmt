import dataclasses
from typing import TYPE_CHECKING, Optional, overload

import tmt
import tmt.base
import tmt.log
import tmt.options
import tmt.result
import tmt.steps
import tmt.steps.report
import tmt.utils
from tmt.plugins import ModuleImporter
from tmt.utils import Path, field

if TYPE_CHECKING:
    import junit_xml

    from tmt.steps.report import ReportPlugin
    from tmt.steps.report.polarion import ReportPolarionData

DEFAULT_NAME = "junit.xml"


# ignore[unused-ignore]: Pyright would report that "module cannot be
# used as a type", and it would be correct. On the other hand, it works,
# and both mypy and pyright are able to propagate the essence of a given
# module through `ModuleImporter` that, eventually, the module object
# returned by the importer does have all expected members.
#
# The error message does not have its own code, but simple `type: ignore`
# is enough to suppress it. And then mypy complains about an unused
# ignore, hence `unused-ignore` code, leading to apparently confusing
# directive.
import_junit_xml: ModuleImporter['junit_xml'] = ModuleImporter(  # type: ignore[unused-ignore]
    'junit_xml',
    tmt.utils.ReportError,
    "Missing 'junit-xml', fixable by 'pip install tmt[report-junit]'.",
    tmt.log.Logger.get_bootstrap_logger())


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


def make_junit_xml(
        report: 'ReportPlugin[ReportJUnitData]|ReportPlugin[ReportPolarionData]'
        ) -> 'junit_xml.TestSuite':
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
            elapsed_sec=duration_to_seconds(result.duration))

        if report.data.include_output_log:
            case.stdout = main_log

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
    file: Optional[Path] = field(
        default=None,
        option='--file',
        metavar='PATH',
        help='Path to the file to store JUnit to.',
        normalize=lambda key_address, raw_value, logger: Path(raw_value) if raw_value else None)

    include_output_log: bool = field(
        default=True,
        option=('--include-output-log / --no-include-output-log'),
        is_flag=True,
        show_default=True,
        help='Include full standard output in resulting xml file.')


@tmt.steps.provides_method('junit')
class ReportJUnit(tmt.steps.report.ReportPlugin[ReportJUnitData]):
    """
    Save test results in JUnit format.

    When ``file`` is not specified, output is written into a file
    named ``junit.xml`` located in the current workdir.
    """

    _data_class = ReportJUnitData

    def prune(self, logger: tmt.log.Logger) -> None:
        """ Do not prune generated junit report """

    def go(self, *, logger: Optional[tmt.log.Logger] = None) -> None:
        """ Read executed tests and write junit """
        super().go(logger=logger)

        junit_xml = import_junit_xml()
        suite = make_junit_xml(self)

        assert self.workdir is not None
        f_path = self.data.file or self.workdir / DEFAULT_NAME
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
