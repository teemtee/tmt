import dataclasses
import os
from shlex import quote
from typing import Any, Optional, Union, cast

import tmt
import tmt.base
import tmt.log
import tmt.steps
import tmt.steps.provision
import tmt.utils
from tmt.options import show_step_method_hints
from tmt.steps.provision import GuestCapability
from tmt.utils import Command, OnProcessStartCallback, Path, ShellScript, field, retry

# Timeout in seconds of waiting for a connection
CONNECTION_TIMEOUT = 60

# Defaults
DEFAULT_IMAGE = "fedora"
DEFAULT_USER = "root"
DEFAULT_PULL_ATTEMPTS = 5
DEFAULT_PULL_INTERVAL = 5
# podman default stop time is 10s
DEFAULT_STOP_TIME = 1


@dataclasses.dataclass
class PodmanGuestData(tmt.steps.provision.GuestData):
    image: str = field(
        default=DEFAULT_IMAGE,
        option=('-i', '--image'),
        metavar='IMAGE',
        help='Select image to use. Short name or complete url.')
    # Override parent class with our defaults
    user: str = field(
        default=DEFAULT_USER,
        option=('-u', '--user'),
        metavar='USERNAME',
        help='Username to use for all guest operations.')
    force_pull: bool = field(
        default=False,
        option=('-p', '--pull', '--force-pull'),
        is_flag=True,
        help='Force pulling a fresh container image.')

    container: Optional[str] = field(
        default=None,
        option=('-c', '--container'),
        metavar='NAME',
        help='Name or id of an existing container to be used.')
    network: Optional[str] = field(
        default=None,
        internal=True)

    pull_attempts: int = field(
        default=DEFAULT_PULL_ATTEMPTS,
        option='--pull-attempts',
        metavar='COUNT',
        help=f"""
             How many times to try pulling the image,
             {DEFAULT_PULL_ATTEMPTS} attempts by default.
             """,
        normalize=tmt.utils.normalize_int)

    pull_interval: int = field(
        default=DEFAULT_PULL_INTERVAL,
        option='--pull-interval',
        metavar='SECONDS',
        help=f"""
             How long to wait before a new pull attempt,
             {DEFAULT_PULL_INTERVAL} seconds by default.
             """,
        normalize=tmt.utils.normalize_int)

    stop_time: int = field(
        default=DEFAULT_STOP_TIME,
        option='--stop-time',
        metavar='SECONDS',
        help=f"""
             How long to wait before forcibly stopping the container,
             {DEFAULT_STOP_TIME} seconds by default.
             """,
        normalize=tmt.utils.normalize_int)


@dataclasses.dataclass
class ProvisionPodmanData(PodmanGuestData, tmt.steps.provision.ProvisionStepData):
    pass


class GuestContainer(tmt.Guest):
    """ Container Instance """

    _data_class = PodmanGuestData

    image: Optional[str]
    container: Optional[str]
    user: str
    force_pull: bool
    parent: tmt.steps.Step
    pull_attempts: int
    pull_interval: int
    stop_time: int
    logger: tmt.log.Logger

    @property
    def is_ready(self) -> bool:
        """ Detect the guest is ready or not """
        # Check the container is running or not
        if self.container is None:
            return False
        cmd_output = self.podman(Command(
            'container', 'inspect',
            '--format', '{{json .State.Running}}',
            self.container
            ))
        return str(cmd_output.stdout).strip() == 'true'

    def wake(self) -> None:
        """ Wake up the guest """
        self.debug(
            f"Waking up container '{self.container}'.", level=2, shift=0)

    def pull_image(self) -> None:
        """ Pull image if not available or pull forced """
        assert self.image is not None  # narrow type

        self.podman(
            Command('pull', '-q', self.image),
            message=f"Pull image '{self.image}'."
            )

    def _setup_network(self) -> list[str]:
        """
        Set up the desired network.
        Will look for existing network using the tmt workdir name,
        or will create that network if it doesn't exist.
        Returns the network arguments to be used in podman run command.
        """

        run_id = self._tmt_name().split('-')[1]
        self.network = f"tmt-{run_id}-network"

        try:
            self.podman(
                Command('network', 'create', self.network),
                message=f"Create network '{self.network}'."
                )
        except tmt.utils.RunError as err:
            if err.stderr and 'network already exists' in err.stderr:
                # error string:
                # https://github.com/containers/common/blob/main/libnetwork/types/define.go#L19
                self.debug(f"Network '{self.network}' already exists.", level=3)
            else:
                raise err

        return ['--network', self.network]

    def start(self) -> None:
        """ Start provisioned guest """
        if self.is_dry_run:
            return

        if self.container:
            self.primary_address = self.topology_address = self.container

            self.verbose('primary address', self.primary_address, 'green')
            self.verbose('topology address', self.topology_address, 'green')

            return

        self.container = self.primary_address = self.topology_address = self._tmt_name()
        self.verbose('primary address', self.primary_address, 'green')
        self.verbose('topology address', self.topology_address, 'green')

        # Check if the image is available
        assert self.image is not None

        try:
            self.podman(
                Command('image', 'exists', self.image),
                message=f"Check for container image '{self.image}'."
                )
            needs_pull = False
        except tmt.utils.RunError:
            needs_pull = True

        # Retry pulling the image in case of network issues
        # Temporary solution until configurable in podman itself
        if needs_pull or self.force_pull:
            retry(
                self.pull_image,
                self.pull_attempts,
                self.pull_interval,
                f"Pulling '{self.image}' image",
                self._logger
                )

        # Mount the whole plan directory in the container
        workdir = self.parent.plan.workdir

        self.verbose('name', self.container, 'green')

        additional_args = []

        additional_args.extend(self._setup_network())

        # Run the container
        self.debug(f"Start container '{self.image}'.")
        assert self.container is not None
        self.podman(Command(
            'run',
            *additional_args,
            '--name', self.container,
            '-v', f'{workdir}:{workdir}:z',
            '-itd',
            '--user', self.user,
            self.image
            ))

    def reboot(self, hard: bool = False,
               command: Optional[Union[Command, ShellScript]] = None,
               timeout: Optional[int] = None) -> bool:
        """ Restart the container, return True if successful  """
        if command:
            raise tmt.utils.ProvisionError(
                "Custom reboot command not supported in podman provision.")
        if not hard:
            raise tmt.utils.ProvisionError(
                "Containers do not support soft reboot, they can only be "
                "stopped and started again (hard reboot).")
        assert self.container is not None
        self.podman(Command('container', 'restart', self.container))
        return self.reconnect(timeout=timeout or CONNECTION_TIMEOUT)

    def _run_ansible(
            self,
            playbook: tmt.steps.provision.AnsibleApplicable,
            playbook_root: Optional[Path] = None,
            extra_args: Optional[str] = None,
            friendly_command: Optional[str] = None,
            log: Optional[tmt.log.LoggingFunction] = None,
            silent: bool = False) -> tmt.utils.CommandOutput:
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

        # As non-root we must run with podman unshare
        podman_command = Command()

        if os.geteuid() != 0:
            podman_command += ['podman', 'unshare']

        podman_command += cast(tmt.utils.RawCommand, [
            'ansible-playbook',
            *self._ansible_verbosity(),
            *self._ansible_extra_args(extra_args),
            '-c', 'podman', '-i', f'{self.container},', playbook
            ])

        try:
            return self._run_guest_command(
                podman_command,
                cwd=self.parent.plan.worktree,
                env=self._prepare_environment(),
                friendly_command=friendly_command,
                log=log,
                silent=silent)
        except tmt.utils.RunError as exc:
            if "File 'ansible-playbook' not found." in exc.message:
                show_step_method_hints('plugin', 'ansible', self._logger)
            raise exc

    def podman(
            self,
            command: Command,
            silent: bool = True,
            **kwargs: Any) -> tmt.utils.CommandOutput:
        """ Run given command via podman """
        try:
            return self._run_guest_command(Command('podman') + command, silent=silent, **kwargs)
        except tmt.utils.RunError as err:
            if ("File 'podman' not found." in err.message or
                    "File 'ansible-playbook' not found." in err.message):
                raise tmt.utils.ProvisionError(
                    "Install 'tmt+provision-container' to provision using this method.")
            raise err

    def execute(self,
                command: Union[tmt.utils.Command, tmt.utils.ShellScript],
                cwd: Optional[Path] = None,
                env: Optional[tmt.utils.Environment] = None,
                friendly_command: Optional[str] = None,
                test_session: bool = False,
                tty: bool = False,
                silent: bool = False,
                log: Optional[tmt.log.LoggingFunction] = None,
                interactive: bool = False,
                on_process_start: Optional[OnProcessStartCallback] = None,
                **kwargs: Any) -> tmt.utils.CommandOutput:
        """ Execute given commands in podman via shell """
        if not self.container and not self.is_dry_run:
            raise tmt.utils.ProvisionError(
                'Could not execute without provisioned container.')

        podman_command = Command('exec')

        # Accumulate all necessary commands - they will form a "shell" script, a single
        # string passed to a shell executed inside the container.
        script = ShellScript.from_scripts(self._export_environment(self._prepare_environment(env)))

        # Change to given directory on guest if cwd provided
        if cwd is not None:
            script += ShellScript(f'cd {quote(str(cwd))}')

        if isinstance(command, Command):
            script += command.to_script()

        else:
            script += command

        # Run in interactive mode if requested
        if interactive:
            podman_command += ['-it']

        # Run with a `tty` if requested
        elif tty:
            podman_command += ['-t']

        podman_command += [
            self.container or 'dry',
            ]

        podman_command += script.to_shell_command()

        # Note that we MUST run commands via bash, so variables
        # work as expected
        return self.podman(
            podman_command,
            log=log if log else self._command_verbose_logger,
            friendly_command=friendly_command or str(command),
            silent=silent,
            interactive=interactive,
            on_process_start=on_process_start,
            **kwargs)

    def push(
            self,
            source: Optional[Path] = None,
            destination: Optional[Path] = None,
            options: Optional[list[str]] = None,
            superuser: bool = False) -> None:
        """ Make sure that the workdir has a correct selinux context """
        if not self.is_ready:
            return

        assert self.parent.plan.my_run is not None  # narrow type
        assert self.parent.plan.workdir is not None  # narrow type

        # Relabel workdir to container_file_t if SELinux supported
        self.debug("Update selinux context of the run workdir.", level=3)

        if self.parent.plan.my_run.runner.facts.has_selinux:
            self._run_guest_command(Command(
                "chcon", "--recursive", "--type=container_file_t", self.parent.plan.workdir
                ), shell=False, silent=True)

        # In case explicit destination is given, use `podman cp` to copy data
        # to the container. If running in toolbox, make sure to copy from the toolbox
        # container instead of localhost.
        if source and destination:
            container_name: Optional[str] = None
            if self.parent.plan.my_run.runner.facts.is_toolbox:
                container_name = self.parent.plan.my_run.runner.facts.toolbox_container_name
            self.podman(
                Command(
                    "cp",
                    f"{container_name}:{source}"
                    if container_name else source,
                    f"{self.container}:{destination}"
                    )
                )

    def pull(
            self,
            source: Optional[Path] = None,
            destination: Optional[Path] = None,
            options: Optional[list[str]] = None,
            extend_options: Optional[list[str]] = None) -> None:
        """ Nothing to be done to pull workdir """
        if not self.is_ready:
            return

    def stop(self) -> None:
        """ Stop provisioned guest """
        if self.container:
            self.podman(Command('container', 'stop', '--time',
                        str(self.stop_time), self.container))
            self.info('container', 'stopped', 'green')

    def remove(self) -> None:
        """ Remove the container """
        if self.container:
            self.podman(Command('container', 'rm', '-f', self.container))
            self.info('container', 'removed', 'green')

        if self.network:
            # Will remove the network if there are no more containers attached to it.
            try:
                self.podman(
                    Command('network', 'rm', self.network),
                    message=f"Remove network '{self.network}'.")
                self.info('container', 'network removed', 'green')
            except tmt.utils.RunError as err:
                if err.stderr and 'network is being used' in err.stderr:
                    # error string:
                    # https://github.com/containers/podman/blob/main/libpod/define/errors.go#L180
                    self.debug(f"Network '{self.network}' is being used, not removing.", level=3)
                else:
                    raise err


@tmt.steps.provides_method('container')
class ProvisionPodman(tmt.steps.provision.ProvisionPlugin[ProvisionPodmanData]):
    """
    Create a new container using ``podman``.

    Example config:

    .. code-block:: yaml

        provision:
            how: container
            image: fedora:latest

    In order to always pull the fresh container image use ``pull: true``.

    In order to run the container with different user as the default ``root``,
    use ``user: USER``.
    """

    _data_class = ProvisionPodmanData
    _guest_class = GuestContainer

    _thread_safe = True

    # Guest instance
    _guest = None

    def default(self, option: str, default: Any = None) -> Any:
        """ Return default data for given option """
        if option == 'pull':
            return self.data.force_pull

        return super().default(option, default=default)

    def go(self, *, logger: Optional[tmt.log.Logger] = None) -> None:
        """ Provision the container """
        super().go(logger=logger)

        # Prepare data for the guest instance
        data = PodmanGuestData.from_plugin(self)

        data.show(verbose=self.verbosity_level, logger=self._logger)

        if data.hardware and data.hardware.constraint:
            self.warn("The 'container' provision plugin does not support hardware requirements.")

        # Create a new GuestTestcloud instance and start it
        self._guest = GuestContainer(
            logger=self._logger,
            data=data,
            name=self.name,
            parent=self.step)
        self._guest.start()
        self._guest.setup()

        # TODO: this might be allowed with `--privileged`...
        self._guest.facts.capabilities[GuestCapability.SYSLOG_ACTION_READ_ALL] = False
        # ... while this seems to be forbidden completely.
        self._guest.facts.capabilities[GuestCapability.SYSLOG_ACTION_READ_CLEAR] = False

    def guest(self) -> Optional[GuestContainer]:
        """ Return the provisioned guest """
        return self._guest
