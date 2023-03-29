import dataclasses
import os
from time import time
from typing import Optional

from reportportal_client import ReportPortalService

import tmt.steps.report
import tmt.utils


def timestamp() -> str:
    return str(int(time() * 1000))


@dataclasses.dataclass
class ReportReportPortalData(tmt.steps.report.ReportStepData):
    url: Optional[str] = tmt.utils.field(
        option="--url",
        metavar="URL",
        default=os.environ.get("TMT_REPORT_REPORTPORTAL_URL"),
        help="The URL of the ReportPortal instance where the data should be sent to.")
    token: Optional[str] = tmt.utils.field(
        option="--token",
        metavar="TOKEN",
        default=os.environ.get("TMT_REPORT_REPORTPORTAL_TOKEN"),
        help="The token to use for upload to the ReportPortal instance.")
    project: Optional[str] = tmt.utils.field(
        option="--project",
        metavar="PROJECT",
        default=None,
        help="The project name which is used to create the full URL.")
    launch_name: Optional[str] = tmt.utils.field(
        option="--launch-name",
        metavar="LAUNCH_NAME",
        default=None,
        help="The launch name (base name of run id used by default).")


@tmt.steps.provides_method("reportportal")
class ReportReportPortal(tmt.steps.report.ReportPlugin):
    """  Report test results to a ReportPortal instance  """

    _data_class = ReportReportPortalData

    def go(self) -> None:
        """ Process results """
        super().go()

        endpoint = self.get("url")
        project = self.get("project")
        token = self.get("token")
        launch_name = self.get("launch-name")

        service = ReportPortalService(endpoint=endpoint, project=project, token=token)

        attributes = {k: v[0] for k, v in self.step.plan._fmf_context().items()}
        # create launch and its items
        launch_id = service.start_launch(name=launch_name,
                                         start_time=timestamp(),
                                         rerun=False,
                                         rerunOf=None,
                                         attributes=attributes,
                                         description="Testing RP API")

        suite_id = service.start_test_item(name="Suite",
                                           start_time=timestamp(),
                                           item_type="SUITE",
                                           attributes=attributes,
                                           description="Some Test Plan")

        attributes['contact'] = self.step.plan.discover.tests()[0].contact[0]
        test_id = service.start_test_item(name="Test Case",
                                          start_time=timestamp(),
                                          item_type="TEST",
                                          parent_item_id=suite_id,
                                          test_case_id="xx123",
                                          code_ref="12345xxx",
                                          parameters={"key1": "val1", "key2": "val2"},
                                          attributes=attributes,
                                          description="Some Test Case")

        print("URL:         " + str(service.get_launch_ui_url()))
        print("LAUNCH UIID: " + str(service.get_launch_ui_id()))
        print("LAUNCH ID:   " + str(launch_id))
        print("SUITE ID:    " + str(suite_id))
        print("TEST ID:     " + str(test_id))

        # report the logs
        for result in self.step.plan.execute.results():
            for log_path in result.log:
                try:
                    log = self.step.plan.execute.read(log_path)
                except (IndexError, AttributeError):
                    log = None

                print("LOG: " + str(log_path))
                service.log(item_id=test_id,
                            time=timestamp(),
                            message=str(os.path.basename(log_path)) + ":\n" + log,
                            level="INFO")

        # finnish reporting
        service.finish_test_item(item_id=test_id, end_time=timestamp(), status="PASSED")
        service.finish_test_item(item_id=suite_id, end_time=timestamp(), status="PASSED")
        service.finish_launch(end_time=timestamp())
        service.terminate()

        return
