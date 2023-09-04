import dataclasses
import os
import re
from typing import List, Optional

import requests

import tmt.steps.report
from tmt.result import ResultOutcome
from tmt.utils import field, yaml_to_dict


@dataclasses.dataclass
class ReportReportPortalData(tmt.steps.report.ReportStepData):
    url: Optional[str] = field(
        option="--url",
        metavar="URL",
        default=None,
        help="The URL of the ReportPortal instance where the data should be sent to.")
    token: Optional[str] = field(
        option="--token",
        metavar="TOKEN",
        default=None,
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
        help="Regular expression for excluding environment variables "
             "from reporting to ReportPortal ('^TMT_.*' used by default).")
    attributes: List[str] = field(
        default_factory=list,
        multiple=True,
        normalize=tmt.utils.normalize_string_list,
        option="--attributes",
        metavar="KEY:VALUE",
        help="Additional attributes to be reported to ReportPortal,"
             "especially launch attributes for merge option.")
    merge: bool = field(
        option="--merge",
        default=False,
        is_flag=True,
        help="Report suite per plan and merge them into one launch.")
    uuid: Optional[str] = field(
        option="--uuid",
        metavar="LAUNCH_UUID",
        default=None,
        help="The launch uuid for additional merging to an existing launch.")
    launch_url: str = ""
    launch_uuid: str = ""


@tmt.steps.provides_method("reportportal")
class ReportReportPortal(tmt.steps.report.ReportPlugin):
    """
    Report test results to a ReportPortal instance via API.

    Requires a token for authentication, a URL of the ReportPortal
    instance and the project name. In addition to command line options
    it's possible to use environment variables in form of
    ``TMT_PLUGIN_REPORT_REPORTPORTAL_${OPTION}``:

    .. code-block:: bash

        export TMT_PLUGIN_REPORT_REPORTPORTAL_URL=...
        export TMT_PLUGIN_REPORT_REPORTPORTAL_TOKEN=...

    The optional launch name doesn't have to be provided if it is the
    same as the plan name (by default). Assuming the URL and token
    are provided by the environment variables, the plan config can look
    like this:

    .. code-block:: yaml

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
        Check the endpoint response and raise an exception if needed.
        """

        if not response.ok:
            raise tmt.utils.ReportError(
                f"Received non-ok status code from ReportPortal: {response.text}")

        self.debug("Response code from the endpoint", str(response.status_code))
        self.debug("Message from the endpoint", str(response.text))

    def go(self) -> None:
        """
        Report test results to the endpoint

        Create a ReportPortal launch and its test items,
        fill it with all parts needed and report the logs.
        """

        super().go()

        endpoint = self.get("url", os.getenv('TMT_PLUGIN_REPORT_REPORTPORTAL_URL'))
        if not endpoint:
            raise tmt.utils.ReportError("No ReportPortal endpoint url provided.")
        endpoint = endpoint.rstrip("/")

        project = self.get("project", os.getenv('TMT_PLUGIN_REPORT_REPORTPORTAL_PROJECT'))
        if not project:
            raise tmt.utils.ReportError("No ReportPortal project provided.")

        token = self.get("token", os.getenv('TMT_PLUGIN_REPORT_REPORTPORTAL_TOKEN'))
        if not token:
            raise tmt.utils.ReportError("No ReportPortal token provided.")

        url = f"{endpoint}/api/{self.DEFAULT_API_VERSION}/{project}"
        headers = {
            "Authorization": "bearer " + token,
            "accept": "*/*",
            "Content-Type": "application/json"}

        launch_time = self.step.plan.execute.results()[0].starttime
        merge_bool = self.get("merge")
        rerun_bool = False
        create_launch = True
        launch_uuid = ""
        suite_uuid = ""
        launch_url = ""
        launch_name = ""

        envar_pattern = self.get("exclude-variables") or "$^"
        extra_attributes = self.get("attributes")
        launch_attributes = [
            {'key': attribute.split(':', 2)[0], 'value': attribute.split(':', 2)[1]}
            for attribute in extra_attributes] or []

        attributes = [
            {'key': key, 'value': value[0]}
            for key, value in self.step.plan._fmf_context.items()]
        for attr in launch_attributes:
            if attr not in attributes:
                attributes.append(attr)

        # Communication with RP instance
        with tmt.utils.retry_session() as session:

            stored_launch_uuid = self.get("uuid") or self.step.plan.my_run.rp_uuid
            if merge_bool and stored_launch_uuid:
                create_launch = False
                launch_uuid = stored_launch_uuid
                response = session.get(
                    url=f"{url}/launch/uuid/{launch_uuid}",
                    headers=headers)
                self.handle_response(response)
                launch_name = yaml_to_dict(response.text).get("name")
                self.verbose("launch", launch_name, color="yellow")
                launch_id = yaml_to_dict(response.text).get("id")
                launch_url = f"{endpoint}/ui/#{project}/launches/all/{launch_id}"
            else:
                # create_launch = True
                launch_name = self.get("launch", os.getenv(
                    'TMT_PLUGIN_REPORT_REPORTPORTAL_LAUNCH')) or self.step.plan.name

                # Create a launch
                self.info("launch", launch_name, color="cyan")
                response = session.post(
                    url=f"{url}/launch",
                    headers=headers,
                    json={
                        "name": launch_name,
                        "description": "" if merge_bool else self.step.plan.summary,
                        "attributes": launch_attributes if merge_bool else attributes,
                        "startTime": launch_time,
                        "rerun": rerun_bool})
                self.handle_response(response)
                launch_uuid = yaml_to_dict(response.text).get("id")
                assert launch_uuid is not None
                if merge_bool:
                    self.step.plan.my_run.rp_uuid = launch_uuid

            self.verbose("uuid", launch_uuid, "yellow", shift=1)
            self.data.launch_uuid = launch_uuid

            if merge_bool:
                # Create a suite
                suite_name = self.step.plan.name
                self.info("suite", suite_name, color="cyan")
                response = session.post(
                    url=f"{url}/item",
                    headers=headers,
                    json={
                        "name": suite_name,
                        "description": self.step.plan.summary,
                        "attributes": attributes,
                        "startTime": launch_time,
                        "launchUuid": launch_uuid,
                        "type": "suite"})
                self.handle_response(response)
                suite_uuid = yaml_to_dict(response.text).get("id")
                assert suite_uuid is not None
                self.verbose("uuid", suite_uuid, "yellow", shift=1)

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
                    url=f"{url}/item{f'/{suite_uuid}' if merge_bool else ''}",
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
                            "time": result.end_time})
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

            if merge_bool:
                # Finish the test suite
                response = session.put(
                    url=f"{url}/item/{suite_uuid}",
                    headers=headers,
                    json={
                        "launchUuid": launch_uuid,
                        "endTime": launch_time})
                self.handle_response(response)

            if create_launch:
                # Finish the launch
                response = session.put(
                    url=f"{url}/launch/{launch_uuid}/finish",
                    headers=headers,
                    json={"endTime": launch_time})
                self.handle_response(response)
                launch_url = yaml_to_dict(response.text).get("link")

            self.info("url", launch_url, "magenta")
            self.data.launch_url = launch_url
