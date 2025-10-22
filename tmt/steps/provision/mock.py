import fcntl
import functools
import io
import os
import select
import shlex
import subprocess
from collections.abc import Generator
from types import TracebackType
from typing import Any, Callable, Optional, Union, cast

import tmt
import tmt.base
import tmt.log
import tmt.steps
import tmt.steps.provision
import tmt.utils
from tmt._compat.typing import Self
from tmt.container import container, field
from tmt.utils import Command, OnProcessEndCallback, OnProcessStartCallback, Path, ShellScript
from tmt.utils.wait import Waiting


@functools.cache
def mock_config(root: Optional[str]) -> dict[str, Any]:
    try:
        import mockbuild.config

    except ImportError as error:
        raise tmt.utils.GeneralError("Could not import mockbuild.config package.") from error

    return cast(dict[str, Any], mockbuild.config.simple_load_config(root if root else 'default'))


@container
class MockGuestData(tmt.steps.provision.GuestData):
    root: Optional[str] = field(
        default=None,
        option=('-r', '--root'),
        metavar='ROOT',
        help="""
             Mock chroot configuration file.
             The `--root` flag to be passed to the mock process.
             """,
    )
    rootdir: Optional[Path] = field(
        default=None,
        option=('--rootdir'),
        metavar='ROOTDIR',
        help='The path for where the chroot should be built.',
        normalize=tmt.utils.normalize_path,
    )


@container
class ProvisionMockData(MockGuestData, tmt.steps.provision.ProvisionStepData):
    pass


class MockShell:
    # Lazy object that collects chunks of bytes and decodes them when a
    # newline is encountered
    class Stream:
        def __init__(self, logger: Callable[[str], None]):
            self.logger = logger
            self.output = b''
            self.string = ''

        def __iadd__(self, content: bytes) -> Self:
            self.output += content
            while True:
                pos = self.output.find(b'\n')
                if pos == -1:
                    break
                string = self.output[:pos].decode('utf-8', errors='replace')
                self.output = self.output[pos + 1 :]
                self.logger(string)
                self.string += string
                self.string += '\n'
            return self

    class ManagedEpollFd:
        def __init__(self, epoll: 'select.epoll', fd: int) -> None:
            self.epoll = epoll
            self.fd: Optional[int] = fd

        def __enter__(self) -> 'MockShell.ManagedEpollFd':
            assert self.fd is not None
            self.epoll.register(self.fd, select.EPOLLIN)
            return self

        def try_unregister(self) -> None:
            if self.fd is not None:
                self.epoll.unregister(self.fd)
                self.fd = None

        def __exit__(
            self,
            exc_type: Optional[type[BaseException]],
            exc_value: Optional[BaseException],
            exc_traceback: Optional[TracebackType],
        ) -> None:
            self.try_unregister()

    def __init__(self, parent: 'GuestMock', root: Optional[str], rootdir: Optional[Path]):
        self.parent = parent
        self.root = root
        self.rootdir = rootdir
        self.mock_shell: Optional[subprocess.Popen[str]] = None

        # `select.epoll` is not available on non-Linux platforms.
        # The `ruff` linter complains but for no good reason, so we silence it.
        self.epoll: Optional['select.epoll'] = None  # noqa: UP037

    def __del__(self) -> None:
        self.exit_shell()

    def exit_shell(self) -> None:
        if self.mock_shell is not None:
            self.parent.verbose('mock', 'Exiting shell...', color='blue', level=2)
            if self.epoll is not None:
                self.epoll.close()
                self.epoll = None
            self.mock_shell.communicate()
            self.mock_shell = None
            self.parent.verbose('mock', 'Exited shell.', color='blue', level=2)

    def enter_shell(self) -> None:
        command = self.parent.mock_command_prefix.to_popen()
        command.append('-q')

        # TODO should networking be configurable?
        command.append('--enable-network')

        # Bind-mounting can be an easy way to implement push/pull.
        # Currently we do not use it.
        """
        command.append('--enable-plugin=bind_mount')
        command.append(
            '--plugin-option=bind_mount:dirs=['
            f'("{shlex.quote(str(self.parent.run_workdir))}", '
            f'"{shlex.quote(str(self.parent.run_workdir))}")'
            ']'
        )
        """

        command.append('--shell')

        self.parent.verbose('mock', 'Entering shell.', color='blue', level=2)
        self.parent.debug('mock', f'Command line arguments: {command}.', color='blue')
        self.mock_shell = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.epoll = select.epoll()

        assert self.mock_shell.stdout is not None
        assert self.mock_shell.stderr is not None
        assert self.mock_shell.stdin is not None
        assert self.epoll is not None

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
                        self.parent._logger.debug('err', line.rstrip(), 'yellow')

        if mock_shell_result is not None:
            raise tmt.utils.ProvisionError(
                f'Failed to launch mock shell: exited {mock_shell_result}.'
            )

        self.parent.verbose('mock', 'Shell is ready.', color='blue', level=3)

        # We do not expect these commands to fail.
        self.mock_shell.stdin.write('rm -rf /srv/tmt-mock\n')
        self.mock_shell.stdin.write('mkdir /srv/tmt-mock\n')
        self.mock_shell.stdin.write(
            'mkfifo'
            ' /srv/tmt-mock/stdout'
            ' /srv/tmt-mock/stderr'
            ' /srv/tmt-mock/returncode'
            ' /srv/tmt-mock/filesync'
            '\n'
        )
        self.mock_shell.stdin.write('chmod a+rw /srv/tmt-mock/filesync\n')
        self.mock_shell.stdin.flush()

        # Wait until the previous commands finished.
        loop = 4
        while loop != 0 and self.mock_shell.poll() is None:
            events = self.epoll.poll()
            for fileno, _ in events:
                if fileno == self.mock_shell_stdout_fd:
                    loop -= 1
                    self.mock_shell.stdout.read()
                    break
        self.mock_shell.stderr.read()

    def _spawn_command(
        self,
        command: Command,
        *,
        cwd: Optional[Path] = None,
        env: Optional[tmt.utils.Environment] = None,
        friendly_command: Optional[str] = None,
        log: Optional[tmt.log.LoggingFunction] = None,
        silent: bool = False,
        logger: tmt.log.Logger,
        join: Optional[bool] = None,
        timeout: Optional[int] = None,
        **kwargs: Any,
    ) -> Generator[tuple[str, str]]:
        """
        Execute the command in a running mock shell for increased speed.
        """

        assert self.mock_shell is not None

        if kwargs is not None and len(kwargs) != 0:
            logger.debug(
                'mock',
                f'execute: unrecognized keyword arguments: {", ".join(kwargs.keys())}.',
                color='blue',
            )

        stdout_stem = 'srv/tmt-mock/stdout'
        stderr_stem = 'srv/tmt-mock/stderr'
        returncode_stem = 'srv/tmt-mock/returncode'

        # The friendly command version would be emitted only when we were not
        # asked to be quiet.
        if not silent and friendly_command:
            (log or logger.verbose)('cmd', friendly_command, color='yellow', level=2)

        # Fail nicely if the working directory does not exist.
        if cwd:
            chroot_cwd = self.parent.root_path / (
                cwd.relative_to('/') if cwd.is_absolute() else cwd
            )
            if not chroot_cwd.exists():
                raise tmt.utils.GeneralError(
                    f"The working directory '{chroot_cwd}' does not exist."
                )

        shell_command_components: list[str] = [str(command)]

        if env is not None:
            shell_command_components = [
                *(f'{key}={shlex.quote(value)}' for key, value in env.items()),
                *shell_command_components,
            ]

        if cwd is not None:
            shell_command_components = [
                '(',
                f'cd {shlex.quote(str(cwd))}',
                '&&',
                *shell_command_components,
                ')',
            ]

        shell_command_components = [
            *shell_command_components,
            f'1>/{stdout_stem}',
            f'2>/{stderr_stem}' if not join else '2>&1',
            ';',
            f'echo $?>/{returncode_stem}',
        ]

        shell_command = ' '.join(shell_command_components) + '\n'

        logger.debug('mock', f'Executing shell command: {shell_command[:-1]}', color='blue')

        io_flags: int = os.O_RDONLY | os.O_NONBLOCK
        with (
            io.FileIO(os.open(str(self.parent.root_path / stdout_stem), io_flags)) as stdout_io,
            io.FileIO(os.open(str(self.parent.root_path / stderr_stem), io_flags)) as stderr_io,
            io.FileIO(
                os.open(str(self.parent.root_path / returncode_stem), io_flags)
            ) as returncode_io,
        ):
            stdout_fd = stdout_io.fileno()
            stderr_fd = stderr_io.fileno()
            returncode_fd = returncode_io.fileno()

            assert self.epoll is not None
            assert self.mock_shell is not None
            assert self.mock_shell.stdin is not None
            assert self.mock_shell.stdout is not None
            assert self.mock_shell.stderr is not None

            with (
                MockShell.ManagedEpollFd(self.epoll, stdout_fd) as stdout_epoll,
                MockShell.ManagedEpollFd(self.epoll, stderr_fd) as stderr_epoll,
                MockShell.ManagedEpollFd(self.epoll, returncode_fd) as returncode_epoll,
            ):
                self.mock_shell.stdin.write(shell_command)
                self.mock_shell.stdin.flush()

                # For command output logging, use either the given logging callback, or
                # use the given logger & emit to verbose log.
                # NOTE Command.run uses debug, not verbose.
                output_logger: tmt.log.LoggingFunction = (
                    (log or logger.verbose) if not silent else logger.verbose
                )

                stream_out = MockShell.Stream(
                    lambda text: output_logger('out', text, 'yellow', level=3)
                )
                stream_err = MockShell.Stream(
                    lambda text: output_logger('err', text, 'yellow', level=3)
                )
                returncode = None

                yield  # type: ignore[misc]

                while self.mock_shell.poll() is None:
                    events = self.epoll.poll(timeout=timeout)

                    if len(events) == 0:
                        # TODO
                        # kill the process spawned inside the mock shell
                        pass

                    # The command is finished when mock shell prints a newline on its
                    # stdout. We want to break loop after we handled all the other
                    # epoll events because the event ordering is not guaranteed.
                    if len(events) == 1 and events[0][0] == self.mock_shell_stdout_fd:
                        self.mock_shell.stdout.read()
                        break
                    for fileno, _ in events:
                        # Whatever we sent on mock shell's input it prints on the stderr
                        # so just discard it.
                        if fileno == self.mock_shell_stderr_fd:
                            self.mock_shell.stderr.read()
                        elif fileno == stdout_fd:
                            content = os.read(stdout_fd, 128)
                            stream_out += content
                            if not content:
                                stdout_epoll.try_unregister()
                        elif fileno == stderr_fd:
                            content = os.read(stderr_fd, 128)
                            stream_err += content
                            if not content:
                                stderr_epoll.try_unregister()
                        elif fileno == returncode_fd:
                            content = os.read(returncode_fd, 16)
                            if not content:
                                returncode_epoll.try_unregister()
                            else:
                                returncode = int(content.decode('utf-8').strip())

                stdout = stream_out.string
                stderr = stream_err.string

                if returncode is None:
                    raise tmt.utils.RunError(
                        'Invalid state when executing command '
                        f"'{friendly_command or shell_command}'.",
                        command,
                        127,
                        stdout=stdout,
                        stderr=stderr,
                    )
                if returncode != 0:
                    raise tmt.utils.RunError(
                        f"Command '{friendly_command or shell_command}' returned {returncode}.",
                        command,
                        returncode,
                        stdout=stdout,
                        stderr=stderr,
                    )
                yield (stdout, stderr)

    def execute(self, *args: Any, **kwargs: Any) -> tuple[str, str]:
        process = self._spawn_command(*args, **kwargs)
        next(process)
        return next(process)


class GuestMock(tmt.Guest):
    """
    Mock environment
    """

    _data_class = MockGuestData
    root: Optional[str] = None
    rootdir: Optional[Path] = None

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

        self.mock_command_prefix = Command('mock')
        if self.root is not None:
            self.mock_command_prefix += Command('-r', self.root)
        if self.rootdir is not None:
            self.mock_command_prefix += Command('--rootdir', self.rootdir)
        root_path = (
            (self.mock_command_prefix + Command('--print-root-path'))
            .run(cwd=None, logger=self._logger)
            .stdout
        )
        assert root_path is not None
        self.root_path = Path(root_path.rstrip())

        self.mock_shell = MockShell(parent=self, root=self.root, rootdir=self.rootdir)

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

        raise NotImplementedError("Ansible is not currently supported.")

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
        on_process_end: Optional[OnProcessEndCallback] = None,
        **kwargs: Any,
    ) -> tmt.utils.CommandOutput:
        """
        Execute command inside mock
        """

        if self.mock_shell.mock_shell is None:
            self.mock_shell.enter_shell()

        actual_command = command if isinstance(command, Command) else command.to_shell_command()
        if on_process_start:
            assert self.mock_shell.mock_shell is not None  # narrow type

            # ignore[arg-type]: `on_process_start` expects `Popen[bytes]`,
            # `mock_shell` is `Popen[str]`. Callbacks are not supposed to
            # communicate with the process, but it's not written down anywhere.
            # Tracked in https://github.com/teemtee/tmt/issues/4097
            on_process_start(
                actual_command,
                self.mock_shell.mock_shell,  # type: ignore[arg-type]
                self._logger,
            )
        command_output = tmt.utils.CommandOutput(
            *self.mock_shell.execute(
                actual_command,
                cwd=cwd,
                env=env,
                friendly_command=friendly_command or str(command),
                logger=self._logger,
                **kwargs,
            )
        )
        if on_process_end is not None:
            try:
                on_process_end(
                    actual_command,
                    self.mock_shell.mock_shell,  # type: ignore[arg-type]
                    command_output,
                    self._logger,
                )

            except Exception as exc:
                tmt.utils.show_exception_as_warning(
                    exception=exc,
                    message=f'On-process-end callback {on_process_end.__name__} failed.',
                    logger=self._logger,
                )
        return command_output

    def reboot(
        self,
        hard: bool = False,
        command: Optional[Union[Command, ShellScript]] = None,
        waiting: Optional[Waiting] = None,
    ) -> bool:
        # TODO refresh shell
        self.debug(f"Doing nothing to reboot guest '{self.primary_address}'.")
        return False

    def remove(self) -> None:
        """
        Currently do not prune the mock chroot, that may be undesirable.
        """
        # TODO consider whether we really want this
        pass

    def _do_scrub(self) -> None:
        """
        This is the actual implementation of `remove`.
        """
        (self.mock_command_prefix + Command('--scrub=all')).run(cwd=None, logger=self._logger)

    def suspend(self) -> None:
        self.mock_shell.exit_shell()

    def stop(self) -> None:
        self.mock_shell.exit_shell()

    def push(
        self,
        source: Optional[Path] = None,
        destination: Optional[Path] = None,
        options: Optional[tmt.steps.provision.TransferOptions] = None,
        superuser: bool = False,
    ) -> None:
        """
        Push content into the mock chroot via a pipe at /srv/tmt-mock/filesync.
        For directories we use tar.
        For files we use cp / install.
        Compress option is ignored, it only slows down the execution.
        Create destination option is ignored, there were problems with workdir.
        """
        # TODO chmod permissions for tar
        options = options or tmt.steps.provision.DEFAULT_PUSH_OPTIONS
        excludes = Command()
        permissions = Command()
        if options.chmod is not None:
            permissions = Command('-m', f'{options.chmod:03o}')
        for exclude in options.exclude:
            excludes += Command(f'--exclude={exclude}')
        source = source or self.plan_workdir
        destination = destination or source

        if source.is_dir():
            self.mock_shell.execute(Command('mkdir', '-p', str(destination)), logger=self._logger)
            p = self.mock_shell._spawn_command(
                Command('tar', '-C', str(destination), '-xf', '/srv/tmt-mock/filesync') + excludes,
                logger=self._logger,
            )
            next(p)
            (
                Command(
                    'tar',
                    '-C',
                    str(source),
                    '-cf',
                    str(self.root_path / 'srv/tmt-mock/filesync'),
                    '.',
                )
            ).run(cwd=None, logger=self._logger)
            next(p)
        else:
            self.mock_shell.execute(
                Command('mkdir', '-p', str(destination.parent)), logger=self._logger
            )
            p = self.mock_shell._spawn_command(
                Command('install', '/srv/tmt-mock/filesync', str(destination)) + permissions,
                logger=self._logger,
            )
            next(p)
            Command('cp', str(source), str(self.root_path / 'srv/tmt-mock/filesync')).run(
                cwd=None, logger=self._logger
            )
            next(p)

    def pull(
        self,
        source: Optional[Path] = None,
        destination: Optional[Path] = None,
        options: Optional[tmt.steps.provision.TransferOptions] = None,
    ) -> None:
        """
        Pull content from the mock chroot via a pipe at /srv/tmt-mock/filesync.
        For directories we use tar.
        For files we use cp / install.
        Compress option is ignored, it only slows down the execution.
        """
        # TODO chmod permissions for tar
        options = options or tmt.steps.provision.DEFAULT_PULL_OPTIONS
        excludes = Command()
        permissions = Command()
        if options.chmod is not None:
            permissions = Command('-m', f'{options.chmod:03o}')
        for exclude in options.exclude:
            excludes += Command(f'--exclude={exclude}')
        source = source or self.plan_workdir
        destination = destination or source
        source_in_chroot = self.root_path / source.relative_to('/')

        if not source_in_chroot.exists():
            if options.create_destination:
                Command('mkdir', '-p', str(destination)).run(cwd=None, logger=self._logger)
        elif source_in_chroot.is_dir():
            if options.create_destination:
                Command('mkdir', '-p', str(destination)).run(cwd=None, logger=self._logger)
            p = self.mock_shell._spawn_command(
                Command('tar', '-C', str(source), '-cf', '/srv/tmt-mock/filesync', '.'),
                logger=self._logger,
            )
            next(p)
            (
                Command(
                    'tar',
                    '-C',
                    str(destination),
                    '-xf',
                    str(self.root_path / 'srv/tmt-mock/filesync'),
                )
                + excludes
            ).run(cwd=None, logger=self._logger)
            next(p)
        else:
            if options.create_destination:
                Command('mkdir', '-p', str(destination.parent)).run(cwd=None, logger=self._logger)
            p = self.mock_shell._spawn_command(
                Command('cp', str(source), '/srv/tmt-mock/filesync'), logger=self._logger
            )
            next(p)
            (
                Command('install', str(self.root_path / 'srv/tmt-mock/filesync'), str(destination))
                + permissions
            ).run(cwd=None, logger=self._logger)
            next(p)


@tmt.steps.provides_method('mock')
class ProvisionMock(tmt.steps.provision.ProvisionPlugin[ProvisionMockData]):
    """
    Use the mock tool for the test execution.

    Tests will be executed inside a mock buildroot.

    .. warning::

        This plugin requires the ``--feeling-safe`` option or
        the ``TMT_FEELING_SAFE=1`` environment variable defined.
        While it is roughly as safe as ``container`` provisioning,
        the plugin still bind-mounts the test directory.

    Using the plugin:

    .. code-block:: yaml

        provision:
            how: mock
            config: fedora-rawhide-x86_64

    .. code-block:: shell

        provision --how mock --config fedora-rawhide-x86_64

    .. note::

        Neither hard nor soft reboot is supported.
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
        # If this provisioning is selected, then we force the use of `mock-` package manager.
        # NOTE use a global variable instead?
        tmt.package_managers.find_package_manager(
            f"mock-{mock_config(data.root)['package_manager']}"
        ).probe_command = tmt.utils.Command('/usr/bin/true')

        # NOTE any better ideas?
        data.primary_address = (str(data.root) if data.root is not None else '<default>') + (
            f'@{data.rootdir}' if data.rootdir is not None else ''
        )

        data.show(verbose=self.verbosity_level, logger=self._logger)

        self.assert_feeling_safe("1.58", "The 'mock' provision plugin")

        if data.hardware and data.hardware.constraint:
            self.warn("The 'mock' provision plugin does not support hardware requirements.")

        self._guest = GuestMock(
            logger=self._logger,
            data=data,
            name=self.name,
            parent=self.step,
        )
        self._guest.setup()
