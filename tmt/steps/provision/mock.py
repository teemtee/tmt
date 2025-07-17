import fcntl
import os
import select
import shlex
import subprocess
from pathlib import Path
from typing import Any, Optional, Union

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
        help='TODO.',
    )
    rootdir: Optional[str] = field(
        default=None,
        option=('--rootdir'),
        metavar='ROOTDIR',
        help='TODO.',
    )


@container
class ProvisionMockData(MockGuestData, tmt.steps.provision.ProvisionStepData):
    pass


class MockShell:
    def __init__(self, parent: 'GuestMock', config, rootdir=None):
        self.parent = parent
        self.config = config
        self.rootdir = rootdir
        self.mock_shell = None
        self.epoll = None

        self.command_prefix = Command('mock')
        if self.config is not None:
            self.command_prefix += ['-r', self.config]
        if self.rootdir is not None:
            self.command_prefix += ['--rootdir', self.rootdir]

        self.root_path = Path(
            (self.command_prefix + ['--print-root-path'])
            .run(cwd=None, logger=self.parent._logger)
            .stdout.rstrip()
        )

    def install(self, *installables, options: tmt.package_managers.Options = {}):
        if len(installables) == 0:
            return
        self.exit_shell()
        # TODO use options
        (self.command_prefix + ["--install"] + installables).run(
            cwd=None, logger=self.parent._logger
        )

    def __del__(self):
        self.exit_shell()

    def exit_shell(self):
        if self.mock_shell is not None:
            self.parent.verbose("Exiting mock shell")

            self.mock_shell.stdin.write("")
            self.mock_shell.stdin.flush()
            self.mock_shell.communicate()
            self.mock_shell = None
            self.epoll.close()
            self.epoll = None

    def enter_shell(self):
        command = self.command_prefix.to_popen()
        command.append(
            f"--plugin-option=bind_mount:dirs=[('{self.parent.workdir_root}', '{self.parent.workdir_root}')]"
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
        self.mock_shell.stderr.read()
        self.parent.verbose("Mock shell is ready")

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
            shell_command += "(cd " + str(cwd) + " && "
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


class GuestMock(tmt.Guest):
    """
    Mock environment
    """

    _data_class = MockGuestData
    mock_shell: MockShell

    @property
    def is_ready(self) -> bool:
        """
        NOTE ???
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

    def save(self) -> tmt.steps.provision.GuestData:
        # inherit
        return super().save()

    def wake(self) -> None:
        # noop
        return super().wake()

    def setup(self) -> None:
        # NOTE call --init?
        # but a valid use case is reusing existing mock envs
        return super().setup()


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

        # If this provisioning is selected, then we force the use of `mock` package manager.
        # NOTE use a global variable instead?
        tmt.package_managers.mock.Mock.probe_command = tmt.utils.Command('true')

        super().go(logger=logger)

        # Create a GuestMock instance
        data = ProvisionMockData.from_plugin(self)

        # TODO is this needed? and where to place it? the data is not yet initialized
        data.primary_address = (self._data_class.config or '<default>') + (
            '@' + self._data_class.rootdir if self._data_class.rootdir is not None else ''
        )

        data.show(verbose=self.verbosity_level, logger=self._logger)

        self.assert_feeling_safe("1.38", "The 'mock' provision plugin")

        if data.hardware and data.hardware.constraint:
            self.warn("The 'mock' provision plugin does not support hardware requirements.")

        self._guest = GuestMock(logger=self._logger, data=data, name=self.name, parent=self.step)
        self._guest.setup()
