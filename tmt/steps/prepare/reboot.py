import dataclasses
import os
from typing import Any, List, Optional, cast

import click
import pkg_resources

import tmt
import tmt.steps.prepare
import tmt.utils
from tmt.steps.execute import TMT_REBOOT_SCRIPT
from tmt.steps.provision import Guest
from tmt.steps.rebootable import RebootCommon

# Scripts source directory
SCRIPTS_SRC_DIR = pkg_resources.resource_filename(
    'tmt', 'steps/execute/scripts')

SCRIPTS = (
    TMT_REBOOT_SCRIPT,
    )

# TODO: remove `ignore` with follow-imports enablement


@dataclasses.dataclass
class PrepareRebootData(tmt.steps.prepare.PrepareStepData):
    script: List[str] = dataclasses.field(default_factory=list)

    _normalize_script = tmt.utils.NormalizeKeysMixin._normalize_string_list


@tmt.steps.provides_method('reboot')
class PrepareReboot(
        tmt.steps.prepare.PreparePlugin,
        RebootCommon
        ):
    """
    Reboot system via provided script
    Example config:
    prepare:
        how: reboot
        script: ./reboot-script
    """

    _data_class = PrepareRebootData  # type: ignore[assignment]

    @classmethod
    def options(cls, how: Optional[str] = None) -> Any:
        """ Prepare command line options """
        return cast(List[tmt.options.ClickOptionDecoratorType], [
            click.option(
                '-s', '--script', metavar='NAME', multiple=True,
                help='Set path to the reboot script.')
            ]) + super().options(how)

    def go(self, guest: Guest) -> None:
        """ Prepare the guests """
        super().go(guest)

        # Prepare scripts, except localhost guest
        self.scripts = SCRIPTS
        self.debug(f"Preparing reboot script: {self.scripts}")
        if not guest.localhost:
            self.prepare_scripts(guest)

        # Define and set reboot count
        if not hasattr(self, "_reboot_count"):
            self._reboot_count = 0

        # Set all supported reboot variables
        self.step.plan._environment["TMT_REBOOT_REQUEST"] = os.path.join(
            self.step.plan.data_directory,
            TMT_REBOOT_SCRIPT.created_file)
        for reboot_variable in TMT_REBOOT_SCRIPT.related_variables:
            self.step.plan._environment[reboot_variable] = str(self._reboot_count)

        # Execute script for reboot
        script = self.get("script")
        try:
            guest.execute(script, cwd=self.step.plan.worktree)
        except tmt.utils.RunError as e:
            self.debug(f"Reboot script was executed: {e}")
            if not guest.execute("test -f $TMT_REBOOT_REQUEST", cwd=self.step.plan.worktree):
                raise tmt.utils.GeneralError("Reboot request file wasn't generated")
        guest.pull(source=self.step.plan.data_directory)

        # Handle reboot
        self.debug(f"Reboot request file: {self._reboot_request_path(None)}")
        if self._will_reboot(None):
            # Output before the reboot
            self.debug("Reboot is in progress")
            if self._handle_reboot(None, guest):
                self.debug("Reboot succeeded")
