import dataclasses
import os
from pathlib import Path
from time import time
from typing import Optional

from reportportal_client import ReportPortalService

import tmt.steps.report
import tmt.utils


def timestamp():
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


# # # # RP # # # #
        service = ReportPortalService(endpoint=endpoint, project=project, token=token)

        # create launch and its items
        launch_id = service.start_launch(name=launch_name,
                                         start_time=timestamp(),
                                         rerun=False,
                                         rerunOf=None,
                                         attributes={"attr1": "val1", "attr2": "val2"},
                                         description="Testing RP API")

        suite_id = service.start_test_item(name="Suite",
                                           start_time=timestamp(),
                                           item_type="SUITE",
                                           attributes={"attr1": "val1", "attr2": "val2"},
                                           description="Some Test Plan")

        test_id = service.start_test_item(name="Test Case",
                                          start_time=timestamp(),
                                          item_type="TEST",
                                          parent_item_id=suite_id,
                                          test_case_id="xx123",
                                          code_ref="12345xxx",
                                          parameters={"key1": "val1", "key2": "val2"},
                                          attributes={"attr1": "val1", "attr2": "val2"},
                                          description="Some Test Case")
        print("URL:         " + service.get_launch_ui_url())
        print("LAUNCH UIID: " + str(service.get_launch_ui_id()))
        print("LAUNCH ID:   " + launch_id)
        print("SUITE ID:    " + suite_id)
        print("TEST ID:     " + test_id)

        # report the logs
        service.log(item_id=test_id,
                    time=timestamp(),
                    message="Hello World!",
                    level="INFO")
        log = "/var/tmp/tmt/run-341/plans/default/execute/data/test/output.txt"
        service.log(item_id=test_id,
                    time=timestamp(),
                    message=Path(log).read_text(),
                    level="INFO")
        service.log(item_id=test_id,
                    time=timestamp(),
                    message="Adding log attachment",
                    level="INFO",
                    attachment={"name": "output.txt",
                                "data": Path(log).read_text(),
                                "mime": "text/plain"})

        # finnish reporting
        service.finish_test_item(item_id=test_id, end_time=timestamp(), status="PASSED")
        service.finish_test_item(item_id=suite_id, end_time=timestamp(), status="PASSED")
        service.finish_launch(end_time=timestamp())
        service.terminate()
# # # # # # # # #

        return
