import dataclasses
import os
import re
from time import time
from typing import Optional

import requests

import tmt.log
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
             "Recommended to use with '--launch' and '--launch-description' options."
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
        help="Pass the suite ID for an additional test upload to a suite "
             "within an existing launch. ID can be found in the suite URL.")
    launch_rerun: bool = field(
        option="--launch-rerun",
        default=False,
        is_flag=True,
        help="Rerun the last launch based on its name and unique test paths to create Retry item"
             "with a new version per each test. Supported in 'suite-per-plan' structure only.")
    defect_type: Optional[str] = field(
        option="--defect-type",
        metavar="DEFECT_NAME",
        default=None,
        help="Pass the defect type to be used for failed test, which is defined in the project"
             " (e.g. 'Idle'). 'To Investigate' is used by default.")
    exclude_variables: str = field(
        option="--exclude-variables",
        metavar="PATTERN",
        default="^TMT_.*",
        help="Regular expression for excluding environment variables "
             "from reporting to ReportPortal ('^TMT_.*' used by default)."
             "Parameters in ReportPortal get filtered out by the pattern"
             "to prevent overloading and to preserve the history aggregation"
             "for ReportPortal item if tmt id is not provided")

    launch_url: Optional[str] = None
    launch_uuid: Optional[str] = None
    suite_uuid: Optional[str] = None
    test_uuids: dict[int, str] = field(
        default_factory=dict
        )


@tmt.steps.provides_method("reportportal")
class ReportReportPortal(tmt.steps.report.ReportPlugin[ReportReportPortalData]):
    """
    Report test results to a ReportPortal instance via API.

    For communication with Report Portal API is neccessary to provide
    following options:

    * token for authentication
    * URL of the ReportPortal instance
    * project name
    * optional API version to override the default one (v1)
    * optional launch name to override the deafult name based on the tmt
      plan name

    In addition to command line options it's possible to use environment
    variables:

    .. code-block:: bash

        export TMT_PLUGIN_REPORT_REPORTPORTAL_${MY_OPTION}=${MY_VALUE}

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

    Where the context and environment sections must be filled with
    corresponding data in order to report context as attributes
    (arch, component, distro, trigger, compose, etc.) and
    environment variables as parameters in the Item Details.

    Other reported fmf data are summary, id, web link and contact per
    test.

    There are supported two ways of mapping plans into ReportPortal

    * launch-per-plan (default) with reported structure 'launch > test',
      resulting in one or more launches.
    * suite-per-plan with reported structure 'launch > suite > test'
      resulting in one launch only, and one or more suites within.
      (Recommended to define launch-name and launch-description in
      addition)
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

        self.debug("Response code from the endpoint", response.status_code)
        self.debug("Message from the endpoint", response.text)

    def check_options(self) -> None:
        """
        Write warning if there might be caused an unexpected behaviour by the option combinations
        """
        # TODO: Update restriction of forbiden option combinations based on feedback.

        if self.data.launch_per_plan and self.data.suite_per_plan:
            raise tmt.utils.ReportError(
                "The options '--launch-per-plan' and '--suite-per-plan' are mutually exclusive. "
                "Choose one of them only.")

        if self.data.launch_rerun and (self.data.upload_to_launch or self.data.upload_to_suite):
            self.warn("Unexpected option combination: "
                      "'--launch-rerun' is ignored when uploading additional tests.")

        if not self.data.suite_per_plan and self.data.launch_rerun:
            self.warn("Unexpected option combination: '--launch-rerun' "
                      "may cause an unexpected behaviour with launch-per-plan structure")

    def time(self) -> str:
        return str(int(time() * 1000))

    def get_headers(self) -> dict[str, str]:
        return {"Authorization": "bearer " + str(self.data.token),
                "accept": "*/*",
                "Content-Type": "application/json"}

    def get_url(self) -> str:
        api_version = os.getenv(
            'TMT_PLUGIN_REPORT_REPORTPORTAL_API_VERSION') or self.DEFAULT_API_VERSION
        return f"{self.data.url}/api/{api_version}/{self.data.project}"

    def construct_launch_attributes(self, suite_per_plan: bool,
                                    attributes: list[dict[str, str]]) -> list[dict[str, str]]:
        if not suite_per_plan or not self.step.plan.my_run:
            return attributes.copy()

        # Get common attributes across the plans
        merged_plans = [{key: value[0] for key, value in plan._fmf_context.items()}
                        for plan in self.step.plan.my_run.plans]
        result_dict = merged_plans[0]
        for current_plan in merged_plans[1:]:
            tmp_dict = {}
            for key, value in current_plan.items():
                if key in result_dict and result_dict[key] == value:
                    tmp_dict[key] = value
            result_dict = tmp_dict
        return [{'key': key, 'value': value} for key, value in result_dict.items()]

    def get_defect_type_locator(self, session: requests.Session,
                                defect_type: Optional[str]) -> str:
        if not defect_type:
            return "ti001"

        response = self.get_rp_api(session, "settings")
        defect_types = yaml_to_dict(response.text).get("subTypes")
        if not defect_types:
            return "ti001"
        dt_tmp = [dt['locator'] for dt in defect_types['TO_INVESTIGATE']
                  if dt['longName'].lower() == defect_type.lower()]
        dt_locator = dt_tmp[0] if dt_tmp else None
        if not dt_locator:
            raise tmt.utils.ReportError(f"Defect type '{defect_type}' "
                                        "is not be defined in the project {self.data.project}")
        self.verbose("defect_typ", defect_type, "yellow")
        return str(dt_locator)

    def get_rp_api(self, session: requests.Session, data_path: str) -> requests.Response:
        response = session.get(url=f"{self.get_url()}/{data_path}",
                               headers=self.get_headers())
        self.handle_response(response)
        return response

    def go(self) -> None:
        """
        Report test results to the endpoint

        Create a ReportPortal launch and its test items,
        fill it with all parts needed and report the logs.
        """

        super().go()

        if not self.data.url:
            raise tmt.utils.ReportError("No ReportPortal endpoint url provided.")
        self.data.url = self.data.url.rstrip("/")

        if not self.data.project:
            raise tmt.utils.ReportError("No ReportPortal project provided.")

        if not self.data.token:
            raise tmt.utils.ReportError("No ReportPortal token provided.")

        if not self.step.plan.my_run:
            raise tmt.utils.ReportError("No run data available.")

        self.check_options()

        launch_time = self.time()

        # Support for idle tests
        executed = bool(self.step.plan.execute.results())
        if executed:
            launch_time = self.step.plan.execute.results()[0].start_time or self.time()

        # Create launch, suites (if "--suite_per_plan") and tests;
        # or report to existing launch/suite if its id is given
        suite_per_plan = self.data.suite_per_plan
        launch_per_plan = self.data.launch_per_plan
        if not launch_per_plan and not suite_per_plan:
            launch_per_plan = True      # by default

        suite_id = self.data.upload_to_suite
        launch_id = self.data.upload_to_launch

        suite_uuid = self.data.suite_uuid
        launch_uuid = self.data.launch_uuid
        additional_upload = suite_id or launch_id or launch_uuid
        is_the_first_plan = self.step.plan == self.step.plan.my_run.plans[0]
        if not launch_uuid and suite_per_plan and not is_the_first_plan:
            rp_phases = list(self.step.plan.my_run.plans[0].report.phases(ReportReportPortal))
            if rp_phases:
                launch_uuid = rp_phases[0].data.launch_uuid

        create_test = not self.data.test_uuids
        create_suite = suite_per_plan and not (suite_uuid or suite_id)
        create_launch = not (launch_uuid or launch_id or suite_uuid or suite_id)

        launch_name = self.data.launch or self.step.plan.name
        suite_name = ""
        launch_url = ""

        launch_rerun = self.data.launch_rerun
        envar_pattern = self.data.exclude_variables or "$^"
        defect_type = self.data.defect_type

        attributes = [
            {'key': key, 'value': value[0]}
            for key, value in self.step.plan._fmf_context.items()]

        launch_attributes = self.construct_launch_attributes(suite_per_plan, attributes)

        launch_description = self.data.launch_description or self.step.plan.summary

        # Communication with RP instance
        with tmt.utils.retry_session() as session:

            if create_launch:

                # Create a launch
                self.info("launch", launch_name, color="cyan")
                response = session.post(
                    url=f"{self.get_url()}/launch",
                    headers=self.get_headers(),
                    json={"name": launch_name,
                          "description": launch_description,
                          "attributes": launch_attributes,
                          "startTime": launch_time,
                          "rerun": launch_rerun})
                self.handle_response(response)
                launch_uuid = yaml_to_dict(response.text).get("id")

            else:
                # Get the launch_uuid or info to log
                if suite_id:
                    response = self.get_rp_api(session, f"item/{suite_id}")
                    suite_uuid = yaml_to_dict(response.text).get("uuid")
                    suite_name = str(yaml_to_dict(response.text).get("name"))
                    launch_id = yaml_to_dict(response.text).get("launchId")

                if launch_id:
                    response = self.get_rp_api(session, f"launch/{launch_id}")
                    launch_uuid = yaml_to_dict(response.text).get("uuid")

            if launch_uuid and not launch_id:
                response = self.get_rp_api(session, f"launch/uuid/{launch_uuid}")
                launch_id = yaml_to_dict(response.text).get("id")

            # Print the launch info
            if not create_launch:
                launch_name = yaml_to_dict(response.text).get("name") or ""
                self.verbose("launch", launch_name, color="green")
                self.verbose("id", launch_id, "yellow", shift=1)

            assert launch_uuid is not None
            self.verbose("uuid", launch_uuid, "yellow", shift=1)
            self.data.launch_uuid = launch_uuid

            launch_url = f"{self.data.url}/ui/#{self.data.project}/launches/all/{launch_id}"

            if create_suite:
                # Create a suite
                suite_name = self.step.plan.name
                self.info("suite", suite_name, color="cyan")
                response = session.post(
                    url=f"{self.get_url()}/item",
                    headers=self.get_headers(),
                    json={"name": suite_name,
                          "description": self.step.plan.summary,
                          "attributes": attributes,
                          "startTime": launch_time,
                          "launchUuid": launch_uuid,
                          "type": "suite"})
                self.handle_response(response)
                suite_uuid = yaml_to_dict(response.text).get("id")
                assert suite_uuid is not None

            elif suite_name:
                self.info("suite", suite_name, color="green")
                self.verbose("id", suite_id, "yellow", shift=1)

            if suite_uuid:
                self.verbose("uuid", suite_uuid, "yellow", shift=1)
                self.data.suite_uuid = suite_uuid

            # For each test
            for test in self.step.plan.discover.tests():
                test_time = self.time()
                if executed:
                    result = next((result for result in self.step.plan.execute.results()
                                   if test.serial_number == result.serial_number), None)
                    if result:
                        test_time = result.start_time or self.time()
                # TODO: for happz, connect Test to Result if possible
                #       (but now it is probably too hackish to be fixed)

                item_attributes = attributes.copy()
                if test.contact:
                    item_attributes.append({"key": "contact", "value": test.contact[0]})
                env_vars = [
                    {'key': key, 'value': value}
                    for key, value in test.environment.items()
                    if not re.search(envar_pattern, key)]

                if create_test:
                    # Create a test item
                    self.info("test", test.name, color="cyan")
                    response = session.post(
                        url=f"{self.get_url()}/item{f'/{suite_uuid}' if suite_uuid else ''}",
                        headers=self.get_headers(),
                        json={"name": test.name,
                              "description": test.summary,
                              "attributes": item_attributes,
                              "parameters": env_vars,
                              "codeRef": test.web_link() or None,
                              "launchUuid": launch_uuid,
                              "type": "step",
                              "testCaseId": test.id or None,
                              "startTime": test_time})
                    self.handle_response(response)
                    item_uuid = yaml_to_dict(response.text).get("id")
                    assert item_uuid is not None
                    self.verbose("uuid", item_uuid, "yellow", shift=1)
                    self.data.test_uuids[test.serial_number] = item_uuid
                else:
                    item_uuid = self.data.test_uuids[test.serial_number]

                # Support for idle tests
                status = "SKIPPED"
                if executed and result:
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
                            url=f"{self.get_url()}/log/entry",
                            headers=self.get_headers(),
                            json={"message": log,
                                  "itemUuid": item_uuid,
                                  "launchUuid": launch_uuid,
                                  "level": level,
                                  "time": result.end_time})
                        self.handle_response(response)

                        # Write out failures
                        if index == 0 and status == "FAILED":
                            message = result.failures(log)
                            response = session.post(
                                url=f"{self.get_url()}/log/entry",
                                headers=self.get_headers(),
                                json={"message": message,
                                      "itemUuid": item_uuid,
                                      "launchUuid": launch_uuid,
                                      "level": "ERROR",
                                      "time": result.end_time})
                            self.handle_response(response)

                    # TODO: Add tmt files as attachments

                    test_time = result.end_time or self.time()

                # Finish the test item
                response = session.put(
                    url=f"{self.get_url()}/item/{item_uuid}",
                    headers=self.get_headers(),
                    json={
                        "launchUuid": launch_uuid,
                        "endTime": test_time,
                        "status": status,
                        "issue": {
                            "issueType": self.get_defect_type_locator(session, defect_type)}})
                self.handle_response(response)
                launch_time = test_time

                # TODO: Resolve the problem with reporting original defect type (idle)
                #           after additional report of results
                #       Temporary solution idea:
                #               if again_additional_tests and status failed,
                #               get test_id, report passed and then again failed

            if create_suite:
                # Finish the test suite
                response = session.put(
                    url=f"{self.get_url()}/item{f'/{suite_uuid}' if suite_uuid else ''}",
                    headers=self.get_headers(),
                    json={
                        "launchUuid": launch_uuid,
                        "endTime": launch_time})
                self.handle_response(response)

            is_the_last_plan = self.step.plan == self.step.plan.my_run.plans[-1]

            if ((launch_per_plan or (suite_per_plan and is_the_last_plan))
                    and not additional_upload):
                # Finish the launch
                response = session.put(
                    url=f"{self.get_url()}/launch/{launch_uuid}/finish",
                    headers=self.get_headers(),
                    json={"endTime": launch_time})
                self.handle_response(response)
                launch_url = str(yaml_to_dict(response.text).get("link"))

            assert launch_url is not None
            self.info("url", launch_url, "magenta")
            self.data.launch_url = launch_url
