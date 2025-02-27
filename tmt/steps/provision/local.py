from typing import Any, Optional, Union

import tmt
import tmt.base
import tmt.log
import tmt.steps
import tmt.steps.provision
import tmt.utils
from tmt.container import container
from tmt.utils import Command, OnProcessStartCallback, Path, ShellScript


@container
class ProvisionLocalData(tmt.steps.provision.GuestData, tmt.steps.provision.ProvisionStepData):
    pass


class GuestLocal(tmt.Guest):
    """
    Local Host
    """

    localhost = True
    parent: Optional[tmt.steps.Step]

    @property
    def is_ready(self) -> bool:
        """
        Local is always ready
        """

        return True

    def _run_ansible(
        self,
        playbook: tmt.steps.provision.AnsibleApplicable,
        playbook_root: Optional[Path] = None,
        extra_args: Optional[str] = None,
        friendly_command: Optional[str] = None,
        log: Optional[tmt.log.LoggingFunction] = None,
        silent: bool = False,
    ) -> tmt.utils.CommandOutput:
        """
        Run an Ansible playbook on the guest.

        This is a main workhorse for :py:meth:`ansible`. It shall run the
        playbook in whatever way is fitting for the guest and infrastructure.

        :param playbook: path to the playbook to run.
        :param playbook_root: if set, ``playbook`` path must be located
            under the given root path.
        :param extra_args: additional arguments to be passed to ``ansible-playbook``
            via ``--extra-args``.
        :param friendly_command: if set, it would be logged instead of the
            command itself, to improve visibility of the command in logging output.
        :param log: a logging function to use for logging of command output. By
            default, ``logger.debug`` is used.
        :param silent: if set, logging of steps taken by this function would be
            reduced.
        """

        playbook = self._sanitize_ansible_playbook_path(playbook, playbook_root)

        try:
            # fmt: off
            return self._run_guest_command(
                Command(
                    'sudo', '-E',
                    'ansible-playbook',
                    *self._ansible_verbosity(),
                    *self._ansible_extra_args(extra_args),
                    '-c', 'local',
                    '-i', 'localhost,',
                    playbook,
                ),
                env=self._prepare_environment(),
                friendly_command=friendly_command,
                log=log,
                silent=silent,
            )
            # fmt: on
        except tmt.utils.RunError as exc:
            if exc.stderr and 'ansible-playbook: command not found' in exc.stderr:
                from tmt.utils.hints import print_hints

                print_hints('ansible-not-available', logger=self._logger)
            raise exc

    def execute(
        self,
        command: Union[Command, ShellScript],
        cwd: Optional[Path] = None,
        env: Optional[tmt.utils.Environment] = None,
        friendly_command: Optional[str] = None,
        test_session: bool = False,
        tty: bool = False,
        silent: bool = False,
        log: Optional[tmt.log.LoggingFunction] = None,
        interactive: bool = False,
        on_process_start: Optional[OnProcessStartCallback] = None,
        **kwargs: Any,
    ) -> tmt.utils.CommandOutput:
        """
        Execute command on localhost
        """

        # Prepare the environment (plan/cli variables override)
        environment = tmt.utils.Environment()
        environment.update(env or {})
        if self.parent:
            environment.update(self.parent.plan.environment)

        if tty:
            self.warn("Ignoring requested tty, not supported by the 'local' provision plugin.")

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
            on_process_start=on_process_start,
            **kwargs,
        )

    def start(self) -> None:
        """
        Start the guest
        """

        self.debug(f"Doing nothing to start guest '{self.primary_address}'.")

        self.verbose('primary address', self.primary_address, 'green')
        self.verbose('topology address', self.topology_address, 'green')

    def stop(self) -> None:
        """
        Stop the guest
        """

        self.debug(f"Doing nothing to stop guest '{self.primary_address}'.")

    def reboot(
        self,
        hard: bool = False,
        command: Optional[Union[Command, ShellScript]] = None,
        timeout: Optional[int] = None,
        tick: float = tmt.utils.DEFAULT_WAIT_TICK,
        tick_increase: float = tmt.utils.DEFAULT_WAIT_TICK_INCREASE,
    ) -> bool:
        # No localhost reboot allowed!
        self.debug(f"Doing nothing to reboot guest '{self.primary_address}'.")

        return False

    def push(
        self,
        source: Optional[Path] = None,
        destination: Optional[Path] = None,
        options: Optional[list[str]] = None,
        superuser: bool = False,
    ) -> None:
        """
        Nothing to be done to push workdir
        """

    def pull(
        self,
        source: Optional[Path] = None,
        destination: Optional[Path] = None,
        options: Optional[list[str]] = None,
        extend_options: Optional[list[str]] = None,
    ) -> None:
        """
        Nothing to be done to pull workdir
        """


@tmt.steps.provides_method('local')
class ProvisionLocal(tmt.steps.provision.ProvisionPlugin[ProvisionLocalData]):
    """
    Use local host for test execution.

    .. warning::

        In general, it is not recommended to run tests on your local machine
        as there might be security risks. Run only those tests which you
        know are safe so that you don't destroy your laptop ;-)

        From tmt version 1.38, the ``--feeling-safe`` option or
        the ``TMT_FEELING_SAFE=1`` environment variable is
        required in order to use the local provision plugin.

    Example config:

    .. code-block:: yaml

        provision:
            how: local

    Note that ``tmt run`` is expected to be executed under a regular user.
    If there are admin rights required (for example in the prepare step)
    you might be asked for a ``sudo`` password.

    .. note::

        Neither hard nor soft reboot is supported.
    """

    _data_class = ProvisionLocalData
    _guest_class = GuestLocal

    _thread_safe = True

    # Guest instance
    _guest = None

    def go(self, *, logger: Optional[tmt.log.Logger] = None) -> None:
        """
        Provision the container
        """

        super().go(logger=logger)

        # Create a GuestLocal instance
        data = tmt.steps.provision.GuestData.from_plugin(self)
        data.primary_address = 'localhost'

        data.show(verbose=self.verbosity_level, logger=self._logger)

        self.assert_feeling_safe("1.38", "The 'local' provision plugin")

        if data.hardware and data.hardware.constraint:
            self.warn("The 'local' provision plugin does not support hardware requirements.")

        self._guest = GuestLocal(logger=self._logger, data=data, name=self.name, parent=self.step)
        self._guest.setup()
