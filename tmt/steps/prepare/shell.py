import dataclasses
from typing import TYPE_CHECKING, Any, Optional, Union, cast

import fmf
import fmf.utils

import tmt
import tmt.log
import tmt.steps
import tmt.steps.prepare
import tmt.utils
from tmt.result import PhaseResult, ResultOutcome
from tmt.steps import safe_filename
from tmt.steps.provision import Guest
from tmt.utils import ShellScript, Stopwatch, field, format_duration, format_timestamp

if TYPE_CHECKING:
    from tmt.steps.finish.shell import FinishShell

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


def go(
        phase: Union['PrepareShell', 'FinishShell'],
        *,
        guest: 'Guest',
        environment: Optional[tmt.utils.Environment] = None,
        wrapper_basename: str,
        logger: tmt.log.Logger) -> list[PhaseResult]:
    """ Run prepare/finish shell scripts on the guest """

    results: list[PhaseResult] = []
    environment = environment or tmt.utils.Environment()

    # Give a short summary
    overview = fmf.utils.listed(phase.data.script, 'script')
    logger.info('overview', f'{overview} found', 'green')

    workdir = phase.step.plan.worktree
    assert workdir is not None  # narrow type

    if not phase.is_dry_run:
        topology = tmt.steps.Topology(phase.step.plan.provision.guests())
        topology.guest = tmt.steps.GuestTopology(guest)

        environment.update(
            topology.push(
                dirpath=workdir,
                guest=guest,
                logger=logger,
                filename_base=safe_filename(tmt.steps.TEST_TOPOLOGY_FILENAME_BASE, phase, guest)
                ))

    wrapper_filename = safe_filename(wrapper_basename, phase, guest)
    wrapper_path = workdir / wrapper_filename

    logger.debug('prepare wrapper', wrapper_path, level=3)

    # Execute each script on the guest (with default shell options)
    for i, script in enumerate(phase.data.script):
        logger.verbose('script', script, 'green')

        script_with_options = tmt.utils.ShellScript(f'{tmt.utils.SHELL_OPTIONS}; {script}')
        phase.write(wrapper_path, str(script_with_options), 'w')

        if not phase.is_dry_run:
            wrapper_path.chmod(0o755)

        guest.push(
            source=wrapper_path,
            destination=wrapper_path,
            options=["-s", "-p", "--chmod=755"])

        command: ShellScript

        if guest.become and not guest.facts.is_superuser:
            command = tmt.utils.ShellScript(f'sudo -E {wrapper_path}')
        else:
            command = tmt.utils.ShellScript(f'{wrapper_path}')

        with Stopwatch() as timer:
            try:
                guest.execute(command=command, cwd=workdir, env=environment)

            except Exception:
                result = PhaseResult(
                    name=f'{phase.name}, script #{i}',
                    result=ResultOutcome.FAIL
                    )

            else:
                result = PhaseResult(
                    name=f'{phase.name}, script #{i}',
                    result=ResultOutcome.PASS
                    )

        result.start_time = format_timestamp(timer.start_time)
        result.end_time = format_timestamp(timer.end_time)
        result.duration = format_duration(timer.duration)

        results.append(result)

    return results


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

        return [
            *super().go(guest=guest, environment=environment, logger=logger),
            *go(
                self,
                guest=guest,
                environment=environment,
                wrapper_basename=PREPARE_WRAPPER_FILENAME,
                logger=logger)]
