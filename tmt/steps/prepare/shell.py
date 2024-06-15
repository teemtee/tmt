import dataclasses
from typing import Any, Optional, cast

import fmf
import fmf.utils

import tmt
import tmt.log
import tmt.steps
import tmt.steps.prepare
import tmt.utils
from tmt.result import PhaseResult
from tmt.steps import safe_filename
from tmt.steps.provision import Guest
from tmt.utils import ShellScript, field

PREPARE_WRAPPER_FILENAME = 'tmt-prepare-wrapper.sh'


@dataclasses.dataclass
class PrepareShellData(tmt.steps.prepare.PrepareStepData):
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

    # ignore[override] & cast: two base classes define to_spec(), with conflicting
    # formal types.
    def to_spec(self) -> dict[str, Any]:  # type: ignore[override]
        data = cast(dict[str, Any], super().to_spec())
        data['script'] = [str(script) for script in self.script]

        return data


@tmt.steps.provides_method('shell')
class PrepareShell(tmt.steps.prepare.PreparePlugin[PrepareShellData]):
    """
    Prepare guest using shell (Bash) scripts.

    Run various commands and scripts on the guest:

    .. code-block:: yaml

        prepare:
            how: shell
            script:
              - sudo dnf install -y 'dnf-command(copr)'
              - sudo dnf copr enable -y psss/tmt
              - sudo dnf install -y tmt
    """

    _data_class = PrepareShellData

    def go(
            self,
            *,
            guest: 'Guest',
            environment: Optional[tmt.utils.Environment] = None,
            logger: tmt.log.Logger) -> list[PhaseResult]:
        """ Prepare the guests """
        results = super().go(guest=guest, environment=environment, logger=logger)

        environment = environment or tmt.utils.Environment()

        # Give a short summary
        overview = fmf.utils.listed(self.data.script, 'script')
        logger.info('overview', f'{overview} found', 'green')

        workdir = self.step.plan.worktree
        assert workdir is not None  # narrow type

        if not self.is_dry_run:
            topology = tmt.steps.Topology(self.step.plan.provision.guests())
            topology.guest = tmt.steps.GuestTopology(guest)

            environment.update(
                topology.push(
                    dirpath=workdir,
                    guest=guest,
                    logger=logger,
                    filename_base=safe_filename(tmt.steps.TEST_TOPOLOGY_FILENAME_BASE, self, guest)
                    ))

        prepare_wrapper_filename = safe_filename(PREPARE_WRAPPER_FILENAME, self, guest)
        prepare_wrapper_path = workdir / prepare_wrapper_filename

        logger.debug('prepare wrapper', prepare_wrapper_path, level=3)

        # Execute each script on the guest (with default shell options)
        for script in self.data.script:
            logger.verbose('script', script, 'green')
            script_with_options = tmt.utils.ShellScript(f'{tmt.utils.SHELL_OPTIONS}; {script}')
            self.write(prepare_wrapper_path, str(script_with_options), 'w')
            if not self.is_dry_run:
                prepare_wrapper_path.chmod(0o755)
            guest.push(
                source=prepare_wrapper_path,
                destination=prepare_wrapper_path,
                options=["-s", "-p", "--chmod=755"])
            command: ShellScript
            if guest.become and not guest.facts.is_superuser:
                command = tmt.utils.ShellScript(f'sudo -E {prepare_wrapper_path}')
            else:
                command = tmt.utils.ShellScript(f'{prepare_wrapper_path}')
            guest.execute(
                command=command,
                cwd=workdir,
                env=environment)

        return results
