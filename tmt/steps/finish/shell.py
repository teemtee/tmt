import dataclasses
from typing import Any, Optional, cast

import tmt
import tmt.steps
import tmt.steps.finish
import tmt.utils
from tmt.result import PhaseResult
from tmt.steps.prepare.shell import go
from tmt.steps.provision import Guest
from tmt.utils import ShellScript, field

FINISH_WRAPPER_FILENAME = 'tmt-finish-wrapper.sh'


@dataclasses.dataclass
class FinishShellData(tmt.steps.finish.FinishStepData):
    script: list[ShellScript] = field(
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
    def to_spec(self) -> dict[str, Any]:  # type: ignore[override]
        data = cast(dict[str, Any], super().to_spec())
        data['script'] = [str(script) for script in self.script]

        return data


@tmt.steps.provides_method('shell')
class FinishShell(tmt.steps.finish.FinishPlugin[FinishShellData]):
    """
    Perform finishing tasks using shell (bash) scripts

    Example config:

    .. code-block:: yaml

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
            environment: Optional[tmt.utils.Environment] = None,
            logger: tmt.log.Logger) -> list[PhaseResult]:
        """ Perform finishing tasks on given guest """

        return [
            *super().go(guest=guest, environment=environment, logger=logger),
            *go(
                self,
                guest=guest,
                environment=environment,
                wrapper_basename=FINISH_WRAPPER_FILENAME,
                logger=logger)]
