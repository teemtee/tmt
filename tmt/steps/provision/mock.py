import fcntl
import os
import select
import shlex
import subprocess
from pathlib import Path
from typing import Any, Optional, Union

import mockbuild
import mockbuild.config
import mockbuild.plugins
import mockbuild.plugins.pm_request

import tmt
import tmt.base
import tmt.log
import tmt.steps
import tmt.steps.provision
import tmt.utils
from tmt.container import container, field
from tmt.utils import Command, OnProcessStartCallback, Path, ShellScript
from tmt.utils.wait import Waiting


@container
class MockGuestData(tmt.steps.provision.GuestData):
    config: Optional[str] = field(
        default=None,
        option=('-r', '--config'),
        metavar='CONFIG',
        help='Mock chroot configuration file.',
    )
    rootdir: Optional[str] = field(
        default=None,
        option=('--rootdir'),
        metavar='ROOTDIR',
        help='The path for where the chroot should be built.',
    )


@container
class ProvisionMockData(MockGuestData, tmt.steps.provision.ProvisionStepData):
    pass


class MockShell:
    def __init__(self, parent: 'GuestMock', config: Optional[str], rootdir: Optional[str] = None):
        self.parent = parent
        self.config = config
        self.rootdir = rootdir
        self.mock_shell: Optional[subprocess.Popen] = None
        self.epoll: Optional[select.epoll] = None
        # Required by loggers
        self.pid: Optional[int] = None

        self.command_prefix = Command('mock')
        if self.config is not None:
            self.command_prefix += ['-r', self.config]
        if self.rootdir is not None:
            self.command_prefix += ['--rootdir', self.rootdir]

        root_path = (
            (self.command_prefix + ['--print-root-path'])
            .run(cwd=None, logger=self.parent._logger)
            .stdout
        )
        assert root_path is not None
        self.root_path = Path(root_path.rstrip())

    def __del__(self):
        self.exit_shell()

    def exit_shell(self) -> None:
        if self.mock_shell is not None:
            self.parent.verbose("Exiting mock shell")

            self.mock_shell.stdin.write("")
            self.mock_shell.stdin.flush()
            self.mock_shell.communicate()
            self.mock_shell = None
            self.epoll.close()
            self.epoll = None
            self.pid = None

    def enter_shell(self):
        command = self.command_prefix.to_popen()
        command.append("--enable-network")
        command.append("--enable-plugin")
        command.append("tmt")
        command.append(
            f"--plugin-option=tmt:workdir_root='{shlex.quote(str(self.parent.workdir_root))}'"
        )
        command.append("-q")
        command.append("--shell")
        self.parent.verbose("Entering mock shell")
        self.parent.verbose(command)
        self.mock_shell = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.epoll = select.epoll()
        self.pid = self.mock_shell.pid

        self.mock_shell_stdout_fd = self.mock_shell.stdout.fileno()
        flags = fcntl.fcntl(self.mock_shell_stdout_fd, fcntl.F_GETFL)
        fcntl.fcntl(self.mock_shell_stdout_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
        self.epoll.register(self.mock_shell_stdout_fd, select.EPOLLIN)

        self.mock_shell_stderr_fd = self.mock_shell.stderr.fileno()
        flags = fcntl.fcntl(self.mock_shell_stderr_fd, fcntl.F_GETFL)
        fcntl.fcntl(self.mock_shell_stderr_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
        self.epoll.register(self.mock_shell_stderr_fd, select.EPOLLIN)

        loop = True
        while loop and self.mock_shell.poll() is None:
            events = self.epoll.poll()
            for fileno, _ in events:
                if fileno == self.mock_shell_stdout_fd:
                    loop = False
                    self.mock_shell.stdout.read()
                    # shell is ready
                    break

        # clear stderr
        if self.mock_shell.poll() is None:
            for fileno, _ in self.epoll.poll(0):
                if fileno == self.mock_shell_stderr_fd:
                    self.mock_shell.stderr.read()
                    break

        self.parent.verbose("Mock shell is ready")

        """
        NOTE Here we would like to add code which unmounts the overlayfs
        after the prepare phase is done. Nevertheless testing should work even
        with the bootstrap chroot mounted.

        plan = self.parent.parent.parent

        prepare_data_class = cast(  # type: ignore[redundant-cast]
            type[tmt.steps.prepare.shell.PrepareShellData],
            tmt.steps.prepare.shell.PrepareShell.get_data_class(),
        )

        data = prepare_data_class(
            name="tmt-unmount-mock-bootstrap-overlay",
            how='shell',
            script=[
                TODO
            ],
        )

        phase: PreparePlugin[Any] = cast(
            PreparePlugin[Any],
            PreparePlugin.delegate(plan.prepare, data=data),
        )

        plan.prepare._phases.append(phase)
        """

        return self

    def execute(
        self,
        command: Command,
        cwd: Optional[Path] = None,
        env: Optional[tmt.utils.Environment] = None,
        friendly_command: str = None,
    ):
        """
        Execute the command in a running mock shell for increased speed.
        """

        if self.mock_shell is None:
            self.enter_shell()
        shell_command = ""
        if cwd is not None:
            shell_command += "(cd " + shlex.quote(str(cwd)) + " && "
        if env is not None:
            for key, value in env.items():
                shell_command += f"{key}={shlex.quote(value)} "
        shell_command += str(command)
        if cwd is not None:
            shell_command += ")"
        shell_command += " 1>/tmp/stdout 2>/tmp/stderr; echo $?>/tmp/returncode"

        self.parent.verbose("Executing inside mock shell", shell_command)

        shell_command += "\n"

        self.mock_shell.stdin.write(shell_command)
        self.mock_shell.stdin.flush()

        # TODO Instead of reading stdout and stderr when the process finishes,
        # we can open sockets or pipes and use epoll to provide real-time output.
        while self.mock_shell.poll() is None:
            events = self.epoll.poll()
            for fileno, _ in events:
                if fileno == self.mock_shell_stderr_fd:
                    self.mock_shell.stderr.read()
                if fileno == self.mock_shell_stdout_fd:
                    self.mock_shell.stdout.read()
                    with open(self.root_path / "tmp/stdout") as istream:
                        stdout = istream.read()
                    with open(self.root_path / "tmp/stderr") as istream:
                        stderr = istream.read()
                    with open(self.root_path / "tmp/returncode") as istream:
                        returncode = int(istream.read().strip())
                    if returncode != 0:
                        raise tmt.utils.RunError(
                            f"Command '{friendly_command or shell_command}' returned {returncode}.",
                            command,
                            returncode,
                            stdout=stdout,
                            stderr=stderr,
                        )
                    return (stdout, stderr)

        raise tmt.utils.RunError(
            f"Invalid state when executing command '{friendly_command or shell_command}'.",
            command,
            127,
            stdout="",
            stderr="",
        )


class GuestMock(tmt.Guest):
    """
    Mock environment
    """

    _data_class = MockGuestData
    mock_shell: MockShell
    mock_config: dict

    @property
    def is_ready(self) -> bool:
        """
        Mock is always ready
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

        raise NotImplementedError("ansible is not currently supported")

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
        Execute command inside mock
        """

        actual_command = command if isinstance(command, Command) else command.to_shell_command()
        if on_process_start:
            on_process_start(actual_command, self.mock_shell, self._logger)
        stdout, stderr = self.mock_shell.execute(
            actual_command, cwd=cwd, env=env, friendly_command=friendly_command or str(command)
        )
        result = tmt.utils.CommandOutput(stdout, stderr)
        return result

    def start(self) -> None:
        """
        Start the guest
        """
        self.debug(f"Doing nothing to start guest '{self.primary_address}'.")

    def stop(self) -> None:
        """
        Stop the guest
        """
        self.debug(f"Doing nothing to stop guest '{self.primary_address}'.")

    def reboot(
        self,
        hard: bool = False,
        command: Optional[Union[Command, ShellScript]] = None,
        waiting: Optional[Waiting] = None,
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
        Thanks to mock's bind-mounting, no file copying is needed
        """

    def pull(
        self,
        source: Optional[Path] = None,
        destination: Optional[Path] = None,
        options: Optional[list[str]] = None,
        extend_options: Optional[list[str]] = None,
    ) -> None:
        """
        Thanks to mock's bind-mounting, no file copying is needed
        """

    def load(self, data: tmt.steps.provision.GuestData) -> None:
        super().load(data)
        self.mock_shell = MockShell(parent=self, config=self.config, rootdir=self.rootdir)
        self.mock_config = data.mock_config

    def save(self) -> tmt.steps.provision.GuestData:
        # inherit
        return super().save()

    def wake(self) -> None:
        # noop
        return super().wake()

    def setup(self) -> None:
        super().setup()
        # If we are not using bootstrap, then we need to install the package manager.
        # Otherwise we use overlayfs and the package manager from bootstrap chroot.
        if self.mock_config['use_bootstrap'] is not True:
            (
                self.mock_shell.command_prefix + ['--install', self.mock_config['package_manager']]
            ).run(cwd=None, logger=self.parent._logger)


@tmt.steps.provides_method('mock')
class ProvisionMock(tmt.steps.provision.ProvisionPlugin[ProvisionMockData]):
    """
    Provisioning using mock chroot.
    """

    _data_class = ProvisionMockData
    _guest_class = GuestMock

    _thread_safe = True

    # Guest instance
    _guest = None

    def go(self, *, logger: Optional[tmt.log.Logger] = None) -> None:
        """
        Provision the container
        """

        super().go(logger=logger)

        # Create a GuestMock instance
        data = MockGuestData.from_plugin(self)

        # NOTE this may be unnecessary, tmt package manager detection should work fine
        # but mock already knows what the package manager is...
        mock_config = mockbuild.config.simple_load_config(data.config)
        package_manager = "mock-" + mock_config['package_manager']

        # If this provisioning is selected, then we force the use of `mock-` package manager.
        # NOTE use a global variable instead?
        tmt.package_managers.find_package_manager(
            package_manager
        ).probe_command = tmt.utils.Command('true')

        # NOTE any better ideas?
        data.primary_address = (data.config or '<default>') + (
            '@' + data.rootdir if data.rootdir is not None else ''
        )
        data.mock_config = mock_config

        data.show(verbose=self.verbosity_level, logger=self._logger)

        self.assert_feeling_safe("1.38", "The 'mock' provision plugin")

        if data.hardware and data.hardware.constraint:
            self.warn("The 'mock' provision plugin does not support hardware requirements.")

        self._guest = GuestMock(logger=self._logger, data=data, name=self.name, parent=self.step)
        self._guest.setup()
