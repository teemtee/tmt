import json
import os

import tmt
import tmt.options
import tmt.steps
import tmt.steps.execute
import tmt.utils
from tmt.base import Test
from tmt.steps import Step, StepData
from tmt.steps.execute import TMT_REBOOT_SCRIPT, ExecutePlugin
from tmt.steps.provision import Guest


class RebootCommon(ExecutePlugin):

    def __init__(
            self,
            step: Step,
            data: StepData,
            workdir: tmt.utils.WorkdirArgumentType = None) -> None:
        super().__init__(step, data, workdir)
        self._reboot_count = 0

    def _will_reboot(self, test: Test) -> bool:
        """ True if reboot is requested """
        return os.path.exists(self._reboot_request_path(test))

    def _reboot_request_path(self, test: Test) -> str:
        """ Return reboot_request """
        # 'test' is None if reboot is requested from prepare/finish step
        if test is not None:
            reboot_request_path = os.path.join(
                self.data_path(test, full=True),
                tmt.steps.execute.TEST_DATA,
                TMT_REBOOT_SCRIPT.created_file)
        else:
            reboot_request_path = os.path.join(
                self.step.plan.data_directory,
                TMT_REBOOT_SCRIPT.created_file)
        return reboot_request_path

    def _handle_reboot(self, test: Test, guest: Guest) -> bool:
        """
        Reboot the guest if the test requested it.

        Check for presence of a file signalling reboot request
        and orchestrate the reboot if it was requested. Also increment
        REBOOTCOUNT variable, reset it to 0 if no reboot was requested
        (going forward to the next test). Return whether reboot was done.
        """
        # 'test' is None if reboot is requested from prepare/finish step
        if self._will_reboot(test):
            reboot_request_path = self._reboot_request_path(test)
            if test is not None:
                test._reboot_count += 1
                self.debug(f"Reboot during test '{test}' "
                           f"with reboot count {test._reboot_count}.")
                data = os.path.join(
                    self.data_path(test, full=True),
                    tmt.steps.execute.TEST_DATA)
            else:
                self._reboot_count += 1
                self.debug(f"Reboot during prepare/finish step "
                           f"with reboot count {self._reboot_count}.")
            with open(reboot_request_path, 'r') as reboot_file:
                reboot_data = json.loads(reboot_file.read())
                data = os.path.join(self.step.plan.data_directory)
            reboot_command = reboot_data.get('command')
            try:
                timeout = int(reboot_data.get('timeout'))
            except ValueError:
                timeout = None
            # Reset the file
            os.remove(reboot_request_path)
            guest.push(data)
            rebooted = False
            try:
                rebooted = guest.reboot(command=reboot_command, timeout=timeout)
            except tmt.utils.RunError:
                self.fail(
                    f"Failed to reboot guest using the "
                    f"custom command '{reboot_command}'.")
                raise
            except tmt.utils.ProvisionError:
                self.warn(
                    "Guest does not support soft reboot, "
                    "trying hard reboot.")
                rebooted = guest.reboot(hard=True, timeout=timeout)
            if not rebooted:
                raise tmt.utils.RebootTimeoutError("Reboot timed out.")
            return True
        return False
