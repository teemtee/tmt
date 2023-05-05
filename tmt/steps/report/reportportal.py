import dataclasses
import os
from time import time
from typing import List, Optional

from reportportal_client import ReportPortalService

import tmt.steps.report
import tmt.utils


def timestamp() -> str:
    return str(int(time() * 1000))


def get_status(result: tmt.result.ResultOutcome) -> str:
    if result == tmt.result.ResultOutcome.PASS:
        return "PASSED"
    elif result == tmt.result.ResultOutcome.FAIL \
            or result == tmt.result.ResultOutcome.ERROR \
            or result == tmt.result.ResultOutcome.WARN:
        return "FAILED"
    else:  # elif result == tmt.result.ResultOutcome.INFO:
        return "SKIPPED"


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
    project: Optional[str] = tmt.utils.field(  # todo: argument should be mandatory
        option="--project",
        metavar="PROJECT",
        default=None,
        help="The project name which is used to create the full URL.")
    launch_name: Optional[str] = tmt.utils.field(
        option="--launch-name",
        metavar="LAUNCH_NAME",
        default=None,
        help="The launch name (base name of run id used by default).")
    env_vars: Optional[List[str]] = tmt.utils.field(
        option="--env-vars",
        metavar="[TMT_VARS]",
        default=None,
        help="List of environment variables \"TMT_\" to disobey the rule \
                        of not displaying them in Report Portal launch.")


@tmt.steps.provides_method("reportportal")
class ReportReportPortal(tmt.steps.report.ReportPlugin):
    """
    Report test results to a ReportPortal instance via reportportal_client API

    Requires a TOKEN for authentication, a URL of the ReportPortal
     instance and the PROJECT name. In addition to command line options
     it's possible to use environment variables to set the url and token:

        export TMT_REPORT_REPORTPORTAL_URL=...
        export TMT_REPORT_REPORTPORTAL_TOKEN=...

    The optional launch NAME doesn't have to be provided if it is the same
     as the plan name (by default). Assuming the URL and TOKEN variables
     are provided by the environment, the config can
     look like this:

        report:
            how: reportportal
            project: baseosqe

    In item details of the ReportPortal instance, the environment variables
     per test are displayed except those that begin with ``TMT_``
     (unique variables break history aggregation). To obey this rule, list
     these variables for particular use case with option --env-vars
            env-vars: [TMT_TEST_DATA,TMT_PLAN_DATA]
    """

    _data_class = ReportReportPortalData

    def go(self) -> None:
        """
        Create a ReportPortal launch and its test items,
        fill it with all parts needed and report the logs.
        """

        super().go()

        endpoint = self.get("url")
        if not endpoint:
            raise tmt.utils.ReportError("No ReportPortal server url provided.")
        project = self.get("project")
        if not project:
            raise tmt.utils.ReportError("No ReportPortal project provided.")
        token = self.get("token")
        if not token:
            raise tmt.utils.ReportError("No ReportPortal token provided.")

        launch_name = self.step.plan.name if not self.get("launch-name") \
            else self.get("launch-name")

        service = ReportPortalService(endpoint=endpoint, project=project, token=token)
        assert service is not None

        attributes = {k: v[0] for k, v in self.step.plan._fmf_context().items()}
        env_variables = self.get("env-vars") if self.get("env-vars") else []
        # # or if you want to use env_variables from the environment:
        # env_variables = os.environ.get("TMT_REPORT_REPORTPORTAL_ENVARS").split(", ") \
        #              if os.environ.get("TMT_REPORT_REPORTPORTAL_ENVARS") else []

        # create launch and its items
        self.debug("Uploading a launch into Report Portal server")
        launch_id = service.start_launch(name=launch_name,
                                         start_time=timestamp(),
                                         rerun=False,
                                         rerunOf=None,
                                         attributes=attributes,
                                         description=self.step.plan.summary)
        assert launch_id is not None
        launch_ui_id = str(service.get_launch_ui_id())
        launch_url = str(service.get_launch_ui_url())

        self.debug(f"ReportPortal launch ID:    {launch_id}")
        self.debug(f"ReportPortal launch UI_ID: {launch_ui_id}")
        self.debug(f"ReportPortal launch URL:   {launch_url}")

        # report the logs
        self.debug("Uploading tests into Report Portal server")
        for result in self.step.plan.execute.results():

            # create test item
            test = [test for test in self.step.plan.discover.tests()
                    if test.serialnumber == result.serialnumber][0]
            attributes['contact'] = test.contact[0]
            self.debug("Creating Report Portal test item")
            test_id = service.start_test_item(
                name=result.name,
                start_time=timestamp(),
                item_type="TEST",
                test_case_id=None if not test.id else test.id,
                code_ref=None if not test.web_link() else test.web_link(),
                parameters={k: v for k, v in test.environment.items()
                            if not k.startswith("TMT_") or k in env_variables},
                attributes=attributes,
                description=test.summary)
            assert test_id is not None
            self.debug(f"ReportPortal test ID:      {str(test_id)}")

            self.debug("Uploading logs into Report Portal server")
            for log_path in result.log:
                try:
                    log = self.step.plan.execute.read(log_path)
                except (IndexError, AttributeError):
                    log = None

                if not log:
                    continue
                service.log(item_id=test_id,
                            time=timestamp(),
                            message=str(os.path.basename(log_path)) + ":\n" + log,
                            level="INFO")
                self.debug(f"Upoaded the log: {str(log_path)}")

            self.debug("Finishing Report Portal test item")
            service.finish_test_item(
                item_id=test_id,
                end_time=timestamp(),
                status=get_status(result.result))

        # finish reporting
        self.debug("Finishing Report Portal launch")
        service.finish_launch(end_time=timestamp())
        service.terminate()

        self.info("Report Portal launch URL", launch_url)

        return
