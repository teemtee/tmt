import abc
import ast
import contextlib
import dataclasses
import enum
import functools
import hashlib
import os
import re
import secrets
import shlex
import shutil
import signal as _signal
import string
import subprocess
import threading
from collections.abc import Iterable, Iterator, Sequence
from shlex import quote
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Literal,
    NewType,
    Optional,
    TypeVar,
    Union,
    cast,
    overload,
)

import fmf.utils

import tmt
import tmt.ansible
import tmt.hardware
import tmt.log
import tmt.package_managers
import tmt.steps
import tmt.steps.scripts
import tmt.utils
import tmt.utils.wait
from tmt._compat.typing import Self
from tmt.ansible import (
    GuestAnsible,
    normalize_guest_ansible,
)
from tmt.container import (
    SerializableContainer,
    SpecBasedContainer,
    container,
    field,
    key_to_option,
)
from tmt.package_managers import (
    FileSystemPath,
    Package,
)
from tmt.utils import (
    Command,
    GeneralError,
    OnProcessEndCallback,
    OnProcessStartCallback,
    Path,
    ProvisionError,
    ShellScript,
    configure_constant,
    effective_workdir_root,
)
from tmt.utils.hints import get_hint
from tmt.utils.wait import Deadline, Waiting

if TYPE_CHECKING:
    import tmt.base.core
    from tmt._compat.typing import TypeAlias
    from tmt.steps.provision import Provision, ProvisionPlugin, ProvisionStepDataT


T = TypeVar('T')

#: How many seconds to wait for a connection to succeed after guest boot.
#: This is the default value tmt would use unless told otherwise.
DEFAULT_CONNECT_TIMEOUT = 2 * 60

#: How many seconds to wait for a connection to succeed after guest boot.
#: This is the effective value, combining the default and optional envvar,
#: ``TMT_CONNECT_TIMEOUT``.
CONNECT_TIMEOUT: int = configure_constant(DEFAULT_CONNECT_TIMEOUT, 'TMT_CONNECT_TIMEOUT')

# When waiting for guest to connect, try re-connecting every
# this many seconds.
CONNECT_WAIT_TICK = 1
CONNECT_WAIT_TICK_INCREASE = 1.0


def default_connect_waiting() -> Waiting:
    """
    Create default waiting context for connecting to the guest.
    """

    return Waiting(
        deadline=Deadline.from_seconds(CONNECT_TIMEOUT),
        tick=CONNECT_WAIT_TICK,
        tick_increase=CONNECT_WAIT_TICK_INCREASE,
    )


#: How many seconds to wait for a connection to succeed after guest reboot.
#: This is the default value tmt would use unless told otherwise.
DEFAULT_REBOOT_TIMEOUT: int = 10 * 60

#: How many seconds to wait for a connection to succeed after guest reboot.
#: This is the effective value, combining the default and optional envvar,
#: ``TMT_REBOOT_TIMEOUT``.
REBOOT_TIMEOUT: int = configure_constant(DEFAULT_REBOOT_TIMEOUT, 'TMT_REBOOT_TIMEOUT')


def default_reboot_waiting() -> Waiting:
    """
    Create default waiting context for guest reboots.
    """

    return Waiting(deadline=Deadline.from_seconds(REBOOT_TIMEOUT))


# When waiting for guest to recover from reboot, try re-connecting every
# this many seconds.
RECONNECT_WAIT_TICK = 5
RECONNECT_WAIT_TICK_INCREASE = 1.0


def default_reconnect_waiting() -> Waiting:
    """
    Create default waiting context for guest reconnect.
    """

    return Waiting(
        deadline=Deadline.from_seconds(REBOOT_TIMEOUT),
        tick=RECONNECT_WAIT_TICK,
        tick_increase=RECONNECT_WAIT_TICK_INCREASE,
    )


# Types for things Ansible can execute
ANSIBLE_COLLECTION_PLAYBOOK_PATTERN = re.compile(r'[a-zA-z0-9_]+\.[a-zA-z0-9_]+\.[a-zA-z0-9_]+')

AnsiblePlaybook: 'TypeAlias' = Path
AnsibleCollectionPlaybook = NewType('AnsibleCollectionPlaybook', str)
AnsibleApplicable = Union[AnsibleCollectionPlaybook, AnsiblePlaybook]


def configure_ssh_options() -> tmt.utils.RawCommand:
    """
    Extract custom SSH options from environment variables
    """

    options: tmt.utils.RawCommand = []

    for name, value in os.environ.items():
        match = re.match(r'TMT_SSH_([a-zA-Z_]+)', name)

        if not match:
            continue

        options.append(f'-o{match.group(1).title().replace("_", "")}={value}')

    return options


#: Default SSH options.
#: This is the default set of SSH options tmt would use for all SSH connections.
DEFAULT_SSH_OPTIONS: tmt.utils.RawCommand = [
    '-oForwardX11=no',
    '-oStrictHostKeyChecking=no',
    '-oUserKnownHostsFile=/dev/null',
    # Try establishing connection multiple times before giving up.
    '-oConnectionAttempts=5',
    '-oConnectTimeout=60',
    # Prevent ssh from disconnecting if no data has been
    # received from the server for a long time (#868).
    '-oServerAliveInterval=5',
    '-oServerAliveCountMax=60',
]

#: Base SSH options.
#: This is the base set of SSH options tmt would use for all SSH
#: connections. It is a combination of the default SSH options and those
#: provided by environment variables.
#: SSH options are processed in order. Options provided via environment
#: variables take precedence over default values. For options that set
#: a specific value (e.g., ``ServerAliveInterval``), the first occurrence
#: takes precedence. For simple on/off flags (e.g., ``-v``/``-q``), the last one wins.
#: Identity files (``-i``) are all considered in order.
BASE_SSH_OPTIONS: tmt.utils.RawCommand = configure_ssh_options() + DEFAULT_SSH_OPTIONS

#: SSH master socket path is limited to this many characters.
#:
#: * UNIX socket path is limited to either 108 or 104 characters, depending
#:   on the platform. See `man 7 unix` and/or kernel sources, for example.
#: * SSH client processes may create paths with added "connection hash"
#:   when connecting to the master, that is a couple of characters we need
#:   space for.
#:
SSH_MASTER_SOCKET_LENGTH_LIMIT = 104 - 20

#: A minimal number of characters of guest ID hash used by
#: :py:func:`_socket_path_hash` when looking for a free SSH socket
#: filename.
SSH_MASTER_SOCKET_MIN_HASH_LENGTH = 4

#: A maximal number of characters of guest ID hash used by
#: :py:func:`_socket_path_hash` when looking for a free SSH socket
#: filename.
SSH_MASTER_SOCKET_MAX_HASH_LENGTH = 64

#: Default username to use in SSH connections.
DEFAULT_USER = 'root'


@overload
def _socket_path_trivial(
    *,
    socket_dir: Path,
    guest_id: str,
    limit_size: Literal[True] = True,
    logger: tmt.log.Logger,
) -> Optional[Path]:
    pass


@overload
def _socket_path_trivial(
    *,
    socket_dir: Path,
    guest_id: str,
    limit_size: Literal[False] = False,
    logger: tmt.log.Logger,
) -> Path:
    pass


def _socket_path_trivial(
    *,
    socket_dir: Path,
    guest_id: str,
    limit_size: bool = True,
    logger: tmt.log.Logger,
) -> Optional[Path]:
    """
    Generate SSH socket path using guest IDs
    """

    socket_path = socket_dir / f'{guest_id}.socket'

    logger.debug(f"Possible SSH master socket path '{socket_path}' (trivial method).", level=4)

    if not limit_size:
        return socket_path

    return socket_path if len(str(socket_path)) < SSH_MASTER_SOCKET_LENGTH_LIMIT else None


def _socket_path_hash(
    *,
    socket_dir: Path,
    guest_id: str,
    limit_size: bool = True,
    logger: tmt.log.Logger,
) -> Optional[Path]:
    """
    Generate SSH socket path using a hash of guest IDs.

    Generates less readable, but hopefully shorter and therefore
    acceptable filename. We try to make sure we create unique
    names for sockets, names that are not shared by multiple
    guests, and we try to make them reasonably short.
    """

    # We're using hashing function which should, in theory, be prone to
    # conflicts enough for us to never hit a collision. However, we cannot
    # rule out the chance of getting same hash for different guests, and
    # letting one socket serve two different guests is extremely hard to
    # debug.
    #
    # Therefore we try to avoid the collision by not using the
    # full size of the hash, just its substring - if we really reach the
    # point where more than one guest yields the same hash, the first
    # would use N starting characters for its socket, the second would
    # use N+1 starting characters, and so on.
    #
    # For each potential socket path, a "reservation" file is used as
    # a placeholder: once atomically created, no other guest can grab
    # the given socket path.
    for i in range(SSH_MASTER_SOCKET_MIN_HASH_LENGTH, SSH_MASTER_SOCKET_MAX_HASH_LENGTH):
        digest = hashlib.sha256(guest_id.encode()).hexdigest()[:i]

        socket_path = socket_dir / f'{digest}.socket'
        socket_reservation_path = f'{socket_path}.reservation'

        logger.debug(f"Possible SSH master socket path '{socket_path}' (hash method).", level=4)

        if limit_size and len(str(socket_path)) >= SSH_MASTER_SOCKET_LENGTH_LIMIT:
            return None

        # O_CREAT | O_EXCL means "atomic create-and-fail-if-exists".
        # It's pretty much what `tempfile` does, but we need to control
        # the full name, not just a prefix or suffix.
        try:
            fd = os.open(socket_reservation_path, flags=os.O_CREAT | os.O_EXCL)

        except FileExistsError:
            logger.debug(f"Proposed SSH socket '{socket_path}' already reserved.", level=4)
            continue

        # Successfully reserved the socket path, we can close the
        # reservation file & return the actual path.
        os.close(fd)

        return socket_path

    return None


#: A pattern to extract ``btime`` from ``/proc/stat`` file.
STAT_BTIME_PATTERN = re.compile(r'btime\s+(\d+)')


@container
class TransferOptions:
    """Options for transferring files to/from the guest."""

    #: Apply permissions to the destination files
    chmod: Optional[int] = None

    #: Enable compression during transfer
    compress: bool = False

    #: Delete extraneous files from destination directory
    delete: bool = False

    #: Exclude files matching any of these patterns
    exclude: list[str] = field(default_factory=list, normalize=tmt.utils.normalize_string_list)

    #: Copy symlinks as symlinks
    links: bool = False

    #: Preserve file permissions
    preserve_perms: bool = False

    #: Protect file and directory names from interpretation
    protect_args: bool = False

    #: Recurse into directories
    recursive: bool = False

    #: Use relative paths
    relative: bool = False

    #: Ignore symlinks that point outside the source tree
    safe_links: bool = False

    #: Run a ``mkdir -p`` of the destination before doing transfer
    create_destination: bool = False

    def copy(self) -> 'TransferOptions':
        """Create a copy of the options."""

        return dataclasses.replace(self, exclude=self.exclude[:])

    def to_rsync(self) -> list[str]:
        """Convert to rsync command line options."""

        options: list[str] = []

        if self.chmod:
            options.append(f'--chmod={self.chmod:o}')
        if self.compress:
            options.append('-z')
        if self.delete:
            options.append('--delete')
        if self.exclude:
            options += [f'--exclude={pattern}' for pattern in self.exclude]
        if self.links:
            options.append('--links')
        if self.protect_args:
            options.append('-s')
        if self.preserve_perms:
            options.append('-p')
        if self.recursive:
            options.append('-r')
        if self.relative:
            options.append('-R')
        if self.safe_links:
            options.append('--safe-links')

        return options


DEFAULT_PUSH_OPTIONS = TransferOptions(
    protect_args=True,
    relative=True,
    recursive=True,
    compress=True,
    links=True,
    safe_links=True,
    delete=True,
)

DEFAULT_PULL_OPTIONS = TransferOptions(
    protect_args=True,
    relative=True,
    recursive=True,
    compress=True,
    links=True,
    safe_links=True,
)


# Note: returns a static list, but we cannot make it a mere list,
# because `tmt.base.core` needs to be imported and that creates a circular
# import loop.
def essential_ansible_requires() -> list['tmt.base.core.Dependency']:
    """
    Return essential requirements for running Ansible modules
    """

    return [tmt.base.core.DependencySimple('/usr/bin/python3')]


def format_guest_full_name(name: str, role: Optional[str]) -> str:
    """
    Render guest's full name, i.e. name and its role
    """

    if role is None:
        return name

    return f'{name} ({role})'


class RebootMode(enum.Enum):
    #: A software-invoked reboot of the guest. ``reboot`` or
    #: ``shutdown -r now`` kind of reboot.
    SOFT = 'soft'

    #: A software-invoked reboot of the guest userspace.
    #: ``systemd soft-reboot`` kind of reboot.
    #:
    #: See https://www.freedesktop.org/software/systemd/man/latest/systemd-soft-reboot.service.html
    #: for systemd documentation on soft-reboot.
    SYSTEMD_SOFT = 'systemd-soft'

    #: A hardware-invoked reboot of the guest. Power off/power on
    #: kind of reboot.
    HARD = 'hard'


SoftRebootModes = Literal[RebootMode.SOFT, RebootMode.SYSTEMD_SOFT]
HardRebootModes = Literal[RebootMode.HARD]


class RebootModeNotSupportedError(ProvisionError):
    """A requested reboot mode is not supported by the guest"""

    def __init__(
        self,
        message: Optional[str] = None,
        guest: Optional['Guest'] = None,
        mode: RebootMode = RebootMode.SOFT,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        if message is not None:
            pass

        elif guest is not None:
            message = f"Guest '{guest.multihost_name}' does not support {mode.value} reboot."

        else:
            message = f"Guest does not support {mode.value} reboot."

        super().__init__(message, *args, **kwargs)


class BootMark(abc.ABC):
    """
    Fetch and compare "boot mark"

    A "boot mark" is a piece of information identifying a particular
    guest boot, and it changes after a reboot. It is used to detect
    whether a reboot has already happened or not.
    """

    @classmethod
    @abc.abstractmethod
    def fetch(cls, guest: 'Guest') -> str:
        """
        Read and return the current value of the boot mark.
        """

        raise NotImplementedError

    @classmethod
    def check(cls, guest: 'Guest', current: Optional[str]) -> None:
        """
        Read the new boot mark, and compare it with the current one.

        Intended to be called as :py:func:`tmt.utils.wait.wait`
        callback.

        :raises tmt.utils.wait.WaitingIncompleteError: when the guest
            is not yet ready after a reboot, e.g. because the boot mark
            is not updated yet.
        """

        try:
            new_boot_mark = cls.fetch(guest)

            if new_boot_mark != current:
                # When the mark changes, we are done with the reboot
                return

            # Same boot mark, reboot didn't happen yet, retrying
            raise tmt.utils.wait.WaitingIncompleteError

        except tmt.utils.RunError as error:
            guest.debug('Failed to fetch boot mark.')

            raise tmt.utils.wait.WaitingIncompleteError from error


class BootMarkSystemdSoftRebootCount(BootMark):
    """
    Use soft reboot count a boot mark.
    """

    @classmethod
    def fetch(cls, guest: 'Guest') -> str:
        stdout = guest.execute(
            Command('systemctl', 'show', '--value', '--property', 'SoftRebootsCount'), silent=True
        ).stdout

        assert stdout

        return stdout.strip()


class BootMarkBootTime(BootMark):
    """
    Use boot time as a boot mark.
    """

    @classmethod
    def fetch(cls, guest: 'Guest') -> str:
        stdout = guest.execute(Command("cat", "/proc/stat")).stdout

        assert stdout

        match = STAT_BTIME_PATTERN.search(stdout)

        if match is None:
            raise tmt.utils.ProvisionError('Failed to retrieve boot time from guest')

        return match.group(1)


class GuestCapability(enum.Enum):
    """
    Various Linux capabilities
    """

    # See man 2 syslog:
    #: Read all messages remaining in the ring buffer.
    SYSLOG_ACTION_READ_ALL = 'syslog-action-read-all'
    #: Read and clear all messages remaining in the ring buffer.
    SYSLOG_ACTION_READ_CLEAR = 'syslog-action-read-clear'


@container
class GuestFacts(SerializableContainer):
    """
    Contains interesting facts about the guest.

    Inspired by Ansible or Puppet facts, interesting guest facts tmt
    discovers while managing the guest are stored in this container,
    plus the code performing the discovery of these facts.
    """

    #: Set to ``True`` by the first call to :py:meth:`sync`.
    in_sync: bool = False

    arch: Optional[str] = None
    distro: Optional[str] = None
    kernel_release: Optional[str] = None
    package_manager: Optional['tmt.package_managers.GuestPackageManager'] = field(
        # cast: since the default is None, mypy cannot infere the full type,
        # and reports `package_manager` parameter to be `object`.
        default=cast(Optional['tmt.package_managers.GuestPackageManager'], None)
    )
    bootc_builder: Optional['tmt.package_managers.GuestPackageManager'] = field(
        # cast: since the default is None, mypy cannot infere the full type,
        # and reports `bootc_builder` parameter to be `object`.
        default=cast(Optional['tmt.package_managers.GuestPackageManager'], None)
    )

    has_selinux: Optional[bool] = None
    has_systemd: Optional[bool] = None
    has_rsync: Optional[bool] = None
    is_superuser: Optional[bool] = None
    can_sudo: Optional[bool] = None
    sudo_prefix: Optional[str] = None
    is_ostree: Optional[bool] = None
    is_image_mode: Optional[bool] = None
    is_toolbox: Optional[bool] = None
    toolbox_container_name: Optional[str] = None
    is_container: Optional[bool] = None
    systemd_soft_reboot: Optional[bool] = None

    #: Various Linux capabilities and whether they are permitted to
    #: commands executed on this guest.
    capabilities: dict[GuestCapability, bool] = field(
        default_factory=cast(Callable[[], dict[GuestCapability, bool]], dict),
        serialize=lambda capabilities: (
            {capability.value: enabled for capability, enabled in capabilities.items()}
            if capabilities
            else {}
        ),
        unserialize=lambda raw_value: {
            GuestCapability(raw_capability): enabled
            for raw_capability, enabled in raw_value.items()
        },
    )

    os_release_content: dict[str, str] = field(default_factory=dict)
    lsb_release_content: dict[str, str] = field(default_factory=dict)

    def has_capability(self, cap: GuestCapability) -> bool:
        if not self.capabilities:
            return False

        return self.capabilities.get(cap, False)

    def _execute(self, guest: 'Guest', command: Command) -> Optional[tmt.utils.CommandOutput]:
        """
        Run a command on the given guest, ignoring :py:class:`tmt.utils.RunError`.

        On image mode systems execute the commands immediately.

        :returns: command output if the command quit with a zero exit code,
            ``None`` otherwise.
        """

        try:
            return guest.execute(command, silent=True)

        except tmt.utils.RunError:
            pass

        return None

    def _fetch_keyval_file(self, guest: 'Guest', filepath: Path) -> dict[str, str]:
        """
        Load key/value pairs from a file on the given guest.

        Converts file with ``key=value`` pairs into a mapping. Some values might
        be wrapped with quotes.

        .. code:: shell

           $ cat /etc/os-release
           NAME="Ubuntu"
           VERSION="20.04.5 LTS (Focal Fossa)"
           ID=ubuntu
           ID_LIKE=debian
           ...

        See https://www.freedesktop.org/software/systemd/man/os-release.html for
        more details on syntax of these files.

        :returns: mapping with key/value pairs loaded from ``filepath``, or an
            empty mapping if it was impossible to load the content.
        """

        content: dict[str, str] = {}

        output = self._execute(guest, Command('cat', filepath))

        if not output or not output.stdout:
            return content

        def _iter_pairs() -> Iterator[tuple[str, str]]:
            assert output  # narrow type in a closure
            assert output.stdout  # narrow type in a closure

            line_pattern = re.compile(r'([A-Z][A-Z_0-9]+)=(.*)')

            for line_number, line in enumerate(output.stdout.splitlines(keepends=False), start=1):
                line = line.rstrip()

                if not line or line.startswith('#'):
                    continue

                match = line_pattern.match(line)

                if not match:
                    raise tmt.utils.ProvisionError(
                        f"Cannot parse line {line_number} in '{filepath}' on guest '{guest.name}':"
                        f" {line}"
                    )

                key, value = match.groups()

                if value and value[0] in '"\'':
                    value = ast.literal_eval(value)

                yield key, value

        return dict(_iter_pairs())

    def _probe(self, guest: 'Guest', probes: list[tuple[Command, T]]) -> Optional[T]:
        """
        Find a first successful command.

        :param guest: the guest to run commands on.
        :param probes: list of command/mark pairs.
        :returns: "mark" corresponding to the first command to quit with
            a zero exit code.
        :raises tmt.utils.GeneralError: when no command succeeded.
        """

        for command, outcome in probes:
            if self._execute(guest, command):
                return outcome

        return None

    def _query(self, guest: 'Guest', probes: list[tuple[Command, str]]) -> Optional[str]:
        """
        Find a first successful command, and extract info from its output.

        :param guest: the guest to run commands on.
        :param probes: list of command/pattenr pairs.
        :returns: substring extracted by the first matching pattern.
        :raises tmt.utils.GeneralError: when no command succeeded, or when no
            pattern matched.
        """

        for command, pattern in probes:
            output = self._execute(guest, command)

            if not output or not output.stdout:
                guest.debug('query', f"Command '{command!s}' produced no usable output.")
                continue

            match = re.search(pattern, output.stdout)

            if not match:
                guest.debug('query', f"Command '{command!s}' produced no usable output.")
                continue

            return match.group(1)

        return None

    def _query_arch(self, guest: 'Guest') -> Optional[str]:
        return self._query(guest, [(Command('arch'), r'(.+)')])

    def _query_distro(self, guest: 'Guest') -> Optional[str]:
        # Try some low-hanging fruits first. We already might have the answer,
        # provided by some standardized locations.
        if 'PRETTY_NAME' in self.os_release_content:
            return self.os_release_content['PRETTY_NAME']

        if 'DISTRIB_DESCRIPTION' in self.lsb_release_content:
            return self.lsb_release_content['DISTRIB_DESCRIPTION']

        # Nope, inspect more files.
        return self._query(
            guest,
            [
                (Command('cat', '/etc/redhat-release'), r'(.*)'),
                (Command('cat', '/etc/fedora-release'), r'(.*)'),
            ],
        )

    def _query_kernel_release(self, guest: 'Guest') -> Optional[str]:
        return self._query(guest, [(Command('uname', '-r'), r'(.+)')])

    def _discover_package_manager(
        self,
        guest: 'Guest',
        plugin_classes: Iterable[
            type[tmt.package_managers.PackageManager[tmt.package_managers.PackageManagerEngine]]
        ],
        *,
        debug_label: str,
    ) -> Optional['tmt.package_managers.GuestPackageManager']:
        # Sort available package managers by priority and probe them one by one,
        # break after the first one is detected.

        for package_manager_class in sorted(
            plugin_classes, key=lambda pm: pm.probe_priority, reverse=True
        ):
            if self._execute(guest, package_manager_class.probe_command):
                guest.debug(
                    f'Discovered {debug_label}',
                    package_manager_class.NAME,
                    level=4,
                )
                return package_manager_class.NAME

        return None

    def _query_package_manager(
        self, guest: 'Guest'
    ) -> Optional['tmt.package_managers.GuestPackageManager']:
        return self._discover_package_manager(
            guest,
            plugin_classes=(
                package_manager_class
                for _, package_manager_class in (
                    tmt.package_managers._PACKAGE_MANAGER_PLUGIN_REGISTRY.items()
                )
            ),
            debug_label='package manager',
        )

    def _query_bootc_builder(
        self, guest: 'Guest'
    ) -> Optional['tmt.package_managers.GuestPackageManager']:
        return self._discover_package_manager(
            guest,
            plugin_classes=(
                pm
                for pm in tmt.package_managers._PACKAGE_MANAGER_PLUGIN_REGISTRY.iter_plugins()
                if pm.bootc_builder
            ),
            debug_label='bootc builder',
        )

    def _query_has_selinux(self, guest: 'Guest') -> Optional[bool]:
        """
        Detect whether guest has SELinux and it is enabled.

        For detection ``/sys/fs/selinux/enforce`` is used. This file exists
        only when SELinux is actually available and mounted (regardless of
        enforcing/permissive mode).
        """
        try:
            guest.execute(Command('test', '-e', '/sys/fs/selinux/enforce'), silent=True)
            return True
        except tmt.utils.RunError:
            return False

    def _query_has_systemd(self, guest: 'Guest') -> Optional[bool]:
        """
        Detect whether guest uses systemd.
        For detection we check if systemctl exists and is executable.
        """
        try:
            guest.execute(Command('systemctl', '--version'), silent=True)
            return True
        except tmt.utils.RunError:
            return False

    def _query_systemd_soft_reboot(self, guest: 'Guest') -> Optional[bool]:
        output = self._execute(
            guest,
            (
                ShellScript('systemctl --help | grep -q "soft-reboot"')
                & ShellScript('cat /proc/sys/kernel/random/boot_id')
            ).to_shell_command(),
        )

        return output is not None and output.stdout is not None

    def _query_has_rsync(self, guest: 'Guest') -> Optional[bool]:
        """
        Detect whether ``rsync`` is available.
        """

        try:
            guest.execute(Command('rsync', '--version'), silent=True)

            return True

        except tmt.utils.RunError:
            return False

    def _query_is_superuser(self, guest: 'Guest') -> Optional[bool]:
        output = self._execute(guest, Command('whoami'))

        if output is None or output.stdout is None:
            return None

        return output.stdout.strip() == 'root'

    def _query_can_sudo(self, guest: 'Guest') -> Optional[bool]:
        try:
            guest.execute(Command("sudo", "-n", "true"), silent=True)
        except tmt.utils.RunError:
            # Failed non-interactive sudo, so we can't sudo
            return False
        # Otherwise we may use sudo
        return True

    def _query_sudo_prefix(self, guest: 'Guest') -> Optional[str]:
        # Note: we cannot reuse `is_superuser` or `can_sudo` fact so we just recall the query
        # functions for now
        if self._query_is_superuser(guest):
            # Root user does not need sudo
            return ""
        if self._query_can_sudo(guest):
            return "sudo"
        return ""

    def _query_is_ostree(self, guest: 'Guest') -> Optional[bool]:
        # https://github.com/vrothberg/chkconfig/commit/538dc7edf0da387169d83599fe0774ea080b4a37#diff-562b9b19cb1cd12a7343ce5c739745ebc8f363a195276ca58e926f22927238a5R1334
        output = self._execute(
            guest,
            ShellScript(
                """
                ( [ -e /run/ostree-booted ] || [ -L /ostree ] ) && echo yes || echo no
                """
            ).to_shell_command(),
        )

        if output is None or output.stdout is None:
            return None

        return output.stdout.strip() == 'yes'

    def _query_is_image_mode(self, guest: 'Guest') -> Optional[bool]:
        """
        Detect whether guest is an image mode based system.

        An image mode based system has the image set to a image reference.
        In case ``bootc`` is installed on a non image mode system, it
        reports ``null``.
        """

        image = self._query(
            guest,
            [(ShellScript('sudo bootc status --format yaml').to_shell_command(), r'image: (.+)')],
        )

        # if bootc reports status and the image is not `image: null`, we are in image mode
        if image and image != "null":
            return True

        return False

    def _query_is_toolbox(self, guest: 'Guest') -> Optional[bool]:
        # https://www.reddit.com/r/Fedora/comments/g6flgd/toolbox_specific_environment_variables/
        output = self._execute(
            guest,
            ShellScript('[ -e /run/.toolboxenv ] && echo yes || echo no').to_shell_command(),
        )

        if output is None or output.stdout is None:
            return None

        return output.stdout.strip() == 'yes'

    def _query_toolbox_container_name(self, guest: 'Guest') -> Optional[str]:
        output = self._execute(
            guest,
            ShellScript('[ -e /run/.containerenv ] && echo yes || echo no').to_shell_command(),
        )

        if output is None or output.stdout is None:
            return None

        if output.stdout.strip() == 'no':
            return None

        output = self._execute(guest, Command('cat', '/run/.containerenv'))

        if output is None or output.stdout is None:
            return None

        for line in output.stdout.splitlines():
            if line.startswith('name="'):
                return line[6:-1]

        return None

    def _query_is_container(self, guest: 'Guest') -> Optional[bool]:
        """
        Detect whether guest is a container (running systemd)

        In containers running systemd pid 1 has environment variable ``container`` set
        (e.g. container=podman). See https://systemd.io/CONTAINER_INTERFACE/ for more details.
        """
        output = self._execute(guest, ShellScript('echo -n "$container"').to_shell_command())

        if output is None or output.stdout is None:
            return None

        return len(output.stdout) > 0

    def _query_capabilities(self, guest: 'Guest') -> dict[GuestCapability, bool]:
        # TODO: there must be a canonical way of getting permitted capabilities.
        # For now, we're interested in whether we can access kernel message buffer.
        return {
            GuestCapability.SYSLOG_ACTION_READ_ALL: True,
            GuestCapability.SYSLOG_ACTION_READ_CLEAR: True,
        }

    def sync(self, guest: 'Guest', *facts: str) -> None:
        """
        Update stored facts to reflect the given guest.

        :param guest: guest whose facts this container should represent.
        :param facts: if specified, only the listed facts - names of
            attributes of this container, like ``arch`` or
            ``is_container`` - will be synced.
        """

        if facts:
            for fact in facts:
                if not hasattr(self, fact):
                    raise GeneralError(f"Cannot sync unknown guest fact '{fact}'.")

                method_name = f'_query_{fact}'

                if not hasattr(self, method_name):
                    raise GeneralError(
                        f"Cannot sync guest fact '{fact}', query method '{method_name}' not found."
                    )

                setattr(self, fact, getattr(self, method_name)(guest))

        else:
            self.os_release_content = self._fetch_keyval_file(guest, Path('/etc/os-release'))
            self.lsb_release_content = self._fetch_keyval_file(guest, Path('/etc/lsb-release'))

            self.arch = self._query_arch(guest)
            self.distro = self._query_distro(guest)
            self.kernel_release = self._query_kernel_release(guest)
            self.package_manager = self._query_package_manager(guest)
            self.bootc_builder = self._query_bootc_builder(guest)
            self.has_selinux = self._query_has_selinux(guest)
            self.has_systemd = self._query_has_systemd(guest)
            self.systemd_soft_reboot = self._query_systemd_soft_reboot(guest)
            self.has_rsync = self._query_has_rsync(guest)
            self.is_superuser = self._query_is_superuser(guest)
            self.can_sudo = self._query_can_sudo(guest)
            self.sudo_prefix = self._query_sudo_prefix(guest)
            self.is_ostree = self._query_is_ostree(guest)
            self.is_image_mode = self._query_is_image_mode(guest)
            self.is_toolbox = self._query_is_toolbox(guest)
            self.toolbox_container_name = self._query_toolbox_container_name(guest)
            self.is_container = self._query_is_container(guest)
            self.capabilities = self._query_capabilities(guest)

        self.in_sync = True

    def format(self) -> Iterator[tuple[str, str, str]]:
        """
        Format facts for pretty printing.

        :yields: three-item tuples: the field name, its pretty label, and formatted representation
            of its value.
        """

        def _value(field: str, label: str) -> tuple[str, str, str]:
            v = getattr(self, field)

            return field, label, v or 'unknown'

        def _flag(field: str, label: str) -> tuple[str, str, str]:
            v = getattr(self, field)

            return field, label, 'yes' if v else 'no'

        yield _value('arch', 'arch')
        yield _value('distro', 'distro')
        yield _value('kernel_release', 'kernel')
        yield _value('package_manager', 'package manager')
        yield _value('bootc_builder', 'bootc builder')
        yield _flag('is_container', 'is container')
        yield _flag('is_ostree', 'is ostree')
        yield _flag('is_image_mode', 'is image mode')
        yield _flag('is_toolbox', 'is toolbox')
        yield _flag('has_selinux', 'selinux')
        yield _flag('has_systemd', 'systemd')
        yield _flag('systemd_soft_reboot', 'systemd soft-reboot')
        yield _flag('has_rsync', 'rsync')
        yield _flag('is_superuser', 'is superuser')
        yield _flag('can_sudo', 'can sudo')


GUEST_FACTS_INFO_FIELDS: list[str] = ['arch', 'distro']
GUEST_FACTS_VERBOSE_FIELDS: list[str] = [
    # SIM118: Use `{key} in {dict}` instead of `{key} in {dict}.keys()`
    # "NormalizeKeysMixin" has no attribute "__iter__" (not iterable)
    key
    for key in GuestFacts.keys()  # noqa: SIM118
    if key not in GUEST_FACTS_INFO_FIELDS
]


def normalize_hardware(
    key_address: str,
    raw_hardware: Union[None, tmt.hardware.Spec, tmt.hardware.Hardware],
    logger: tmt.log.Logger,
) -> Optional[tmt.hardware.Hardware]:
    """
    Normalize a ``hardware`` key value.

    :param key_address: location of the key being that's being normalized.
    :param logger: logger to use for logging.
    :param raw_hardware: input from either command line or fmf node.
    """

    if raw_hardware is None:
        return None

    if isinstance(raw_hardware, tmt.hardware.Hardware):
        return raw_hardware

    # From command line
    if isinstance(raw_hardware, (list, tuple)):
        merged: dict[str, Any] = {}

        for raw_datum in raw_hardware:
            components = tmt.hardware.ConstraintComponents.from_spec(raw_datum)

            if (
                components.name not in tmt.hardware.CHILDLESS_CONSTRAINTS
                and components.child_name is None
            ):
                raise tmt.utils.SpecificationError(
                    f"Hardware requirement '{raw_datum}' lacks "
                    f"child property ({components.name}[N].M)."
                )

            if (
                components.name in tmt.hardware.INDEXABLE_CONSTRAINTS
                and components.peer_index is None
            ):
                raise tmt.utils.SpecificationError(
                    f"Hardware requirement '{raw_datum}' lacks entry index ({components.name}[N])."
                )

            if components.peer_index is not None:
                # This should not happen, the test above already ruled
                # out `child_name` being `None`, but mypy does not know
                # everything is fine.
                assert components.child_name is not None  # narrow type

                if components.name not in merged:
                    merged[components.name] = []

                # Calculate the number of placeholders needed.
                placeholders = components.peer_index - len(merged[components.name]) + 1

                # Fill in empty spots between the existing ones and the
                # one we're adding with placeholders.
                if placeholders > 0:
                    merged[components.name].extend([{} for _ in range(placeholders)])

                merged[components.name][components.peer_index][components.child_name] = (
                    f'{components.operator} {components.value}'
                )

            elif components.name == 'cpu' and components.child_name == 'flag':
                if components.name not in merged:
                    merged[components.name] = {}

                if 'flag' not in merged['cpu']:
                    merged['cpu']['flag'] = []

                merged['cpu']['flag'].append(f'{components.operator} {components.value}')

            elif components.child_name:
                if components.name not in merged:
                    merged[components.name] = {}

                merged[components.name][components.child_name] = (
                    f'{components.operator} {components.value}'
                )

            else:
                merged[components.name] = f'{components.operator} {components.value}'

        # Very crude, we will need something better to handle `and` and
        # `or` and nesting.
        def _drop_placeholders(data: dict[str, Any]) -> dict[str, Any]:
            new_data: dict[str, Any] = {}

            for key, value in data.items():
                if isinstance(value, list):
                    new_data[key] = []

                    for item in value:
                        if isinstance(item, dict) and not item:
                            continue

                        new_data[key].append(item)

                else:
                    new_data[key] = value

            return new_data

        # TODO: if the index matters - and it does, because `disk[0]` is
        # often a "root disk" - we need sparse list. Cannot prune
        # placeholders now, because it would turn `disk[1]` into `disk[0]`,
        # overriding whatever was set for the root disk.
        # https://github.com/teemtee/tmt/issues/3004 for tracking.
        # merged = _drop_placeholders(merged)

        return tmt.hardware.Hardware.from_spec(merged)

    # From fmf
    return tmt.hardware.Hardware.from_spec(raw_hardware)


GuestDataT = TypeVar('GuestDataT', bound='GuestData')


@container
class GuestData(
    SpecBasedContainer[tmt.steps._RawStepData, tmt.steps._RawStepData], SerializableContainer
):
    """
    Keys necessary to describe, create, save and restore a guest.

    Very basic set of keys shared across all known guest classes.
    """

    # TODO: it'd be nice to generate this from all fields, but it seems some
    # fields are not created by `field()` - not sure why, but we can fix that
    # later.
    #: List of fields that are not allowed to be set via fmf keys/CLI options.
    _OPTIONLESS_FIELDS: tuple[str, ...] = ('primary_address', 'topology_address', 'facts')

    #: Primary hostname or IP address for tmt/guest communication.
    primary_address: Optional[str] = None

    #: Guest topology hostname or IP address for guest/guest communication.
    topology_address: Optional[str] = None

    role: Optional[str] = field(
        default=None,
        option='--role',
        metavar='NAME',
        help="""
             Marks guests with the same purpose so that common actions
             can be applied to all such guests at once.
             """,
    )

    become: bool = field(
        default=False,
        is_flag=True,
        option=('-b', '--become'),
        help="""
             Whether to run tests and shell scripts in prepare and
             finish steps with ``sudo``.
             """,
    )

    facts: GuestFacts = field(
        default_factory=GuestFacts,
        serialize=lambda facts: facts.to_serialized(),
        unserialize=lambda serialized: GuestFacts.from_serialized(serialized),
    )

    environment: tmt.utils.Environment = field(
        default_factory=tmt.utils.Environment,
        normalize=tmt.utils.Environment.normalize,
        serialize=lambda environment: environment.to_fmf_spec(),
        unserialize=lambda serialized: tmt.utils.Environment.from_fmf_spec(serialized),
        exporter=lambda environment: environment.to_fmf_spec(),
        help="""
            Environment variables to be defined for this guest. These will be available
            during test execution and can be used to customize behavior on a per-guest basis.
            Note that variables defined here can be overridden by test-level environment variables.
            """,
        option=('-e', '--environment'),
        metavar='KEY=VALUE',
    )

    hardware: Optional[tmt.hardware.Hardware] = field(
        default=cast(Optional[tmt.hardware.Hardware], None),
        option='--hardware',
        help="""
             Hardware requirements the provisioned guest must satisfy.
             """,
        metavar='KEY=VALUE',
        multiple=True,
        normalize=normalize_hardware,
        serialize=lambda hardware: hardware.to_spec() if hardware else None,
        unserialize=lambda serialized: (
            tmt.hardware.Hardware.from_spec(serialized) if serialized is not None else None
        ),
    )

    ansible: Optional[GuestAnsible] = field(
        default=None,
        normalize=normalize_guest_ansible,
        serialize=lambda ansible: ansible.to_serialized() if ansible else None,
        unserialize=lambda serialized: (
            GuestAnsible.from_serialized(serialized) if serialized else GuestAnsible()
        ),
        help='Ansible configuration for individual guest inventory generation.',
    )

    # ignore[override]: expected, we need to accept one extra parameter, `logger`.
    @classmethod
    def from_spec(  # type: ignore[override]
        cls,
        raw_data: tmt.steps._RawStepData,
        logger: tmt.log.Logger,
    ) -> Self:
        # ignore[call-arg]: this is expected, parent classes uses special
        # `from_spec`, and we need to follow.
        return super().from_spec(raw_data, logger)  # type: ignore[call-arg]

    def to_spec(self) -> tmt.steps._RawStepData:
        spec = super().to_spec()

        spec.pop('facts', None)  # type: ignore[typeddict-item]
        spec['ansible'] = self.ansible.to_spec() if self.ansible else {}  # type: ignore[typeddict-unknown-key]

        return spec

    # TODO: find out whether this could live in DataContainer. It probably could,
    # but there are containers not backed by options... Maybe a mixin then?
    @classmethod
    def options(cls) -> Iterator[tuple[str, str]]:
        """
        Iterate over option names.

        Based on :py:meth:`keys`, but skips fields that cannot be set by options.

        :yields: two-item tuples, a key and corresponding option name.
        """

        for f in dataclasses.fields(cls):
            if f.name in cls._OPTIONLESS_FIELDS:
                continue

            yield f.name, key_to_option(f.name)

    @classmethod
    def from_plugin(
        cls,
        container: 'ProvisionPlugin[ProvisionStepDataT]',
    ) -> Self:
        """
        Create guest data from plugin and its current configuration
        """

        return cls(
            **{
                key: container.get(option)
                # SIM118: Use `{key} in {dict}` instead of `{key} in {dict}.keys()`.
                # "Type[ArtemisGuestData]" has no attribute "__iter__" (not iterable)
                for key, option in cls.options()
            }
        )

    def show(
        self,
        *,
        keys: Optional[list[str]] = None,
        verbose: int = 0,
        logger: tmt.log.Logger,
    ) -> None:
        """
        Display guest data in a nice way.

        :param keys: if set, only these keys would be shown.
        :param verbose: desired verbosity. Some fields may be omitted in low
            verbosity modes.
        :param logger: logger to use for logging.
        """

        # If all keys are set to their defaults, do not bother showing them - unless
        # forced to do so by the power of `-v`.
        if self.is_bare and not verbose:
            return

        keys = keys or list(self.keys())

        for key in keys:
            # TODO: teach GuestFacts to cooperate with show() methods, honor
            # the verbosity at the same time.
            if key == 'facts':
                continue

            value = getattr(self, key)

            if value == self.default(key):
                continue

            # TODO: it seems tmt.utils.format() needs a key, and logger.info()
            # does not accept already formatted string.
            if isinstance(value, (list, tuple)):
                printable_value = fmf.utils.listed(value)

            elif isinstance(value, dict):
                printable_value = tmt.utils.format_value(value)

            elif isinstance(value, (tmt.hardware.Hardware, tmt.ansible.GuestAnsible)):
                printable_value = tmt.utils.to_yaml(value.to_spec())

            else:
                printable_value = str(value)

            logger.info(key_to_option(key).replace('-', ' '), printable_value, color='green')


@container
class GuestLog(abc.ABC):
    """
    Represents a single guest log.

    Guest logs are files collected by tmt, containing a wide variety
    of information about the guest and its behavior. They are not tied
    to a particular phase or test, instead they document what was
    happening on the guest while tmt was running its phases.

    The actual set of available guest logs, and the way of their
    acquisition, depends entirely on the plugin providing the guest and
    its backing infrastructure. Some plugins may simply inspect local
    files or services, some plugins need to communicate with a hypervisor
    powering the guest, and so on.

    Eventually, guest logs are stored on the runner, as a collection of
    files, for user to review if needed.

    Log life cycle
    ^^^^^^^^^^^^^^

    * ``GuestLog`` instances shall be created by plugin once possible
      in the context of the guest and its implementation, and added to
      the :py:attr:`Guest.guest_logs` list. Generally, it should be
      possible to fetch content of the log.
    * Once :py:attr:`Guest.guest_logs` is populated, the plugin shall
      invoke :py:meth:`Guest.setup_logs`. This method is responsible
      for invoking :py:meth:`setup` of all registered logs.
    * After this point, tmt may start collecting logs by invoking their
      :py:meth:`update` methods. It is allowed for the log to not be
      available yet, the log may be empty, other issues shall raise an
      exception.
    * The ``cleanup`` step will collect logs one more time.
    * The ``cleanup`` step will invoke :py:meth:`Guest.teardown_logs`,
      which will invoke :py:meth:`teardown` methods of all registered
      logs.
    * After this point, logs will not be collected anymore.
    """

    #: Name of the guest log.
    name: str

    #: Guest whose log this instance represents.
    guest: "Guest"

    @functools.cached_property
    def filename(self) -> str:
        """
        A filename to use when storing the log.

        By default, the name of the log is used.
        """

        return self.name

    @functools.cached_property
    def filepath(self) -> Path:
        """
        A filepath to use when storing the log.
        """

        return self.guest.logdir / self.filename

    # B027: "... is an empty method in an abstract base class, but has
    # no abstract decorator" - expected, it's a default implementation
    # provided for subclasses. It is acceptable to do nothing.
    def setup(self, *, logger: tmt.log.Logger) -> None:  # noqa: B027
        """
        Prepare for collecting the log.

        It is left for plugins to setup the needed infrastructure,
        make API calls, etc.

        :param logger: logger to use for logging.
        """

        pass

    # B027: "... is an empty method in an abstract base class, but has
    # no abstract decorator" - expected, it's a default implementation
    # provided for subclasses. It is acceptable to do nothing.
    def teardown(self, *, logger: tmt.log.Logger) -> None:  # noqa: B027
        """
        Finalize the collection of the log.

        It is left for plugins to tear down and remove what is no longer
        needed once the log stops being collected.

        :param logger: logger to use for logging.
        """

        pass

    @contextlib.contextmanager
    def staging_file(self, final_filepath: Path, logger: tmt.log.Logger) -> Iterator[Path]:
        """
        Provide a temporary file to be swapped with the final filepath.

        Instead of writing directly into the final log filepath, log
        update should write its new content into a temporary file which,
        should everything go well, would replace the existing content
        in an atomic move. That way the existing content would not be
        compromised or broken by a failed update.

        :param final_filepath: the desired final filepath, the temporary
            file would replace this filepath on success.
        :param logger: logger to use for logging.
        """

        temporary_filepath = Path(f'{final_filepath}.new')
        temporary_filepath.unlink(missing_ok=True)

        try:
            logger.debug(
                f"Store '{self.name}' log in the staging file '{temporary_filepath}'.", level=3
            )

            yield temporary_filepath

        except Exception as exc:
            raise exc

        else:
            if temporary_filepath.exists():
                logger.debug(
                    f"Promoting the staging file '{temporary_filepath}' into '{final_filepath}'.",
                    level=3,
                )

                shutil.move(temporary_filepath, final_filepath)

    @abc.abstractmethod
    def update(self, *, logger: tmt.log.Logger) -> None:
        """
        Fetch the up-to-date content of the log, and save it into a file.

        :param logger: logger to use for logging.
        """

        raise NotImplementedError


class CommandCollector(abc.ABC):
    """
    Mixin for that supports collecting commands for deferred execution.
    """

    @abc.abstractmethod
    def collect_command(
        self,
        command: Union[tmt.utils.Command, tmt.utils.ShellScript],
        *,
        sourced_files: Optional[list[Path]] = None,
        cwd: Optional[Path] = None,
        env: Optional[tmt.utils.Environment] = None,
    ) -> None:
        """
        Collect a command for later batch execution.

        :param command: the command to collect.
        :param cwd: working directory for the command.
        :param env: environment variables for the command.
        """

        raise NotImplementedError

    @abc.abstractmethod
    def flush_collected(self) -> None:
        """
        Execute all collected commands.
        """

        raise NotImplementedError

    @property
    @abc.abstractmethod
    def has_collected_commands(self) -> bool:
        """Return True if there are collected commands pending."""

        raise NotImplementedError


class Guest(
    tmt.utils.HasRunWorkdir,
    tmt.utils.HasPlanWorkdir,
    tmt.utils.HasStepWorkdir,
    # TODO: this will not work: `self.parent` is not the owning phase,
    # but the `provision` step itself. We do not have access to the
    # original phase.
    # tmt.utils.HasPhaseWorkdir,
    tmt.utils.HasGuestWorkdir,
    # TODO: `Guest` does "have" environment, but it's a genuine attribute,
    # not a property, and this interface will not work.
    # tmt.utils.HasEnvironment,
    tmt.utils.Common,
):
    """
    Guest provisioned for test execution

    A base class for guest-like classes. Provides some of the basic methods
    and functionality, but note some of the methods are left intentionally
    empty. These do not have valid implementation on this level, and it's up
    to Guest subclasses to provide one working in their respective
    infrastructure.

    The following keys are expected in the 'data' container::

        role ....... guest role in the multihost scenario
        guest ...... name, hostname or ip address
        become ..... boolean, whether to run shell scripts in tests, prepare, and finish with sudo

    These are by default imported into instance attributes.
    """

    # Used by save() to construct the correct container for keys.
    _data_class: type[GuestData] = GuestData

    @classmethod
    def get_data_class(cls) -> type[GuestData]:
        """
        Return step data class for this plugin.

        By default, :py:attr:`_data_class` is returned, but plugin may
        override this method to provide different class.
        """

        return cls._data_class

    role: Optional[str]

    #: Primary hostname or IP address for tmt/guest communication.
    primary_address: Optional[str] = None

    #: Guest topology hostname or IP address for guest/guest communication.
    topology_address: Optional[str] = None

    become: bool

    hardware: Optional[tmt.hardware.Hardware]

    environment: tmt.utils.Environment

    ansible: Optional[GuestAnsible]

    # Flag to indicate localhost guest, requires special handling
    localhost = False

    #: Guest logs active and available for collection.
    guest_logs: list[GuestLog]

    # TODO: do we need this list? Can whatever code is using it use _data_class directly?
    # List of supported keys
    # (used for import/export to/from attributes during load and save)
    @property
    def _keys(self) -> list[str]:
        return list(self.get_data_class().keys())

    def __init__(
        self,
        *,
        data: GuestData,
        name: Optional[str] = None,
        parent: Optional[tmt.utils.Common] = None,
        logger: tmt.log.Logger,
    ) -> None:
        """
        Initialize guest data
        """

        self.guest_logs = []

        super().__init__(logger=logger, parent=parent, name=name)
        self.load(data)

    @property
    def run_workdir(self) -> Path:
        return cast('Provision', self.parent).run_workdir

    @property
    def plan_workdir(self) -> Path:
        return cast('Provision', self.parent).plan_workdir

    @property
    def step_workdir(self) -> Path:
        return cast('Provision', self.parent).step_workdir

    @property
    def guest_workdir(self) -> Path:
        if self.workdir is None:
            raise GeneralError(
                f"Existence of a guest '{self.name}' workdir"
                " was presumed but the workdir does not exist."
            )

        return self.workdir

    def _random_name(self, prefix: str = '', length: int = 16) -> str:
        """
        Generate a random name
        """

        # Append at least 5 random characters
        min_random_part = max(5, length - len(prefix))
        name = prefix + ''.join(
            secrets.choice(string.ascii_letters) for _ in range(min_random_part)
        )
        # Return tail (containing random characters) of name
        return name[-length:]

    def _tmt_name(self) -> str:
        """
        Generate a name prefixed with tmt run id
        """

        # FIXME: cast() - https://github.com/teemtee/tmt/issues/1372
        parent = cast('Provision', self.parent)

        run_id = parent.run_workdir.name
        return self._random_name(prefix=f"tmt-{run_id[-3:]}-")

    @functools.cached_property
    def multihost_name(self) -> str:
        """
        Return guest's multihost name, i.e. name and its role
        """

        return format_guest_full_name(self.name, self.role)

    @property
    @abc.abstractmethod
    def is_ready(self) -> bool:
        """
        Detect guest is ready or not
        """

        raise NotImplementedError

    @functools.cached_property
    def package_manager(
        self,
    ) -> 'tmt.package_managers.PackageManager[tmt.package_managers.PackageManagerEngine]':
        if not self.facts.package_manager:
            raise tmt.utils.GeneralError(
                f"Package manager was not detected on guest '{self.name}'."
            )

        return tmt.package_managers.find_package_manager(self.facts.package_manager)(
            guest=self, logger=self._logger
        )

    @functools.cached_property
    def bootc_builder(
        self,
    ) -> 'tmt.package_managers.PackageManager[tmt.package_managers.PackageManagerEngine]':
        if not self.facts.bootc_builder:
            raise tmt.utils.GeneralError(f"Bootc builder was not detected on guest '{self.name}'.")

        return tmt.package_managers.find_package_manager(self.facts.bootc_builder)(
            guest=self, logger=self._logger
        )

    @functools.cached_property
    def scripts_path(self) -> Path:
        """
        Absolute path to tmt scripts directory
        """

        # For rpm-ostree based distributions use a different default destination directory
        return tmt.steps.scripts.effective_scripts_dest_dir(
            default=tmt.steps.scripts.DEFAULT_SCRIPTS_DEST_DIR_OSTREE
            if self.facts.is_ostree
            else tmt.steps.scripts.DEFAULT_SCRIPTS_DEST_DIR
        )

    @classmethod
    def options(cls, how: Optional[str] = None) -> list[tmt.options.ClickOptionDecoratorType]:
        """
        Prepare command line options related to guests
        """

        return []

    def load(self, data: GuestData) -> None:
        """
        Load guest data into object attributes for easy access

        Called during guest object initialization. Takes care of storing
        all supported keys (see class attribute _keys for the list) from
        provided data to the guest object attributes. Child classes can
        extend it to make additional guest attributes easily available.

        Data dictionary can contain guest information from both command
        line options / L2 metadata / user configuration and wake up data
        stored by the save() method below.
        """

        data.inject_to(self)

    def save(self) -> GuestData:
        """
        Save guest data for future wake up

        Export all essential guest data into a dictionary which will be
        stored in the `guests.yaml` file for possible future wake up of
        the guest. Everything needed to attach to a running instance
        should be added into the data dictionary by child classes.
        """

        return self.get_data_class().extract_from(self)

    def wake(self) -> None:
        """
        Wake up the guest

        Perform any actions necessary after step wake up to be able to
        attach to a running guest instance and execute commands. Called
        after load() is completed so all guest data should be prepared.
        """

        self.debug(f"Doing nothing to wake up guest '{self.primary_address}'.")

    def suspend(self) -> None:
        """
        Suspend the guest.

        Perform any actions necessary before quitting step and tmt. The
        guest may be reused by future tmt invocations.
        """

        self.debug(f"Suspending guest '{self.name}'.")

    def start(self) -> None:
        """
        Start the guest

        Get a new guest instance running. This should include preparing
        any configuration necessary to get it started. Called after
        load() is completed so all guest data should be available.
        """

        self.debug(f"Doing nothing to start guest '{self.primary_address}'.")

    def install_scripts(self, scripts: Sequence[tmt.steps.scripts.Script]) -> None:
        """
        Install scripts required by tmt.
        """

        # Ensure scripts directory exists on guest (create only if missing)
        self.execute(
            ShellScript(
                f"[ -d {quote(str(self.scripts_path))} ] || "
                f"{self.facts.sudo_prefix} mkdir -p {quote(str(self.scripts_path))}"
            ).to_shell_command(),
            silent=True,
        )

        # Install all scripts on guest
        excluded_scripts = []
        scripts_staging_dir = self.run_workdir / tmt.steps.scripts.SCRIPTS_DIR_NAME
        for script in scripts:
            if script.destination_path:
                # scripts with destination_path we have to copy individually
                if script.enabled(self):
                    self.push(
                        source=scripts_staging_dir / script.source_filename,
                        destination=script.destination_path,
                        options=TransferOptions(preserve_perms=True, chmod=0o755),
                        superuser=self.facts.is_superuser is not True,
                    )
                excluded_scripts.append(scripts_staging_dir / script.source_filename)
            elif not script.enabled(self):
                # Otherwise just make a list of scripts and their aliases to skip
                # (they are being copied as a whole from scripts_staging_dir)
                excluded_scripts.extend(
                    scripts_staging_dir / filename
                    for filename in [script.source_filename, *script.aliases]
                )
        # Finally copy the whole staging directory
        self.push(
            source=scripts_staging_dir,
            destination=self.scripts_path,
            options=TransferOptions(
                preserve_perms=True,
                recursive=True,
                create_destination=True,
                exclude=[str(path.absolute()) for path in excluded_scripts],
            ),
            superuser=self.facts.is_superuser is not True,
        )

    def setup(self) -> None:
        """
        Setup the guest

        Setup the guest after it has been started. It is called after :py:meth:`Guest.start`.
        """

        self.install_scripts(tmt.steps.scripts.SCRIPTS)

    # A couple of requiremens for this field:
    #
    # * it should be valid, i.e. when someone tries to access it, the values
    #   should be there.
    # * it should be serializable so we can save & load it, to save time when
    #   using the guest once again.
    #
    # Note that the facts container, `GuestFacts`, is already provided to us,
    # in `GuestData` package given to `Guest.__init__()`, and it's saved in
    # our `__dict__`. It's just empty.
    #
    # A bit of Python magic then:
    #
    # * a property it is, it allows us to do some magic on access. Also,
    #   `guest.facts` is much better than `guest.data.facts`.
    # * property does not need to care about instantiation of the container,
    #   it just works with it.
    # * when accessed, property takes the facts container and starts the sync,
    #   if needed. This is probably going to happen just once, on the first
    #   access, unless something explicitly invalidates the facts.
    # * when loaded from `guests.yaml`, the container is unserialized and put
    #   directly into `__dict__`, like nothing has happened.
    @property
    def facts(self) -> GuestFacts:
        facts = cast(GuestFacts, self.__dict__['facts'])

        if not facts.in_sync:
            facts.sync(self)

        return facts

    @facts.setter
    def facts(self, facts: Union[GuestFacts, dict[str, Any]]) -> None:
        if isinstance(facts, GuestFacts):
            self.__dict__['facts'] = facts

        else:
            self.__dict__['facts'] = GuestFacts.from_serialized(facts)

    @functools.cached_property
    def ansible_host_vars(self) -> dict[str, Any]:
        """
        Get host variables for Ansible inventory.
        """
        return {
            'ansible_host': self.primary_address,
            **(self.ansible.vars if self.ansible else {}),
        }

    @functools.cached_property
    def ansible_host_groups(self) -> list[str]:
        """
        Get guest list of groups for Ansible inventory.
        """
        groups = ['all']  # All hosts are in 'all' group

        # Try to get ansible group from ansible.group key in provision guest data
        if self.ansible and self.ansible.group:
            groups.append(self.ansible.group)
        elif self.role:  # Otherwise use role as group
            groups.append(self.role)
        else:
            groups.append('ungrouped')

        return groups

    def show(self, show_multihost_name: bool = True) -> None:
        """
        Show guest details such as distro and kernel
        """

        if show_multihost_name:
            self.info('multihost name', self.multihost_name, color='green')

        # Skip active checks in dry mode
        if self.is_dry_run:
            return

        if not self.is_ready:
            return

        for key, key_formatted, value_formatted in self.facts.format():
            if key in GUEST_FACTS_INFO_FIELDS:
                self.info(key_formatted, value_formatted, color='green')

            elif key in GUEST_FACTS_VERBOSE_FIELDS:
                self.verbose(key_formatted, value_formatted, color='green')

    def _ansible_verbosity(self) -> list[str]:
        """
        Prepare verbose level based on the --debug option count
        """

        if self.debug_level < 3:
            return []
        return ['-' + (self.debug_level - 2) * 'v']

    @staticmethod
    def _ansible_extra_args(extra_args: Optional[str]) -> tmt.utils.RawCommand:
        """
        Prepare extra arguments for ``ansible-playbook`` command.

        :param extra_args: optional ``ansible-playbook`` arguments,
            packed in a single string as provided by user.
        :returns: empty list if ``extra_args`` is not set or it's empty.
            Otherwise, a list of arguments produced by
            :py:func:`shlex.split` applied on ``extra_args``.
        """

        if extra_args is None:
            return []
        return cast(tmt.utils.RawCommand, shlex.split(str(extra_args)))

    def _ansible_summary(self, output: Optional[str]) -> None:
        """
        Check the output for ansible result summary numbers
        """

        if not output:
            return
        keys = ['ok', 'changed', 'unreachable', 'failed', 'skipped', 'rescued', 'ignored']
        for key in keys:
            matched = re.search(rf'^.*\s:\s.*{key}=(\d+).*$', output, re.MULTILINE)
            if matched and int(matched.group(1)) > 0:
                tasks = fmf.utils.listed(matched.group(1), 'task')
                self.verbose(key, tasks, 'green')

    def _sanitize_ansible_playbook_path(
        self, playbook: AnsibleApplicable, playbook_root: Optional[Path]
    ) -> AnsibleApplicable:
        """
        Prepare full ansible playbook path.

        :param playbook: path to the playbook to run.
        :param playbook_root: if set, ``playbook`` path must be located
            under the given root path.
        :returns: an absolute path to a playbook.
        :raises GeneralError: when ``playbook_root`` is set, but
            ``playbook`` is not located in this filesystem tree, or when
            the eventual playbook path is not absolute.
        """

        # Handle the individual types under the hood of `AnsibleApplicable`.
        # Note that `isinstance()` calls do not use our fancy names,
        # `AnsibleCollectionPlaybook` and `AnsiblePlaybook`. These are
        # extremely helpful to type checkers, but Python interpreter
        # sees only the aliased types, `Path` and `str`.

        # First, a path:
        if isinstance(playbook, Path):
            # Some playbooks must be under playbook root, which is often
            # a metadata tree root.
            if playbook_root is not None:
                playbook = playbook_root / playbook.unrooted()

                if not playbook.is_relative_to(playbook_root):
                    raise tmt.utils.GeneralError(
                        f"'{playbook}' is not relative to the expected root '{playbook_root}'."
                    )

            if not playbook.exists():
                raise tmt.utils.FileError(f"Playbook '{playbook}' does not exist.")

            self.debug(f"Playbook full path: '{playbook}'", level=2)

            return playbook

        # Second, a collection playbook:
        if isinstance(playbook, str):
            self.debug(f"Collection playbook: '{playbook}'", level=2)

            return playbook

        raise GeneralError(f"Unknown Ansible object type, '{type(playbook)}'.")

    def _prepare_environment(
        self, execute_environment: Optional[tmt.utils.Environment] = None
    ) -> tmt.utils.Environment:
        """
        Prepare dict of environment variables
        """
        # Prepare environment variables so they can be correctly passed
        # to shell. Create a copy to prevent modifying source.
        environment = tmt.utils.Environment()
        environment.update(execute_environment or {})
        # Plan environment and variables provided on the command line
        # override environment provided to execute().
        # FIXME: cast() - https://github.com/teemtee/tmt/issues/1372
        if self.parent:
            parent = cast('Provision', self.parent)
            environment.update(parent.plan.environment)
        return environment

    def _run_guest_command(
        self,
        command: Command,
        friendly_command: Optional[str] = None,
        silent: bool = False,
        cwd: Optional[Path] = None,
        env: Optional[tmt.utils.Environment] = None,
        interactive: bool = False,
        log: Optional[tmt.log.LoggingFunction] = None,
        **kwargs: Any,
    ) -> tmt.utils.CommandOutput:
        """
        Run a command, local or remote, related to the guest.

        A rather thin wrapper of :py:meth:`run` whose purpose is to be a single
        point through all commands related to a guest must go through. We expect
        consistent logging from such commands, be it an ``ansible-playbook``
        running on the control host or a test script on the guest.

        :param command: a command to execute.
        :param friendly_command: if set, it would be logged instead of the
            command itself, to improve visibility of the command in logging output.
        :param silent: if set, logging of steps taken by this function would be
            reduced.
        :param cwd: if set, command would be executed in the given directory,
            otherwise the current working directory is used.
        :param env: environment variables to combine with the current environment
            before running the command.
        :param interactive: if set, the command would be executed in an interactive
            manner, i.e. with stdout and stdout connected to terminal for live
            interaction with user.
        :param log: a logging function to use for logging of command output. By
            default, ``self._logger.debug`` is used.
        :returns: command output, bundled in a :py:class:`CommandOutput` tuple.
        """

        if friendly_command is None:
            friendly_command = str(command)

        return self.run(
            command,
            friendly_command=friendly_command,
            silent=silent,
            cwd=cwd,
            env=env,
            interactive=interactive,
            log=log or self._command_verbose_logger,
            **kwargs,
        )

    @abc.abstractmethod
    def _run_ansible(
        self,
        playbook: AnsibleApplicable,
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

        raise NotImplementedError

    def run_ansible_playbook(
        self,
        playbook: AnsibleApplicable,
        playbook_root: Optional[Path] = None,
        extra_args: Optional[str] = None,
        friendly_command: Optional[str] = None,
        log: Optional[tmt.log.LoggingFunction] = None,
        silent: bool = False,
    ) -> tmt.utils.CommandOutput:
        """
        Run an Ansible playbook on the guest.

        A wrapper for :py:meth:`_run_ansible` which is responsible for running
        the playbook while this method makes sure our logging is consistent.

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

        output = self._run_ansible(
            playbook,
            playbook_root=playbook_root,
            extra_args=extra_args,
            friendly_command=friendly_command,
            log=log or self._command_verbose_logger,
            silent=silent,
        )

        self._ansible_summary(output.stdout)

        return output

    def on_step_complete(self, step: 'tmt.steps.Step') -> None:
        """
        Called when a step completes execution.

        Does nothing for :py:class:`Guest`. Should be overridden in subclass if needed.

        :param step: the step that has completed.
        """
        pass

    @overload
    def execute(
        self,
        command: Union[tmt.utils.Command, tmt.utils.ShellScript],
        cwd: Optional[Path] = None,
        env: Optional[tmt.utils.Environment] = None,
        friendly_command: Optional[str] = None,
        test_session: bool = False,
        immediately: Literal[True] = True,
        tty: bool = False,
        silent: bool = False,
        log: Optional[tmt.log.LoggingFunction] = None,
        interactive: bool = False,
        on_process_start: Optional[OnProcessStartCallback] = None,
        on_process_end: Optional[OnProcessEndCallback] = None,
        sourced_files: Optional[list[Path]] = None,
        **kwargs: Any,
    ) -> tmt.utils.CommandOutput:
        pass

    @overload
    def execute(
        self,
        command: Union[tmt.utils.Command, tmt.utils.ShellScript],
        cwd: Optional[Path] = None,
        env: Optional[tmt.utils.Environment] = None,
        friendly_command: Optional[str] = None,
        test_session: bool = False,
        immediately: Literal[False] = False,
        tty: bool = False,
        silent: bool = False,
        log: Optional[tmt.log.LoggingFunction] = None,
        interactive: bool = False,
        on_process_start: Optional[OnProcessStartCallback] = None,
        on_process_end: Optional[OnProcessEndCallback] = None,
        sourced_files: Optional[list[Path]] = None,
        **kwargs: Any,
    ) -> Optional[tmt.utils.CommandOutput]:
        pass

    @abc.abstractmethod
    def execute(
        self,
        command: Union[tmt.utils.Command, tmt.utils.ShellScript],
        cwd: Optional[Path] = None,
        env: Optional[tmt.utils.Environment] = None,
        friendly_command: Optional[str] = None,
        test_session: bool = False,
        immediately: bool = True,
        tty: bool = False,
        silent: bool = False,
        log: Optional[tmt.log.LoggingFunction] = None,
        interactive: bool = False,
        on_process_start: Optional[OnProcessStartCallback] = None,
        on_process_end: Optional[OnProcessEndCallback] = None,
        sourced_files: Optional[list[Path]] = None,
        **kwargs: Any,
    ) -> tmt.utils.CommandOutput:
        """
        Execute a command on the guest.

        :param command: either a command or a shell script to execute.
        :param cwd: if set, execute command in this directory on the guest.
        :param env: if set, set these environment variables before running the command.
        :param friendly_command: nice, human-friendly representation of the command.
        :param immediately: if False, the command may be collected for later
            batch execution on guests that support it (e.g., bootc guests).
            Commands with ``immediately=True`` (default) are always executed
            right away. Use ``immediately=False`` for commands that modify
            system state and can be batched (e.g., package installation).
        """

        raise NotImplementedError

    @abc.abstractmethod
    def push(
        self,
        source: Optional[Path] = None,
        destination: Optional[Path] = None,
        options: Optional[TransferOptions] = None,
        superuser: bool = False,
    ) -> None:
        """
        Push files to the guest
        """

        raise NotImplementedError

    @abc.abstractmethod
    def pull(
        self,
        source: Optional[Path] = None,
        destination: Optional[Path] = None,
        options: Optional[TransferOptions] = None,
    ) -> None:
        """
        Pull files from the guest
        """

        raise NotImplementedError

    @abc.abstractmethod
    def stop(self) -> None:
        """
        Stop the guest

        Shut down a running guest instance so that it does not consume
        any memory or cpu resources. If needed, perform any actions
        necessary to store the instance status to disk.
        """

        raise NotImplementedError

    def perform_reboot(
        self,
        mode: RebootMode,
        action: Callable[[], Any],
        wait: Waiting,
    ) -> bool:
        """
        Perform the actual reboot and wait for the guest to recover.

        This is the core implementation of the common task of triggering
        a reboot and waiting for the guest to recover. :py:meth:`reboot`
        is the public API of guest classes, and feeds
        :py:meth:`perform_reboot` with the right ``action`` callable.

        .. note::

            :py:meth:`perform_reboot` should be used by ``provision``
            plugins only, when they decide what action they need to take
            to take to perform the desired reboot of the guest. Other
            code should use :py:meth:`Guest.reboot` instead.

        :param mode: which boot mode to perform.
        :param action: a callable which will trigger the requested reboot.
        :param waiting: deadline for the reboot.
        :returns: ``True`` if the reboot succeeded, ``False`` otherwise.
        """

        if mode == RebootMode.SYSTEMD_SOFT:
            if not self.facts.systemd_soft_reboot:
                raise RebootModeNotSupportedError(guest=self, mode=mode)

            boot_mark: type[BootMark] = BootMarkSystemdSoftRebootCount

        elif mode in {RebootMode.SOFT, RebootMode.HARD}:
            boot_mark = BootMarkBootTime

        else:
            raise RebootModeNotSupportedError(guest=self, mode=mode)

        current_boot_mark = boot_mark.fetch(self) if mode != RebootMode.HARD else None

        self.debug(f"Triggering {mode.value} reboot with '{action}'.")

        try:
            action()

        except tmt.utils.RunError as error:
            # Connection can be closed by the remote host even before the
            # reboot command is completed. Let's ignore such errors.
            if error.returncode == 255:
                self.debug("Seems the connection was closed too fast, ignoring.")
            else:
                raise

        # Wait until we get new boot mark, connection will drop and will be
        # unreachable for some time
        try:
            wait.wait(lambda: boot_mark.check(self, current_boot_mark), self._logger)

        except tmt.utils.wait.WaitingTimedOutError:
            self.debug("Connection to guest failed after reboot.")
            return False

        self.debug("Connection to guest succeeded after reboot.")
        return True

    @overload
    def reboot(
        self,
        mode: HardRebootModes = RebootMode.HARD,
        command: None = None,
        waiting: Optional[Waiting] = None,
    ) -> bool:
        pass

    @overload
    def reboot(
        self,
        mode: SoftRebootModes = RebootMode.SOFT,
        command: Optional[Union[Command, ShellScript]] = None,
        waiting: Optional[Waiting] = None,
    ) -> bool:
        pass

    @abc.abstractmethod
    def reboot(
        self,
        mode: RebootMode = RebootMode.SOFT,
        command: Optional[Union[Command, ShellScript]] = None,
        waiting: Optional[Waiting] = None,
    ) -> bool:
        """
        Reboot the guest, and wait for the guest to recover.

        :param mode: which boot mode to perform.
        :param command: a command to run on the guest to trigger the
            reboot. Only usable when mode is not
            :py:attr:`RebootMode.HARD`.
        :param waiting: deadline for the reboot.
        :returns: ``True`` if the reboot succeeded, ``False`` otherwise.
        """

        raise NotImplementedError

    def reconnect(
        self,
        wait: Optional[Waiting] = None,
    ) -> bool:
        """
        Ensure the connection to the guest is working

        The default timeout is 5 minutes. Custom number of seconds can be
        provided in the `timeout` parameter. This may be useful when long
        operations (such as system upgrade) are performed.
        """

        wait = wait or default_reconnect_waiting()

        self.debug("Wait for a connection to the guest.")

        def try_whoami() -> None:
            try:
                self.execute(Command('whoami'), silent=True)

            except tmt.utils.RunError as error:
                # Detect common issues with guest access
                if error.stdout and 'Please login as the user' in error.stdout:
                    raise tmt.utils.GeneralError('Login to the guest failed.') from error
                if (
                    error.stderr
                    and f'executable file `{tmt.utils.DEFAULT_SHELL}` not found' in error.stderr
                ):
                    raise tmt.utils.GeneralError(
                        f'{tmt.utils.DEFAULT_SHELL.capitalize()} is required on the guest.'
                    ) from error

                raise tmt.utils.wait.WaitingIncompleteError from error

        try:
            wait.wait(try_whoami, self._logger)

        except tmt.utils.wait.WaitingTimedOutError:
            self.debug("Connection to guest failed.")
            return False

        return True

    def remove(self) -> None:
        """
        Remove the guest

        Completely remove all guest instance data so that it does not
        consume any disk resources.
        """

        self.debug(f"Doing nothing to remove guest '{self.primary_address}'.")

    def assert_reachable(self, wait: Optional[Waiting] = None) -> None:
        """
        Assert that the guest is reachable and responding.
        """

        wait = wait or default_connect_waiting()

        if not self.is_ready:
            raise ProvisionError(f"Guest '{self.multihost_name}' is not ready.")

        if not self.reconnect(wait):
            raise ProvisionError(
                f"Failed to connect to the guest '{self.multihost_name}'"
                f" in {wait.deadline.original_timeout.total_seconds()}s"
            )

    @classmethod
    def essential_requires(cls) -> list['tmt.base.core.Dependency']:
        """
        Collect all essential requirements of the guest.

        Essential requirements of a guest are necessary for the guest to be
        usable for testing.

        :returns: a list of requirements.
        """

        return []

    @functools.cached_property
    def logdir(self) -> Path:
        """
        Path to store logs

        Create the directory if it does not exist yet.
        """

        dirpath = self.guest_workdir / 'logs'
        dirpath.mkdir(parents=True, exist_ok=True)

        return dirpath

    def collect_log(self, log: GuestLog, hint: Optional[str] = None) -> None:
        """
        Register a guest log for (later) collection.

        :param log: guest log to collect and save.
        :param hint: if set, it would be included in the logging message
            emitted by this function.
        """

        message_components: list[str] = [f"Adding '{log.name}' guest log"]

        if hint:
            message_components.append(hint)

        self._logger.debug(f"{', '.join(message_components)}.", level=3)

        self.guest_logs.append(log)

    def setup_logs(self, *, logger: tmt.log.Logger) -> None:
        """
        Notify all registered logs their collection will begin.

        :param logger: logger to use for logging.
        """

        for log in self.guest_logs:
            log.setup(logger=logger)

    def teardown_logs(self, *, logger: tmt.log.Logger) -> None:
        """
        Notify all registered logs their collection will no longer continue.

        :param logger: logger to use for logging.
        """

        for log in self.guest_logs:
            log.teardown(logger=logger)

    def update_logs(
        self,
        *,
        logger: tmt.log.Logger,
    ) -> None:
        """
        Fetch the up-to-date content of guest logs, and update saved files.

        :param logger: logger to use for logging.
        """

        for log in self.guest_logs:
            try:
                log.update(logger=logger)

            except Exception as exc:
                tmt.utils.show_exception_as_warning(
                    exception=exc,
                    message=f"Failed to update guest log '{log.name}'.",
                    logger=logger,
                )

            else:
                logger.info(log.name, str(log.filepath))

    def _construct_mkdtemp_command(
        self,
        prefix: Optional[str] = None,
        template: Optional[str] = None,
        parent: Optional[Path] = None,
    ) -> Command:
        template = template or 'tmp.XXXXXXXXXX'

        if prefix is not None:
            template = f'{prefix}{template}'

        options: list[str] = ['--directory']

        if parent is not None:
            options += ['-p', str(parent)]

        return Command(*('mktemp', *options, template))

    @contextlib.contextmanager
    def mkdtemp(
        self,
        # Suffix is not supported everywhere, namely Alpine does not
        # recognize it, and even requires template to end with `XXXXXX`.
        # Therefore not supporting this option - in the future, someone
        # may need it, fix it for all distros, and uncomment the
        # parameter.
        # suffix: Optional[str] = None,
        prefix: Optional[str] = None,
        template: Optional[str] = None,
        parent: Optional[Path] = None,
    ) -> Iterator[Path]:
        """
        Create a temporary directory.

        Modeled after :py:func:`tempfile.mkdtemp`, but creates the
        temporary directory on the guest, by invoking ``mktemp -d``. The
        implementation may slightly differ, but the temporary directory
        should be created safely, without conflicts, and it should be
        accessible only to user who created it.

        Since the caller is responsible for removing the directory, it
        is recommended to use it as a context manager, just as one would
        use :py:func:`tempfile.mkdtemp`; leaving the context will remove
        the directory:

        .. code-block:: python

            with guest.mkdtemp() as path:
                ...

        :param prefix: if set, the directory name will begin with this
            string.
        :param template: if set, the directory name will follow the
            given naming scheme: the template must end with 6
            consecutive ``X``s, i.e. ``XXXXXX``. All ``X`` letters will
            be replaced with random characters.
        :param parent: if set, new directory will be created under this
            path. Otherwise, the default directory is used.
        """

        output = self.execute(
            self._construct_mkdtemp_command(prefix=prefix, template=template, parent=parent)
        )

        if not output.stdout:
            raise GeneralError(f"Failed to create temporary directory on guest: {output.stderr}")

        path = Path(output.stdout.strip())

        try:
            yield path

        except Exception as exc:
            raise exc

        else:
            self.execute(Command('rm', '-rf', path))


@container
class GuestSshData(GuestData):
    """
    Keys necessary to describe, create, save and restore a guest with SSH
    capability.

    Derived from GuestData, this class adds keys relevant for guests that can be
    reached over SSH.
    """

    port: Optional[int] = field(
        default=None,
        option=('-P', '--port'),
        metavar='PORT',
        help="""
             Port to use for SSH connections instead of the default
             one.
             """,
        normalize=tmt.utils.normalize_optional_int,
    )
    user: str = field(
        default=DEFAULT_USER,
        option=('-u', '--user'),
        metavar='NAME',
        help='A username to use for all guest operations.',
    )
    key: list[Path] = field(
        default_factory=list,
        option=('-k', '--key'),
        metavar='PATH',
        multiple=True,
        help="""
             Private key to use as SSH identity for key-based
             authentication.
             """,
        normalize=tmt.utils.normalize_path_list,
    )
    password: Optional[str] = field(
        default=None,
        option=('-p', '--password'),
        metavar='PASSWORD',
        help="""
             Password to use for password-based authentication.
             """,
    )
    ssh_option: list[str] = field(
        default_factory=list,
        option='--ssh-option',
        metavar="OPTION",
        multiple=True,
        help="""
             Additional SSH option. Value is passed to the ``-o``
             option of ``ssh``, see ``ssh_config(5)`` for supported
             options. Can be specified multiple times.
             """,
        normalize=tmt.utils.normalize_string_list,
    )


class GuestSsh(Guest, CommandCollector):
    """
    Guest provisioned for test execution, capable of accepting SSH connections

    This class implements :py:class:`CommandCollector` to support
    guests in image mode. When running in image mode, commands with
    ``immediately=False`` are collected into a Containerfile
    rather than executed immediately and applied on step completion.

    The following keys are expected in the 'data' dictionary::

        role ....... guest role in the multihost scenario (inherited)
        guest ...... hostname or ip address (inherited)
        become ..... run shell scripts in tests, prepare, and finish with sudo (inherited)
        port ....... port to connect to
        user ....... user name to log in
        key ........ path to the private key (str or list)
        password ... password

    These are by default imported into instance attributes.
    """

    _data_class: type[GuestData] = GuestSshData

    port: Optional[int]
    user: Optional[str]
    key: list[Path]
    password: Optional[str]
    ssh_option: list[str]

    # Master ssh connection process and socket path
    _ssh_master_process_lock: threading.Lock
    _ssh_master_process: Optional['subprocess.Popen[bytes]'] = None

    def __init__(
        self,
        *,
        data: GuestData,
        name: Optional[str] = None,
        parent: Optional[tmt.utils.Common] = None,
        logger: tmt.log.Logger,
    ) -> None:
        self._ssh_master_process_lock = threading.Lock()

        super().__init__(data=data, logger=logger, parent=parent, name=name)

    def collect_command(
        self,
        command: Union[tmt.utils.Command, tmt.utils.ShellScript],
        *,
        sourced_files: Optional[list[Path]] = None,
        cwd: Optional[Path] = None,
        env: Optional[tmt.utils.Environment] = None,
    ) -> None:
        """
        Collect a command for image mode container build.

        Adds a RUN directive to the bootc package manager's Containerfile.
        Uses the same environment and cwd handling as regular execute().
        """

        sourced_files = sourced_files or []

        if not self.facts.is_image_mode or not isinstance(
            self.package_manager, tmt.package_managers.bootc.Bootc
        ):
            return

        # Build the command script using the same approach as execute()
        # Start with environment exports
        collected_commands: ShellScript = ShellScript.from_scripts(
            self._prepare_environment(env).to_shell_exports()
        )

        # Add working directory change (properly quoted like in execute())
        if cwd:
            collected_commands += ShellScript(f'cd {quote(str(cwd))}')

        for file in sourced_files:
            collected_commands += ShellScript(f'source {quote(str(file))}')

        # Add the actual command
        if isinstance(command, tmt.utils.Command):
            collected_commands += command.to_script()
        else:
            collected_commands += command

        collected_command = collected_commands.to_element()

        # Add to the package manager's engine
        self.package_manager.engine.open_containerfile_directives()
        self.package_manager.engine.containerfile_directives.append(f"RUN {collected_command}")
        self.debug(f"Collected command for Containerfile: {collected_command}")

    @property
    def has_collected_commands(self) -> bool:
        """Check if there are collected commands to be applied."""

        if not self.facts.is_image_mode or not isinstance(
            self.package_manager, tmt.package_managers.bootc.Bootc
        ):
            return False

        return bool(self.package_manager.engine.containerfile_directives)

    def flush_collected(self) -> None:
        """
        Build image mode container image from collected commands, switch, and reboot.

        Delegates to the bootc package manager's build_container() method.
        """
        if not self.facts.is_image_mode or not isinstance(
            self.package_manager, tmt.package_managers.bootc.Bootc
        ):
            return

        self.info("building container image from collected commands", "green")
        self.package_manager.build_container()

    def on_step_complete(self, step: 'tmt.steps.Step') -> None:
        """
        Called when a step completes execution.

        Flush collected commands if there are some.

        :param step: the step that has completed.
        """
        if self.has_collected_commands:
            self.flush_collected()

    @functools.cached_property
    def _ssh_guest(self) -> str:
        """
        Return user@guest
        """

        return f'{self.user}@{self.primary_address}'

    @functools.cached_property
    def _is_ssh_master_socket_path_acceptable(self) -> bool:
        """
        Whether the SSH master socket path we create is acceptable by SSH
        """

        if len(str(self._ssh_master_socket_path)) >= SSH_MASTER_SOCKET_LENGTH_LIMIT:
            self.warn(
                "SSH multiplexing will not be used because the SSH master socket path "
                f"'{self._ssh_master_socket_path}' is too long."
            )
            return False

        return True

    @property
    def is_ssh_multiplexing_enabled(self) -> bool:
        """
        Whether SSH multiplexing should be used
        """

        if self.primary_address is None:
            return False

        if not self._is_ssh_master_socket_path_acceptable:
            return False

        return True

    @functools.cached_property
    def _ssh_master_socket_path(self) -> Path:
        """
        Return path to the SSH master socket
        """

        # Can be any step opening the connection
        socket_dir = self.run_workdir / 'ssh-sockets'

        try:
            socket_dir.mkdir(parents=True, exist_ok=True)

        except Exception as exc:
            raise ProvisionError(f"Failed to create SSH socket directory '{socket_dir}'.") from exc

        # Try more informative, but possibly too long path, constructed
        # from pieces humans can easily understand and follow.
        #
        # The template is what seems to be a common template in general
        # SSH discussions, hostname, port, username. Can we use guest
        # name? Maybe, on the other hand, guest name is meaningless
        # outside of its plan, it might be too ambiguous. Starting with
        # what SSH folk uses, we may amend it later.

        # This should be true, otherwise `is_ssh_multiplexing_enabled` would return `False`
        # and nobody would need to use SSH master socket path.
        assert self.primary_address

        guest_id_components: list[str] = [self.primary_address]

        if self.port:
            guest_id_components.append(str(self.port))

        if self.user:
            guest_id_components.append(self.user)

        guest_id = '-'.join(guest_id_components)

        socket_path = _socket_path_trivial(
            socket_dir=socket_dir, guest_id=guest_id, logger=self._logger
        )

        if socket_path is not None:
            self.debug(
                f"SSH master socket path will be '{socket_path}' (trivial method).", level=4
            )

            return socket_path

        # The readable name was too long. Try different approach: use
        # a hash of the pieces, and use just a substring of the hash,
        # not all 64 or whatever characters. If the substring is already
        # in use - extremely unlikely, yet possible - try a slightly
        # longer one.
        socket_path = _socket_path_hash(
            socket_dir=socket_dir, guest_id=guest_id, logger=self._logger
        )

        if socket_path is not None:
            self.debug(f"SSH master socket path will be '{socket_path}' (hash method).", level=4)

            return socket_path

        # Not even the hashing function and short substrings helped.
        # Return the most readable one, and let caller decide whether
        # they use it or not. We run out of options.
        socket_path = _socket_path_trivial(
            socket_dir=socket_dir, guest_id=guest_id, limit_size=False, logger=self._logger
        )

        self.debug(
            f"SSH master socket path will be '{socket_path}' (trivial method, no size limit).",
            level=4,
        )

        return socket_path

    @functools.cached_property
    def _ssh_master_socket_reservation_path(self) -> Path:
        return Path(f'{self._ssh_master_socket_path}.reservation')

    @property
    def _ssh_options(self) -> Command:
        """
        Return common SSH options
        """

        options = BASE_SSH_OPTIONS[:]

        if self.key or self.password:
            # Skip ssh-agent (it adds additional identities)
            options.append('-oIdentitiesOnly=yes')
        if self.port:
            options.append(f'-p{self.port}')
        if self.key:
            for key in self.key:
                options.extend(['-i', key])
        if self.password:
            options.extend(['-oPasswordAuthentication=yes'])
        else:
            # Make sure the connection is rejected when we want key-
            # based authentication only instead of presenting a prompt.
            # Prevents issues like https://github.com/teemtee/tmt/issues/2687
            # from happening and makes the ssh connection more robust
            # by allowing proper re-try mechanisms to kick-in.
            options.extend(['-oPasswordAuthentication=no'])

        # Include the SSH master process
        if self.is_ssh_multiplexing_enabled:
            options.append(f'-S{self._ssh_master_socket_path}')

        options.extend([f'-o{option}' for option in self.ssh_option])

        return Command(*options)

    @property
    def _base_ssh_command(self) -> Command:
        """
        A base SSH command shared by all SSH processes
        """

        command = Command(*(["sshpass", "-p", self.password] if self.password else []), "ssh")

        return command + self._ssh_options

    def _spawn_ssh_master_process(self) -> subprocess.Popen[bytes]:
        """
        Spawn the SSH master process
        """

        # NOTE: do not modify `command`, it might be reused by the caller. To
        # be safe, include it in our own command.
        ssh_master_command = (
            self._base_ssh_command + self._ssh_options + Command("-MNnT", self._ssh_guest)
        )

        self.debug(f"Spawning the SSH master process: {ssh_master_command}")

        return subprocess.Popen(
            ssh_master_command.to_popen(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def _cleanup_ssh_master_process(
        self, signal: _signal.Signals = _signal.SIGTERM, logger: Optional[tmt.log.Logger] = None
    ) -> None:
        logger = logger or self._logger

        if not self.is_ssh_multiplexing_enabled:
            logger.debug(
                'The SSH master process cannot be terminated because it is disabled.', level=3
            )

            return

        with self._ssh_master_process_lock:
            if self._ssh_master_process is None:
                logger.debug(
                    'The SSH master process cannot be terminated because it is unset.', level=3
                )

                return

            logger.debug(
                f'Terminating the SSH master process {self._ssh_master_process.pid}'
                f' with {signal.name}.',
                level=3,
            )

            self._ssh_master_process.send_signal(signal)

            try:
                # TODO: make the deadline configurable
                self._ssh_master_process.wait(timeout=3)

            except subprocess.TimeoutExpired:
                logger.warning(
                    f'Terminating the SSH master process {self._ssh_master_process.pid} timed out.'
                )

            self._ssh_master_process = None

    @property
    def _ssh_command(self) -> Command:
        """
        A base SSH command shared by all SSH processes
        """

        if self.is_ssh_multiplexing_enabled:
            with self._ssh_master_process_lock:
                if self._ssh_master_process is None:
                    self._ssh_master_process = self._spawn_ssh_master_process()

        return self._base_ssh_command

    def _unlink_ssh_master_socket_path(self) -> None:
        if not self.is_ssh_multiplexing_enabled:
            return

        with self._ssh_master_process_lock:
            if not self._ssh_master_socket_path:
                return

            self.debug(f"Remove SSH master socket '{self._ssh_master_socket_path}'.", level=3)

            try:
                self._ssh_master_socket_path.unlink(missing_ok=True)
                self._ssh_master_socket_reservation_path.unlink(missing_ok=True)

            except OSError as error:
                self.debug(f"Failed to remove the SSH master socket: {error}", level=3)

            del self._ssh_master_socket_path
            del self._ssh_master_socket_reservation_path

    def _run_ansible(
        self,
        playbook: AnsibleApplicable,
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

        ansible_command = Command(
            'ansible-playbook', *self._ansible_verbosity(), *self._ansible_extra_args(extra_args)
        )

        # FIXME: cast() - https://github.com/teemtee/tmt/issues/1372
        parent = cast('Provision', self.parent)

        inventory_path = parent.plan.provision.ansible_inventory_path

        self.debug(f"Using Ansible inventory file '{inventory_path}'", level=3)

        # Build command arguments
        ansible_command += Command(
            '--ssh-common-args',
            self._ssh_options.to_element(),
            '-i',
            str(inventory_path),
            '--limit',
            self.name,
            playbook,
        )

        try:
            return self._run_guest_command(
                ansible_command,
                friendly_command=friendly_command,
                silent=silent,
                cwd=parent.plan.worktree,
                env=self._prepare_environment(),
                log=log,
            )
        except tmt.utils.RunError as exc:
            hint = get_hint('ansible-not-available', ignore_missing=False)

            if hint.search_cli_patterns(exc.stderr, exc.stdout, exc.message):
                hint.print(self._logger)

            raise exc

    @property
    def is_ready(self) -> bool:
        """
        Detect guest is ready or not
        """

        # Enough for now, ssh connection can be created later
        return self.primary_address is not None

    @functools.cached_property
    def ansible_host_vars(self) -> dict[str, Any]:
        """
        Get host variables for Ansible inventory with SSH-specific variables.
        """
        return {
            **super().ansible_host_vars,
            'ansible_connection': 'ssh',
            'ansible_user': self.user,
            'ansible_port': self.port,
        }

    def setup(self) -> None:
        super().setup()

        if self.is_dry_run:
            return
        if not self.facts.is_superuser and self.become:
            self.package_manager.install(FileSystemPath('/usr/bin/setfacl'))
            workdir_root = effective_workdir_root()
            self.execute(
                ShellScript(
                    f"""
                    mkdir -p {workdir_root};
                    setfacl -d -m o:rX {workdir_root}
                    """
                )
            )

    @overload
    def execute(
        self,
        command: Union[tmt.utils.Command, tmt.utils.ShellScript],
        cwd: Optional[Path] = None,
        env: Optional[tmt.utils.Environment] = None,
        friendly_command: Optional[str] = None,
        test_session: bool = False,
        immediately: Literal[True] = True,
        tty: bool = False,
        silent: bool = False,
        log: Optional[tmt.log.LoggingFunction] = None,
        interactive: bool = False,
        on_process_start: Optional[OnProcessStartCallback] = None,
        on_process_end: Optional[OnProcessEndCallback] = None,
        sourced_files: Optional[list[Path]] = None,
        **kwargs: Any,
    ) -> tmt.utils.CommandOutput:
        pass

    @overload
    def execute(
        self,
        command: Union[tmt.utils.Command, tmt.utils.ShellScript],
        cwd: Optional[Path] = None,
        env: Optional[tmt.utils.Environment] = None,
        friendly_command: Optional[str] = None,
        test_session: bool = False,
        immediately: Literal[False] = False,
        tty: bool = False,
        silent: bool = False,
        log: Optional[tmt.log.LoggingFunction] = None,
        interactive: bool = False,
        on_process_start: Optional[OnProcessStartCallback] = None,
        on_process_end: Optional[OnProcessEndCallback] = None,
        sourced_files: Optional[list[Path]] = None,
        **kwargs: Any,
    ) -> Optional[tmt.utils.CommandOutput]:
        pass

    def execute(
        self,
        command: Union[tmt.utils.Command, tmt.utils.ShellScript],
        cwd: Optional[Path] = None,
        env: Optional[tmt.utils.Environment] = None,
        friendly_command: Optional[str] = None,
        test_session: bool = False,
        immediately: bool = True,
        tty: bool = False,
        silent: bool = False,
        log: Optional[tmt.log.LoggingFunction] = None,
        interactive: bool = False,
        on_process_start: Optional[OnProcessStartCallback] = None,
        on_process_end: Optional[OnProcessEndCallback] = None,
        sourced_files: Optional[list[Path]] = None,
        **kwargs: Any,
    ) -> Optional[tmt.utils.CommandOutput]:
        """
        Execute a command on the guest.

        :param command: either a command or a shell script to execute.
        :param cwd: execute command in this directory on the guest.
        :param env: if set, set these environment variables before running the command.
        :param friendly_command: nice, human-friendly representation of the command.
        :param test_session: if True, this is the actual test being run.
        :param immediately: if False, the command may be collected for later
            batch execution on guests that support it (e.g., bootc guests).
            Commands with ``immediately=True`` (default) are always executed
            right away. Use ``immediately=False`` for commands that modify
            system state and can be batched (e.g., package installation).
            When a command is deferred, ``None`` is returned instead of
            :py:class:`CommandOutput`.
        :returns: command output, or ``None`` if the command was deferred
            for batch execution (when ``immediately=False`` on supported guests).
        """

        sourced_files = sourced_files or []

        # For guests in image mode collect non testing commands with
        # immediately=False for later batch execution.
        if not immediately and self.facts.is_image_mode:
            self.collect_command(command, sourced_files=sourced_files, cwd=cwd, env=env)
            return None

        # Abort if guest is unavailable
        if self.primary_address is None and not self.is_dry_run:
            raise tmt.utils.GeneralError('The guest is not available.')

        ssh_command: tmt.utils.Command = self._ssh_command

        # Run in interactive mode if requested
        if interactive:
            ssh_command += Command('-t')

        # Force ssh to allocate pseudo-terminal if requested. Without a pseudo-terminal,
        # remote processes spawned by SSH would keep running after SSH process death, e.g.
        # in the case of a timeout.
        #
        # Note that polite request, `-t`, is not enough since `ssh` itself has no pseudo-terminal,
        # and a single `-t` wouldn't have the necessary effect.
        if test_session or tty:
            ssh_command += Command('-tt')

        # Accumulate all necessary commands - they will form a "shell" script, a single
        # string passed to SSH to execute on the remote machine.
        remote_commands: ShellScript = ShellScript.from_scripts(
            self._prepare_environment(env).to_shell_exports()
        )

        # Change to given directory on guest if cwd provided
        if cwd:
            remote_commands += ShellScript(f'cd {quote(str(cwd))}')

        for file in sourced_files:
            remote_commands += ShellScript(f'source {quote(str(file))}')

        if isinstance(command, Command):
            remote_commands += command.to_script()

        else:
            remote_commands += command

        remote_command = remote_commands.to_element()

        ssh_command += [self._ssh_guest, remote_command]

        self.debug(f"Execute command '{remote_command}' on guest '{self.primary_address}'.")

        output = self._run_guest_command(
            ssh_command,
            log=log,
            friendly_command=friendly_command or str(command),
            silent=silent,
            cwd=cwd,
            interactive=interactive,
            on_process_start=on_process_start,
            on_process_end=on_process_end,
            **kwargs,
        )

        # Drop ssh connection closed messages, #2524
        if test_session and output.stdout:
            # Get last line index
            last_line_index = output.stdout.rfind(os.linesep, 0, -2)
            # Drop the connection closed message line, keep the ending lineseparator
            if (
                'Shared connection to ' in output.stdout[last_line_index:]
                or 'Connection to ' in output.stdout[last_line_index:]
            ):
                output = dataclasses.replace(
                    output, stdout=output.stdout[: last_line_index + len(os.linesep)]
                )

        return output

    def _assert_rsync(self) -> None:
        """
        Make sure ``rsync`` is installed on the guest.
        """

        # Refresh the fact first if it's unknown. This will prevent us
        # trying to install rsync if it's (still, or already) installed,
        # with whatever price such an attempt comes with.
        if self.facts.has_rsync is None:
            self.facts.sync(self, 'has_rsync')

        if self.facts.has_rsync:
            return

        self.debug('rsync has not been confirmed on the guest, try installing it')

        try:
            # Refresh package metadata to ensure packages are locatable,
            # this is needed for example on fresh Debian installs.
            self.package_manager.refresh_metadata()
            self.package_manager.install(Package('rsync'))

        except Exception as exc:
            raise tmt.utils.GeneralError(
                f"Failed to verify rsync presence on the guest."
                f" This often means there is a problem with its package manager,"
                f" or logging in as '{self.user}' does not work, or the network"
                f" connection itself."
            ) from exc

        # We changed the state of the guest, refresh the fact.
        self.facts.sync(self, 'has_rsync')

    def push(
        self,
        source: Optional[Path] = None,
        destination: Optional[Path] = None,
        options: Optional[TransferOptions] = None,
        superuser: bool = False,
    ) -> None:
        """
        Push files to the guest.

        By default the whole plan workdir is synced to the same location
        on the guest. Use the ``source`` and ``destination`` to sync
        custom locations.

        :param source: if set, this path will be uploaded to the guest.
            If not set, plan workdir is uploaded.
        :param destination: if set, content will be uploaded to this
            path. If not set, root (``/``) is used.
        :param options: custom transfer options to use instead of
            :py:data:`DEFAULT_PUSH_OPTIONS`.
        :param superuser: if set, use ``sudo`` if :py:attr:`user` is not
            privileged. It is necessary for pushing to locations that
            only privileged users are allowed to modify.
        """

        # Abort if guest is unavailable
        if self.primary_address is None and not self.is_dry_run:
            raise tmt.utils.GeneralError('The guest is not available.')

        self._assert_rsync()

        # Prepare options and the push command
        options = options or DEFAULT_PUSH_OPTIONS
        if destination is None:
            destination = Path("/")
        if source is None:
            source = self.plan_workdir
            self.debug(f"Push workdir to guest '{self.primary_address}'.")
        else:
            self.debug(f"Copy '{source}' to '{destination}' on the guest.")

        cmd = Command('rsync')

        if superuser and self.user != 'root':
            cmd += ['--rsync-path', 'sudo rsync']

        # When rsync-ing directories, make sure we do not copy to a subfolder (/foo/bar/bar)
        path_suffix = "/" if options.recursive else ""

        cmd += [
            *options.to_rsync(),
            "-e",
            self._ssh_command.to_element(),
            f"{source}{path_suffix}",
            f"{self._ssh_guest}:{destination}{path_suffix}",
        ]

        try:
            if options.create_destination:
                self.execute(Command("mkdir", "-p", destination.parent), silent=True)
            self._run_guest_command(cmd, silent=True)

        except tmt.utils.RunError as exc:
            # Provide a reasonable error to the user
            raise tmt.utils.GeneralError(
                f"Failed to push workdir to the guest. This usually means "
                f"that login as '{self.user}' to the guest does not work."
            ) from exc

    def pull(
        self,
        source: Optional[Path] = None,
        destination: Optional[Path] = None,
        options: Optional[TransferOptions] = None,
    ) -> None:
        """
        Pull files from the guest.

        By default the whole plan workdir is synced from the same
        location on the guest. Use the ``source`` and ``destination`` to
        sync custom locations.

        :param source: if set, this path will be downloaded from the
            guest. If not set, plan workdir is downloaded.
        :param destination: if set, content will be downloaded to this
            path. If not set, root (``/``) is used.
        :param options: custom transfer options to use instead of
            :py:data:`DEFAULT_PULL_OPTIONS`.
        """

        # Abort if guest is unavailable
        if self.primary_address is None and not self.is_dry_run:
            raise tmt.utils.GeneralError('The guest is not available.')

        self._assert_rsync()

        # Prepare options and the pull command
        options = options or DEFAULT_PULL_OPTIONS
        if destination is None:
            destination = Path("/")
        if source is None:
            source = self.plan_workdir
            self.debug(f"Pull workdir from guest '{self.primary_address}'.")
        else:
            self.debug(f"Copy '{source}' from the guest to '{destination}'.")

        try:
            self._run_guest_command(
                Command(
                    "rsync",
                    *options.to_rsync(),
                    "-e",
                    self._ssh_command.to_element(),
                    f"{self._ssh_guest}:{source}",
                    destination,
                ),
                silent=True,
            )

        except tmt.utils.RunError as exc:
            # Provide a reasonable error to the user
            raise tmt.utils.GeneralError(
                f"Failed to pull workdir from the guest. "
                f"This usually means that login as '{self.user}' "
                f"to the guest does not work."
            ) from exc

    def suspend(self) -> None:
        """
        Suspend the guest.

        Perform any actions necessary before quitting step and tmt. The
        guest may be reused by future tmt invocations.
        """

        super().suspend()

        # Close the master ssh connection
        self._cleanup_ssh_master_process()

        # Remove the ssh socket
        self._unlink_ssh_master_socket_path()

    def stop(self) -> None:
        """
        Stop the guest

        Shut down a running guest instance so that it does not consume
        any memory or cpu resources. If needed, perform any actions
        necessary to store the instance status to disk.
        """

        self.suspend()

    @overload
    def reboot(
        self,
        mode: HardRebootModes = RebootMode.HARD,
        command: None = None,
        waiting: Optional[Waiting] = None,
    ) -> bool:
        pass

    @overload
    def reboot(
        self,
        mode: SoftRebootModes = RebootMode.SOFT,
        command: Optional[Union[Command, ShellScript]] = None,
        waiting: Optional[Waiting] = None,
    ) -> bool:
        pass

    def reboot(
        self,
        mode: RebootMode = RebootMode.SOFT,
        command: Optional[Union[Command, ShellScript]] = None,
        waiting: Optional[Waiting] = None,
    ) -> bool:
        if mode == RebootMode.SYSTEMD_SOFT:
            default_reboot_command = tmt.steps.DEFAULT_SYSTEMD_SOFT_REBOOT_COMMAND

        elif mode == RebootMode.SOFT:
            default_reboot_command = tmt.steps.DEFAULT_SOFT_REBOOT_COMMAND

        else:
            raise tmt.utils.ProvisionError(
                f"Guest '{self.multihost_name}' does not support hard reboot."
            )

        if self.become:
            default_reboot_command = ShellScript(
                f'sudo {default_reboot_command.to_shell_command()}'
            )

        command = command or default_reboot_command
        waiting = waiting or default_reboot_waiting()

        self.debug(f"{mode.name.capitalize()} reboot using command '{command}'.")

        return self.perform_reboot(mode, lambda: self.execute(command), waiting)

    def remove(self) -> None:
        """
        Remove the guest

        Completely remove all guest instance data so that it does not
        consume any disk resources.
        """

        self.debug(f"Doing nothing to remove guest '{self.primary_address}'.")
