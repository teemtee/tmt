import dataclasses
from typing import Any, Dict, List, Optional, cast

import fmf

import tmt
import tmt.log
import tmt.steps
import tmt.steps.prepare
import tmt.utils
from tmt.steps.provision import Guest
from tmt.utils import ShellScript, field


@dataclasses.dataclass
class PrepareShellData(tmt.steps.prepare.PrepareStepData):
    script: List[ShellScript] = field(
        default_factory=list,
        option=('-s', '--script'),
        multiple=True,
        metavar='SCRIPT',
        help='Shell script to be executed. Can be used multiple times.',
        normalize=tmt.utils.normalize_shell_script_list,
        serialize=lambda scripts: [str(script) for script in scripts],
        unserialize=lambda serialized: [ShellScript(script) for script in serialized]
        )

    # ignore[override] & cast: two base classes define to_spec(), with conflicting
    # formal types.
    def to_spec(self) -> Dict[str, Any]:  # type: ignore[override]
        data = cast(Dict[str, Any], super().to_spec())
        data['script'] = [str(script) for script in self.script]

        return data


@tmt.steps.provides_method('shell')
class PrepareShell(tmt.steps.prepare.PreparePlugin):
    """
    Prepare guest using shell (bash) scripts

    Example config:

    prepare:
        how: shell
        script:
        - sudo dnf install -y 'dnf-command(copr)'
        - sudo dnf copr enable -y psss/tmt
        - sudo dnf install -y tmt

    Use 'order' attribute to select in which order preparation should
    happen if there are multiple configs. Default order is '50'.
    Default order of required packages installation is '70'.
    """

    _data_class = PrepareShellData

    def go(
            self,
            *,
            guest: 'Guest',
            environment: Optional[tmt.utils.EnvironmentType] = None,
            logger: tmt.log.Logger) -> None:
        """ Prepare the guests """
        super().go(guest=guest, environment=environment, logger=logger)

        environment = environment or {}

        # Give a short summary
        scripts: List[tmt.utils.ShellScript] = self.get('script')
        overview = fmf.utils.listed(scripts, 'script')
        logger.info('overview', f'{overview} found', 'green')

        if not self.is_dry_run and self.step.plan.worktree:
            topology = tmt.steps.Topology(self.step.plan.provision.guests())
            topology.guest = tmt.steps.GuestTopology(guest)

            # Since we do not have the test data dir at hand, we must make the topology
            # filename unique on our own, and include the phase name and guest name.
            filename_base = f'{tmt.steps.TEST_TOPOLOGY_FILENAME_BASE}-{self.safe_name}-{guest.safe_name}'  # noqa: E501

            environment.update(
                topology.push(
                    dirpath=self.step.plan.worktree,
                    guest=guest,
                    logger=logger,
                    filename_base=filename_base))

        # Execute each script on the guest (with default shell options)
        for script in scripts:
            logger.verbose('script', script, 'green')
            script_with_options = tmt.utils.ShellScript(f'{tmt.utils.SHELL_OPTIONS}; {script}')
            guest.execute(script_with_options, cwd=self.step.plan.worktree, env=environment)
