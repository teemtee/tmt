import dataclasses
from typing import Any, List, Optional, Union

import tmt
import tmt.base
import tmt.log
import tmt.steps
import tmt.steps.provision
import tmt.utils
from tmt.utils import Command, Path, ShellScript


@dataclasses.dataclass
class ProvisionLocalData(tmt.steps.provision.GuestData, tmt.steps.provision.ProvisionStepData):
    pass


class GuestLocal(tmt.Guest):
    """ Local Host """

    localhost = True
    parent: tmt.steps.Step

    @property
    def is_ready(self) -> bool:
        """ Local is always ready """
        return True

    def _run_ansible(
            self,
            playbook: Path,
            extra_args: Optional[str] = None,
            friendly_command: Optional[str] = None,
            log: Optional[tmt.log.LoggingFunction] = None,
            silent: bool = False) -> tmt.utils.CommandOutput:
        """
        Run an Ansible playbook on the guest.

        This is a main workhorse for :py:meth:`ansible`. It shall run the
        playbook in whatever way is fitting for the guest and infrastructure.

        :param playbook: path to the playbook to run.
        :param extra_args: aditional arguments to be passed to ``ansible-playbook``
            via ``--extra-args``.
        :param friendly_command: if set, it would be logged instead of the
            command itself, to improve visibility of the command in logging output.
        :param log: a logging function to use for logging of command output. By
            default, ``logger.debug`` is used.
        :param silent: if set, logging of steps taken by this function would be
            reduced.
        """

        playbook = self._ansible_playbook_path(playbook)

        return self._run_guest_command(
            Command(
                'sudo', '-E',
                'ansible-playbook',
                *self._ansible_verbosity(),
                *self._ansible_extra_args(extra_args),
                '-c', 'local',
                '-i', 'localhost,',
                str(playbook)),
            env=self._prepare_environment(),
            friendly_command=friendly_command,
            log=log,
            silent=silent)

    def execute(self,
                command: Union[Command, ShellScript],
                cwd: Optional[Path] = None,
                env: Optional[tmt.utils.EnvironmentType] = None,
                friendly_command: Optional[str] = None,
                test_session: bool = False,
                silent: bool = False,
                log: Optional[tmt.log.LoggingFunction] = None,
                interactive: bool = False,
                **kwargs: Any) -> tmt.utils.CommandOutput:
        """ Execute command on localhost """
        # Prepare the environment (plan/cli variables override)
        environment: tmt.utils.EnvironmentType = {}
        environment.update(env or {})
        environment.update(self.parent.plan.environment)

        actual_command = command if isinstance(command, Command) else command.to_shell_command()

        # Run the command under the prepared environment
        return self._run_guest_command(
            actual_command,
            env=environment,
            log=log,
            friendly_command=friendly_command or str(command),
            silent=silent,
            cwd=cwd,
            interactive=interactive,
            **kwargs)

    def stop(self) -> None:
        """ Stop the guest """

        self.debug(f"Doing nothing to stop guest '{self.guest}'.")

    def reboot(self,
               hard: bool = False,
               command: Optional[Union[Command, ShellScript]] = None,
               timeout: Optional[int] = None) -> bool:
        """ Reboot the guest, return True if successful """

        self.debug(f"Doing nothing to reboot guest '{self.guest}'.")

        return False

    def push(
            self,
            source: Optional[Path] = None,
            destination: Optional[Path] = None,
            options: Optional[List[str]] = None,
            superuser: bool = False) -> None:
        """ Nothing to be done to push workdir """

    def pull(
            self,
            source: Optional[Path] = None,
            destination: Optional[Path] = None,
            options: Optional[List[str]] = None,
            extend_options: Optional[List[str]] = None) -> None:
        """ Nothing to be done to pull workdir """


@tmt.steps.provides_method('local')
class ProvisionLocal(tmt.steps.provision.ProvisionPlugin):
    """
    Use local host for test execution

    In general it is not recommended to run tests on your local machine
    as there might be security risks. Run only those tests which you
    know are safe so that you don't destroy your laptop ;-)

    Example config:

        provision:
            how: local

    Note that 'tmt run' is expected to be executed under a regular user.
    If there are admin rights required (for example in the prepare step)
    you might be asked for a sudo password.
    """

    _data_class = ProvisionLocalData
    _guest_class = GuestLocal

    # Guest instance
    _guest = None

    def go(self) -> None:
        """ Provision the container """
        super().go()

        # Create a GuestLocal instance
        data = tmt.steps.provision.GuestData.from_plugin(self)
        data.guest = 'localhost'

        data.show(verbose=self.verbosity_level, logger=self._logger)

        if data.hardware and data.hardware.constraint:
            self.warn("The 'local' provision plugin does not support hardware requirements.")

        self._guest = GuestLocal(logger=self._logger, data=data, name=self.name, parent=self.step)

    def guest(self) -> Optional[GuestLocal]:
        """ Return the provisioned guest """
        return self._guest
