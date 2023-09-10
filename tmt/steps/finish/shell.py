import dataclasses
from typing import Any, Dict, List, Optional, cast

import fmf

import tmt
import tmt.steps
import tmt.steps.finish
import tmt.utils
from tmt.steps.provision import Guest
from tmt.utils import ShellScript


@dataclasses.dataclass
class FinishShellData(tmt.steps.finish.FinishStepData):
    script: List[ShellScript] = tmt.utils.field(
        default_factory=list,
        option=('-s', '--script'),
        multiple=True,
        metavar='SCRIPT',
        help='Shell script to be executed. Can be used multiple times.',
        normalize=tmt.utils.normalize_shell_script_list,
        serialize=lambda scripts: [str(script) for script in scripts],
        unserialize=lambda serialized: [ShellScript(script) for script in serialized]
        )

    # TODO: well, our brave new field() machinery should be able to deal with all of this...
    # ignore[override] & cast: two base classes define to_spec(), with conflicting
    # formal types.
    def to_spec(self) -> Dict[str, Any]:  # type: ignore[override]
        data = cast(Dict[str, Any], super().to_spec())
        data['script'] = [str(script) for script in self.script]

        return data


@tmt.steps.provides_method('shell')
class FinishShell(tmt.steps.finish.FinishPlugin):
    """
    Perform finishing tasks using shell (bash) scripts

    Example config:

    finish:
        how: shell
        script:
            - upload-logs.sh || true
            - rm -rf /tmp/temporary-files

    Use the 'order' attribute to select in which order finishing tasks
    should happen if there are multiple configs. Default order is '50'.
    """

    _data_class = FinishShellData

    def go(
            self,
            *,
            guest: 'Guest',
            environment: Optional[tmt.utils.EnvironmentType] = None,
            logger: tmt.log.Logger) -> None:
        """ Perform finishing tasks on given guest """
        super().go(guest=guest, environment=environment, logger=logger)

        # Give a short summary
        scripts: List[tmt.utils.ShellScript] = self.get('script')
        overview = fmf.utils.listed(scripts, 'script')
        self.info('overview', f'{overview} found', 'green')

        # Execute each script on the guest
        for script in scripts:
            self.verbose('script', script, 'green')
            script_with_options = tmt.utils.ShellScript(f'{tmt.utils.SHELL_OPTIONS}; {script}')
            guest.execute(script_with_options, cwd=self.step.plan.worktree)
