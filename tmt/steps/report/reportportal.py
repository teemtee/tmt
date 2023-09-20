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
        default=os.getenv('TMT_PLUGIN_REPORT_REPORTPORTAL_URL'),
        help="The URL of the ReportPortal instance where the data should be sent to.")
    token: Optional[str] = field(
        option="--token",
        metavar="TOKEN",
        default=os.getenv('TMT_PLUGIN_REPORT_REPORTPORTAL_TOKEN'),
        help="The token to use for upload to the ReportPortal instance (from the user profile).")
    project: Optional[str] = field(
        option="--project",
        metavar="PROJECT_NAME",
        default=os.getenv('TMT_PLUGIN_REPORT_REPORTPORTAL_PROJECT'),
        help="Name of the project into which the results should be uploaded.")
    launch: Optional[str] = field(
        option="--launch",
        metavar="LAUNCH_NAME",
        default=os.getenv('TMT_PLUGIN_REPORT_REPORTPORTAL_LAUNCH'),
        help="The launch name (name of plan per launch is used by default).")
    launch_description: Optional[str] = field(
        option="--launch-description",
        metavar="LAUNCH_DESCRIPTION",
        default=os.getenv('TMT_PLUGIN_REPORT_REPORTPORTAL_LAUNCH_DESCRIPTION'),
        help="Pass the description for ReportPortal launch, especially with '--suite-per-plan' "
             "option (Otherwise Summary from plan fmf data per each launch is used by default).")
    ## launch_attributes: List[str] = field(
    ## default_factory=list,
    ## multiple=True,
    ## normalize=tmt.utils.normalize_string_list,
    ## option="--launch-attributes",
    ## metavar="KEY:VALUE",
    ## help="Additional attributes to be reported to ReportPortal,"
    ## "especially launch attributes for merge option.")
    launch_per_plan: bool = field(
        option="--launch-per-plan",
        default=False,
        is_flag=True,
        help="Mapping launch per plan, creating one or more launches with no suite structure.")
    suite_per_plan: bool = field(
        option="--suite-per-plan",
        default=False,
        is_flag=True,
        help="Mapping suite per plan, creating one launch and continous uploading suites into it. "
             "Can be used with '--upload-to-launch' option to avoid creating a new launch.")
    upload_to_launch: Optional[str] = field(
        option="--upload-to-launch",
        metavar="LAUNCH_ID",
        default=None,
        help="Pass the launch ID for an additional test/suite upload to an existing launch. "
             "ID can be found in the launch URL.")
    upload_to_suite: Optional[str] = field(
        option="--upload-to-suite",
        metavar="LAUNCH_SUITE",
        default=None,
        help="Pass the suite ID for an additional test upload to an existing launch. "
             "ID can be found in the suite URL.")
    launch_rerun: bool = field(
        option="--launch-rerun",
        default=False,
        is_flag=True,
        help="Rerun the launch and create Retry version per each test. Note that mapping is "
             "based on unique suite/test names and works with '--suite-per-plan' option only.")
    defect_type: Optional[str] = field(
        option="--defect-type",
        metavar="DEFECT_NAME",
        default=None,
        help="Pass the defect type to be used for failed test "
             "('To Investigate' is used by default).")
    exclude_variables: str = field(
        option="--exclude-variables",
        metavar="PATTERN",
        default="^TMT_.*",
        help="Regular expression for excluding environment variables "
             "from reporting to ReportPortal ('^TMT_.*' used by default).")
    launch_url: str = ""
    launch_uuid: str = ""
    suite_uuid: str = ""
    test_uuids: List[str] = []


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
    # TODO: Finish the description ^ with the new options

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

        endpoint = self.get("url")
        if not endpoint:
            raise tmt.utils.ReportError("No ReportPortal endpoint url provided.")
        endpoint = endpoint.rstrip("/")

        project = self.get("project")
        if not project:
            raise tmt.utils.ReportError("No ReportPortal project provided.")

        token = self.get("token")
        if not token:
            raise tmt.utils.ReportError("No ReportPortal token provided.")

        url = f"{endpoint}/api/{self.DEFAULT_API_VERSION}/{project}"
        headers = {
            "Authorization": "bearer " + token,
            "accept": "*/*",
            "Content-Type": "application/json"}

        launch_time = self.step.plan.execute.results()[0].starttime



        # Create launch, suites (if "--suite_per_plan") and tests;
        # or report to existing launch/suite if its id is given

        # TODO: 
        #       * upload_to_launch: change id to uuid
        #       * launch_uuid: add the param per plan, and do the matching when uploading
        #       * launch_uuid: add the param per plan, and do the matching when uploading

        launch_uuid = self.get("launch_uuid") or self.step.plan.my_run.rp_uuid
        suite_uuid =  self.get("suite_uuid")

        launch_id = self.get("upload_to_launch")
        suite_id = self.get("upload_to_suite")

        suite_per_plan = self.get("suite_per_plan")
        launch_per_plan = self.get("launch_per_plan")
        if not launch_per_plan and not suite_per_plan:
            launch_per_plan = True                  # default
        elif launch_per_plan and suite_per_plan:
            raise tmt.utils.ReportError("The options '--launch-per-plan' and "
            "'--suite-per-plan' are mutually exclusive. Choose one of them only.")
        
        create_launch = not (launch_uuid or launch_id) and not suite_uuid
        create_suite = suite_per_plan and not (suite_uuid or suite_id)

        launch_url = ""
        launch_name = self.get("launch") or self.step.plan.name

        launch_rerun = self.get("launch_rerun")
        envar_pattern = self.get("exclude-variables") or "$^"
        defect_type = self.get("defect_type")

        attributes = [
            {'key': key, 'value': value[0]}
            for key, value in self.step.plan._fmf_context.items()]

        if suite_per_plan:
            launch_attributes = ""
            # TODO: get common attributes from all plans
        else:
            launch_attributes = attributes.copy()

        launch_description = self.get("launch_description") or self.step.plan.summary

        # Communication with RP instance
        with tmt.utils.retry_session() as session:

            # get defect type locator
            dt_locator = None
            if defect_type:
                response = session.get(url=f"{url}/settings", headers=headers)
                self.handle_response(response)
                defect_types = yaml_to_dict(response.text).get("subTypes")
                dt_tmp = [dt['locator']
                        for dt in defect_types['TO_INVESTIGATE'] if dt['longName'] == defect_type]
                dt_locator = dt_tmp[0] if dt_tmp else None
                # TODO: check the case when the given defect type is not defined

            if create_launch:

                # Create a launch
                self.info("launch", launch_name, color="cyan")
                response = session.post(
                           url=f"{url}/launch",
                           headers=headers,
                           json={ "name": launch_name,
                                  "description": launch_description,
                                  "attributes": launch_attributes,
                                  "startTime": launch_time,
                                  "rerun": launch_rerun})
                self.handle_response(response)
                launch_uuid = yaml_to_dict(response.text).get("id")
                if suite_per_plan:
                    self.step.plan.my_run.rp_uuid = launch_uuid
            else:
                # Get the launch_uuid or info to log

                # TODO:     get launch_uuid from launch_id/suite_id
                #   if launch_id:
                #       response = ...
                #   elif suite_ide:
                #       response = ...

                response = session.get(
                    url=f"{url}/launch/uuid/{launch_uuid}",
                    headers=headers)
                self.handle_response(response)
                launch_name = yaml_to_dict(response.text).get("name")
                self.verbose("launch", launch_name, color="yellow")
                launch_id = yaml_to_dict(response.text).get("id")
                launch_url = f"{endpoint}/ui/#{project}/launches/all/{launch_id}"

            assert launch_uuid is not None
            self.verbose("uuid", launch_uuid, "yellow", shift=1)
            self.data.launch_uuid = launch_uuid

            if create_suite:
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
                    url=f"{url}/item{f'/{suite_uuid}' if suite_uuid else ''}",
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

                    # TODO: Add tmt files as attachments

                # Finish the test item
                response = session.put(
                    url=f"{url}/item/{item_uuid}",
                    headers=headers,
                    json={
                        "launchUuid": launch_uuid,
                        "endTime": result.endtime,
                        "status": status,
                        "issue": {"issueType": dt_locator or "ti001"}})
                self.handle_response(response)
                launch_time = result.endtime

            if create_suite:
                # Finish the test suite
                response = session.put(
                    url=f"{url}/item/{suite_uuid}",
                    headers=headers,
                    json={
                        "launchUuid": launch_uuid,
                        "endTime": launch_time})
                self.handle_response(response)

            # TODO: Get if it is the last plan
            #
            #   if create_launch and (not suite_per_plan or
            #   (suite_per_plan and this-is-the-last-plan)):

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
