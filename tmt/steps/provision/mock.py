import fcntl
import os
import io
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
    # Lazy object that collects chunks of bytes and decodes them when a
    # newline is encountered
    class Stream:
        def __init__(self, logger):
            self.logger = logger
            self.output = bytes()
            self.string = str()

        def __iadd__(self, content: bytes):
            self.output += content
            while True:
                pos = self.output.find(b'\n')
                if pos == -1:
                    break
                string = self.output[:pos].decode('utf-8', errors='replace')
                self.output = self.output[pos + 1:]
                self.logger(string)
                self.string += string
                self.string += '\n'
            return self

    def __init__(self, parent: 'GuestMock', config: Optional[str], rootdir: Optional[str]):
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
        command.append("--plugin-option=tmt:workdir_root=" + shlex.quote(str(self.parent.workdir_root)))
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

        # We need to wait until mock shell is ready. That is when it prints the
        # prompt on its stdout.
        # Meanwhile we want to log all the content from stderr.
        #
        # Failure to launch mock shell is detected by two ways: either .poll()
        # returns a the exit code number or mock shell outputs an empty string
        # to its stdout, while the process is not yet finished.
        mock_shell_result = None
        while True:
            mock_shell_result = self.mock_shell.poll()
            if mock_shell_result is not None:
                break
            events = self.epoll.poll()
            if len(events) == 1 and events[0][0] == self.mock_shell_stdout_fd:
                if not self.mock_shell.stdout.read():
                    mock_shell_result = self.mock_shell.wait()
                # shell is ready
                break
            for fileno, _ in events:
                if fileno == self.mock_shell_stderr_fd:
                    for line in self.mock_shell.stderr.readlines():
                        self.parent._logger.debug("err", line.rstrip(), 'yellow', level = 0)

        if mock_shell_result is not None:
            raise tmt.utils.ProvisionError("Failed to launch mock shell: exited {}".format(mock_shell_result))

        self.parent.verbose("Mock shell is ready")

        # We do not expect these commands to fail.
        self.mock_shell.stdin.write("rm -rf /tmp/stdout /tmp/stderr /tmp/returncode\n")
        self.mock_shell.stdin.write("mkfifo /tmp/stdout /tmp/stderr /tmp/returncode\n")
        self.mock_shell.stdin.flush()

        loop = 2
        while loop != 0 and self.mock_shell.poll() is None:
            events = self.epoll.poll()
            for fileno, _ in events:
                if fileno == self.mock_shell_stdout_fd:
                    loop -= 1
                    self.mock_shell.stdout.read()
                    break
        self.mock_shell.stderr.read()

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
        log: Optional[tmt.log.LoggingFunction] = None,
        silent: bool = False,
    ):
        """
        Execute the command in a running mock shell for increased speed.
        """

        stdout_stem = "tmp/stdout"
        stderr_stem = "tmp/stderr"
        returncode_stem = "tmp/returncode"

        if self.mock_shell is None:
            self.enter_shell()

        shell_command_components: list[str] = [str(command)]

        if env is not None:
            shell_command_components = [
                *(f"{key}={shlex.quote(value)}" for key, value in env.items()),
                *shell_command_components
            ]

        if cwd is not None:
            shell_command_components = [
                "(", f"cd {shlex.quote(str(cwd))}", "&&", *shell_command_components, ")"
            ]

        shell_command_components = [
            *shell_command_components,
            f"1>/{stdout_stem} 2>/{stderr_stem}; echo $?>/{returncode_stem}"
        ]

        shell_command = ' '.join(shell_command_components) + "\n"

        self.parent.verbose("Executing inside mock shell", shell_command[:-1])

        io_flags: int = os.O_RDONLY | os.O_NONBLOCK
        with (io.FileIO(os.open(str(self.root_path / stdout_stem), io_flags)) as stdout_io,
              io.FileIO(os.open(str(self.root_path / stderr_stem), io_flags)) as stderr_io,
              io.FileIO(os.open(str(self.root_path / returncode_stem), io_flags)) as returncode_io):
            stdout_fd = stdout_io.fileno()
            stderr_fd = stderr_io.fileno()
            returncode_fd = returncode_io.fileno()

            self.epoll.register(stdout_fd, select.EPOLLIN)
            self.epoll.register(stderr_fd, select.EPOLLIN)
            self.epoll.register(returncode_fd, select.EPOLLIN)

            self.mock_shell.stdin.write(shell_command)
            self.mock_shell.stdin.flush()

            logger = self.parent._logger
            output_logger: tmt.log.LoggingFunction = (log or logger.debug) if not silent else logger.debug

            stdout = MockShell.Stream(lambda text: output_logger("out", text, 'yellow', level = 0))
            stderr = MockShell.Stream(lambda text: output_logger("err", text, 'yellow', level = 0))
            returncode = None

            while self.mock_shell.poll() is None:
                events = self.epoll.poll()
                # The command is finished when mock shell prints a newline on its
                # stdout. We want to break loop after we handled all the other
                # epoll events because the event ordering is not guaranteed.
                if len(events) == 1 and events[0][0] == self.mock_shell_stdout_fd:
                    self.mock_shell.stdout.read()
                    break
                for fileno, _ in events:
                    # Whatever we sent on mock shell's input it prints on the stderr
                    # so just disard it.
                    if fileno == self.mock_shell_stderr_fd:
                        self.mock_shell.stderr.read()
                    elif fileno == stdout_fd:
                        content = os.read(stdout_fd, 128)
                        stdout += content
                        if not content:
                            self.epoll.unregister(stdout_fd)
                    elif fileno == stderr_fd:
                        content = os.read(stderr_fd, 128)
                        stderr += content
                        if not content:
                            self.epoll.unregister(stderr_fd)
                    elif fileno == returncode_fd:
                        content = os.read(returncode_fd, 16)
                        if not content:
                            self.epoll.unregister(returncode_fd)
                        else:
                            returncode = int(content.decode("utf-8").strip())

            stdout = stdout.string
            stderr = stderr.string

            if returncode is None:
                raise tmt.utils.RunError(
                    f"Invalid state when executing command '{friendly_command or shell_command}'.",
                    command,
                    127,
                    stdout=stdout,
                    stderr=stderr,
                )
            elif returncode != 0:
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

        self.assert_feeling_safe("1.58", "The 'mock' provision plugin")

        if data.hardware and data.hardware.constraint:
            self.warn("The 'mock' provision plugin does not support hardware requirements.")

        self._guest = GuestMock(logger=self._logger, data=data, name=self.name, parent=self.step)
        self._guest.setup()
