import dataclasses
from typing import Any, Optional, cast

import fmf

import tmt
import tmt.steps
import tmt.steps.finish
import tmt.utils
from tmt.result import PhaseResult
from tmt.steps import safe_filename
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
        results = super().go(guest=guest, environment=environment, logger=logger)

        # Give a short summary
        overview = fmf.utils.listed(self.data.script, 'script')
        self.info('overview', f'{overview} found', 'green')

        workdir = self.step.plan.worktree
        assert workdir is not None  # narrow type

        finish_wrapper_filename = safe_filename(FINISH_WRAPPER_FILENAME, self, guest)
        finish_wrapper_path = workdir / finish_wrapper_filename

        logger.debug('finish wrapper', finish_wrapper_path, level=3)

        # Execute each script on the guest
        for script in self.data.script:
            self.verbose('script', script, 'green')
            script_with_options = tmt.utils.ShellScript(f'{tmt.utils.SHELL_OPTIONS}; {script}')
            self.write(finish_wrapper_path, str(script_with_options), 'w')
            if not self.is_dry_run:
                finish_wrapper_path.chmod(0o755)
            guest.push(
                source=finish_wrapper_path,
                destination=finish_wrapper_path,
                options=["-s", "-p", "--chmod=755"])
            command: ShellScript
            if guest.become and not guest.facts.is_superuser:
                command = tmt.utils.ShellScript(f'sudo -E {finish_wrapper_path}')
            else:
                command = tmt.utils.ShellScript(f'{finish_wrapper_path}')
            guest.execute(command, cwd=workdir)

        return results
