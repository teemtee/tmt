import dataclasses
import os
import re
from typing import Optional

import requests

import tmt.steps.report
from tmt.result import ResultOutcome
from tmt.utils import field, yaml_to_dict


@dataclasses.dataclass
class ReportReportPortalData(tmt.steps.report.ReportStepData):
    url: Optional[str] = field(
        option="--url",
        metavar="URL",
        default=os.environ.get("TMT_REPORT_REPORTPORTAL_URL"),
        help="The URL of the ReportPortal instance where the data should be sent to.")
    token: Optional[str] = field(
        option="--token",
        metavar="TOKEN",
        default=os.environ.get("TMT_REPORT_REPORTPORTAL_TOKEN"),
        help="The token to use for upload to the ReportPortal instance (from the user profile).")
    project: Optional[str] = field(
        option="--project",
        metavar="PROJECT_NAME",
        default=None,
        help="Name of the project into which the results should be uploaded.")
    launch: Optional[str] = field(
        option="--launch",
        metavar="LAUNCH_NAME",
        default=None,
        help="The launch name (name of plan per launch is used by default).")
    exclude_variables: str = field(
        option="--exclude-variables",
        metavar="PATTERN",
        default="^TMT_.*",
        help="""
             Regular expression for excluding environment variables from reporting to ReportPortal
             ('^TMT_.*' used by default).
             """)


@tmt.steps.provides_method("reportportal")
class ReportReportPortal(tmt.steps.report.ReportPlugin):
    """
    Report test results to a ReportPortal instance via API.

    Requires a TOKEN for authentication, a URL of the ReportPortal
    instance and the PROJECT name. In addition to command line options
    it's possible to use environment variables to set the url and token:

        export TMT_REPORT_REPORTPORTAL_URL=...
        export TMT_REPORT_REPORTPORTAL_TOKEN=...

    The optional LAUNCH name doesn't have to be provided if it is the
    same as the plan name (by default). Assuming the URL and TOKEN
    variables are provided by the environment, the plan config can look
    like this:

        report:
            how: reportportal
            project: baseosqe

        context:
            ...

        environment:
            ...

    The context and environment sections must be filled in order to
    report context as attributes and environment variables as parameters
    in the Item Details. Environment variables can be filtered out by
    pattern to prevent overloading and to preserve the history
    aggregation for ReportPortal item if tmt id is not provided. Other
    reported fmf data are summary, id, web link and contact per test.
    """

    _data_class = ReportReportPortalData

    DEFAULT_API_VERSION = "v1"

    TMT_TO_RP_RESULT_STATUS = {
        ResultOutcome.PASS: "PASSED",
        ResultOutcome.FAIL: "FAILED",
        ResultOutcome.ERROR: "FAILED",
        ResultOutcome.WARN: "FAILED",
        ResultOutcome.INFO: "SKIPPED"
        }

    def handle_response(self, response: requests.Response) -> None:
        """
        Check the server response and raise an exception if needed.
        """

        if not response.ok:
            raise tmt.utils.ReportError(
                f"Received non-ok status code from ReportPortal: {response.text}")

        self.debug("Response code from the server", response.status_code)
        self.debug("Message from the server", response.text)

    def go(self) -> None:
        """
        Report test results to the server

        Create a ReportPortal launch and its test items,
        fill it with all parts needed and report the logs.
        """

        super().go()

        server = self.get("url")
        if not server:
            raise tmt.utils.ReportError("No ReportPortal server url provided.")
        server = server.rstrip("/")

        project = self.get("project")
        if not project:
            raise tmt.utils.ReportError("No ReportPortal project provided.")

        token = self.get("token")
        if not token:
            raise tmt.utils.ReportError("No ReportPortal token provided.")

        assert self.step.plan.name is not None
        launch_name = self.get("launch") or self.step.plan.name

        url = f"{server}/api/{self.DEFAULT_API_VERSION}/{project}"
        headers = {
            "Authorization": "bearer " + token,
            "accept": "*/*",
            "Content-Type": "application/json"}

        envar_pattern = self.get("exclude-variables") or "$^"
        attributes = [
            {'key': key, 'value': value[0]}
            for key, value in self.step.plan._fmf_context.items()]
        launch_time = self.step.plan.execute.results()[0].starttime

        # Communication with RP instance
        with tmt.utils.retry_session() as session:

            # Create a launch
            self.info("launch", launch_name, color="cyan")
            response = session.post(
                url=f"{url}/launch",
                headers=headers,
                json={
                    "name": launch_name,
                    "description": self.step.plan.summary,
                    "attributes": attributes,
                    "startTime": launch_time})
            self.handle_response(response)
            launch_uuid = yaml_to_dict(response.text).get("id")
            assert launch_uuid is not None
            self.verbose("uuid", launch_uuid, "yellow", shift=1)

            # For each test
            for result in self.step.plan.execute.results():
                test = [test for test in self.step.plan.discover.tests()
                        if test.serialnumber == result.serialnumber][0]
                # TODO: for happz, connect Test to Result if possible

                item_attributes = attributes.copy()
                if test.contact:
                    item_attributes.append({"key": "contact", "value": test.contact[0]})
                env_vars = [
                    {'key': key, 'value': value}
                    for key, value in test.environment.items()
                    if not re.search(envar_pattern, key)]

                # Create a test item
                self.info("test", result.name, color="cyan")
                response = session.post(
                    url=f"{url}/item",
                    headers=headers,
                    json={
                        "name": result.name,
                        "description": test.summary,
                        "attributes": item_attributes,
                        "parameters": env_vars,
                        "codeRef": test.web_link() or None,
                        "launchUuid": launch_uuid,
                        "type": "step",
                        "testCaseId": test.id or None,
                        "startTime": result.starttime})
                self.handle_response(response)
                item_uuid = yaml_to_dict(response.text).get("id")
                assert item_uuid is not None
                self.verbose("uuid", item_uuid, "yellow", shift=1)

                # For each log
                for index, log_path in enumerate(result.log):
                    try:
                        log = self.step.plan.execute.read(log_path)
                    except tmt.utils.FileError:
                        continue

                    level = "INFO" if log_path == result.log[0] else "TRACE"
                    status = self.TMT_TO_RP_RESULT_STATUS[result.result]

                    # Upload log
                    response = session.post(
                        url=f"{url}/log/entry",
                        headers=headers,
                        json={
                            "message": log,
                            "itemUuid": item_uuid,
                            "launchUuid": launch_uuid,
                            "level": level,
                            "time": result.endtime})
                    self.handle_response(response)

                    # Write out failures
                    if index == 0 and status == "FAILED":
                        message = result.failures(log)
                        response = session.post(
                            url=f"{url}/log/entry",
                            headers=headers,
                            json={
                                "message": message,
                                "itemUuid": item_uuid,
                                "launchUuid": launch_uuid,
                                "level": "ERROR",
                                "time": result.endtime})
                        self.handle_response(response)

                # Finish the test item
                response = session.put(
                    url=f"{url}/item/{item_uuid}",
                    headers=headers,
                    json={
                        "launchUuid": launch_uuid,
                        "endTime": result.endtime,
                        "status": status})
                self.handle_response(response)
                launch_time = result.endtime

            # Finish the launch
            response = session.put(
                url=f"{url}/launch/{launch_uuid}/finish",
                headers=headers,
                json={"endTime": launch_time})
            self.handle_response(response)
            link = yaml_to_dict(response.text).get("link")
            self.info("url", link, "magenta")
