from pathlib import Path
from time import time

from reportportal_client import ReportPortalService


def timestamp():
    return str(int(time() * 1000))


endpoint = "https://reportportal-rhel.apps.ocp-c1.prod.psi.redhat.com"
project = "<project name>"
token = "<UUID Access Token>"   # RP > User Profile > Access Token
service = ReportPortalService(endpoint=endpoint, project=project, token=token)
launch_name = "Test Launch"

# create launch and its items
launch_id = service.start_launch(name=launch_name,
                                 start_time=timestamp(),
                                 rerun=False,       # eg.: True
                                 rerunOf=None,  # "3070a17f-1... <launch_id> ...477e972"
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
                                  test_case_id="xx123",     # use case?
                                  code_ref="12345xxx",      # use case?
                                  parameters={"key1": "val1", "key2": "val2"},  # use case?
                                  attributes={"attr1": "val1", "attr2": "val2"},
                                  description="Some Test Case")
print("URL:         " + service.get_launch_ui_url())
print("LAUNCH UIID: " + str(service.get_launch_ui_id()))
print("LAUNCH ID:   " + launch_id)
print("SUITE ID:    " + suite_id)
print("TEST ID:     " + test_id)

# report the logs
service.log(item_id=test_id, time=timestamp(), message="Hello World!", level="INFO")
log = "/var/tmp/tmt/run-341/plans/default/execute/data/test/output.txt"
service.log(item_id=test_id, time=timestamp(), message=Path(log).read_text(), level="INFO")
service.log(item_id=test_id, time=timestamp(), message="Adding log attachment", level="INFO",
            attachment={"name": "output.txt",
                        "data": Path(log).read_text(),
                        "mime": "text/plain"})          # usecase?

# finnish reporting
service.finish_test_item(item_id=test_id, end_time=timestamp(), status="PASSED")
service.finish_test_item(item_id=suite_id, end_time=timestamp(), status="PASSED")
service.finish_launch(end_time=timestamp())
service.terminate()
