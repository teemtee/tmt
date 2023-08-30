import ast
import collections
import dataclasses
import datetime
import enum
import os
import random
import re
import shlex
import string
import subprocess
import tempfile
from shlex import quote
from typing import (
    TYPE_CHECKING,
    Any,
    DefaultDict,
    Dict,
    Generator,
    List,
    Optional,
    Tuple,
    Type,
    TypeVar,
    Union,
    cast,
    overload,
    )

import click
import fmf
from click import echo

import tmt
import tmt.hardware
import tmt.log
import tmt.plugins
import tmt.steps
import tmt.utils
from tmt.options import option
from tmt.plugins import PluginRegistry
from tmt.steps import Action
from tmt.utils import Command, Path, ShellScript, cached_property, field

if TYPE_CHECKING:
    import tmt.base
    import tmt.cli


# Timeout in seconds of waiting for a connection after reboot
CONNECTION_TIMEOUT = 5 * 60

# When waiting for guest to recover from reboot, try re-connecting every
# this many seconds.
RECONNECT_WAIT_TICK = 5
RECONNECT_WAIT_TICK_INCREASE = 1.0

# Default rsync options
DEFAULT_RSYNC_OPTIONS = [
    "-s", "-R", "-r", "-z", "--links", "--safe-links", "--delete"]

DEFAULT_RSYNC_PUSH_OPTIONS = ["-s", "-R", "-r", "-z", "--links", "--safe-links", "--delete"]
DEFAULT_RSYNC_PULL_OPTIONS = ["-s", "-R", "-r", "-z", "--links", "--safe-links", "--protect-args"]


def format_guest_full_name(name: str, role: Optional[str]) -> str:
    """ Render guest's full name, i.e. name and its role """

    if role is None:
        return name

    return f'{name} ({role})'


class CheckRsyncOutcome(enum.Enum):
    ALREADY_INSTALLED = 'already-installed'
    INSTALLED = 'installed'


class GuestPackageManager(enum.Enum):
    DNF = 'dnf'
    DNF5 = 'dnf5'
    YUM = 'yum'
    RPM_OSTREE = 'rpm-ostree'


T = TypeVar('T')


@dataclasses.dataclass
class GuestFacts(tmt.utils.SerializableContainer):
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
    package_manager: Optional[GuestPackageManager] = field(
        # cast: since the default is None, mypy cannot infere the full type,
        # and reports `package_manager` parameter to be `object`.
        default=cast(Optional[GuestPackageManager], None),
        serialize=lambda package_manager: package_manager.value if package_manager else None,
        unserialize=lambda raw_value: GuestPackageManager(raw_value) if raw_value else None)

    has_selinux: Optional[bool] = None
    is_superuser: Optional[bool] = None

    os_release_content: Dict[str, str] = field(default_factory=dict)
    lsb_release_content: Dict[str, str] = field(default_factory=dict)

    # TODO nothing but a fancy helper, to check for some special errors that
    # may appear this soon in provisioning. But, would it make sense to put
    # this detection into the `GuestSsh.execute()` method?
    def _execute(
            self,
            guest: 'Guest',
            command: Command) -> Optional[tmt.utils.CommandOutput]:
        """
        Run a command on the given guest.

        On top of the basic :py:meth:`Guest.execute`, this helper is able to
        detect a common issue with guest access. Facts are the first info tmt
        fetches from the guest, and would raise the error as soon as possible.

        :returns: command output if the command quit with a zero exit code,
            ``None`` otherwise.
        :raises tmt.units.GeneralError: when logging into the guest fails
            because of a username mismatch.
        """

        try:
            return guest.execute(command, silent=True)

        except tmt.utils.RunError as exc:
            if exc.stdout and 'Please login as the user' in exc.stdout:
                raise tmt.utils.GeneralError(f'Login to the guest failed.\n{exc.stdout}') from exc

        return None

    def _fetch_keyval_file(self, guest: 'Guest', filepath: Path) -> Dict[str, str]:
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

        content: Dict[str, str] = {}

        output = self._execute(guest, Command('cat', str(filepath)))

        if not output or not output.stdout:
            return content

        def _iter_pairs() -> Generator[Tuple[str, str], None, None]:
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
                        f" {line}")

                key, value = match.groups()

                if value and value[0] in '"\'':
                    value = ast.literal_eval(value)

                yield key, value

        return dict(_iter_pairs())

    def _probe(
            self,
            guest: 'Guest',
            probes: List[Tuple[Command, T]]) -> Optional[T]:
        """
        Find a first successfull command.

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

    def _query(
            self,
            guest: 'Guest',
            probes: List[Tuple[Command, str]]) -> Optional[str]:
        """
        Find a first successfull command, and extract info from its output.

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
        return self._query(
            guest,
            [
                (Command('arch'), r'(.+)')
                ])

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
                (Command('cat', '/etc/fedora-release'), r'(.*)')
                ])

    def _query_kernel_release(self, guest: 'Guest') -> Optional[str]:
        return self._query(
            guest,
            [
                (Command('uname', '-r'), r'(.+)')
                ])

    def _query_package_manager(self, guest: 'Guest') -> Optional[GuestPackageManager]:
        return self._probe(
            guest,
            [
                (Command('stat', '/run/ostree-booted'), GuestPackageManager.RPM_OSTREE),
                (Command('dnf5', '--version'), GuestPackageManager.DNF5),
                (Command('dnf', '--version'), GuestPackageManager.DNF),
                (Command('yum', '--version'), GuestPackageManager.YUM),
                # And, one day, we'd follow up on this with...
                # (Command('dpkg', '-l', 'apt'), 'apt')
                ])

    def _query_has_selinux(self, guest: 'Guest') -> Optional[bool]:
        """
        For detection ``/proc/filesystems`` is used, see ``man 5 filesystems`` for details.
        """

        output = self._execute(guest, Command('cat', '/proc/filesystems'))

        if output is None or output.stdout is None:
            return None

        return 'selinux' in output.stdout

    def _query_is_superuser(self, guest: 'Guest') -> Optional[bool]:
        output = self._execute(guest, Command('whoami'))

        if output is None or output.stdout is None:
            return None

        return output.stdout.strip() == 'root'

    def sync(self, guest: 'Guest') -> None:
        """ Update stored facts to reflect the given guest """

        self.os_release_content = self._fetch_keyval_file(guest, Path('/etc/os-release'))
        self.lsb_release_content = self._fetch_keyval_file(guest, Path('/etc/lsb-release'))

        self.arch = self._query_arch(guest)
        self.distro = self._query_distro(guest)
        self.kernel_release = self._query_kernel_release(guest)
        self.package_manager = self._query_package_manager(guest)
        self.has_selinux = self._query_has_selinux(guest)
        self.is_superuser = self._query_is_superuser(guest)

        self.in_sync = True


def normalize_hardware(
        key_address: str,
        raw_hardware: Optional[tmt.hardware.Spec],
        logger: tmt.log.Logger) -> Optional[tmt.hardware.Hardware]:
    """
    Normalize a ``hardware`` key value.

    :param key_address: location of the key being that's being normalized.
    :param logger: logger to use for logging.
    :param raw_hardware: input from either command line or fmf node.
    """

    if raw_hardware is None:
        return None

    # From command line
    if isinstance(raw_hardware, (list, tuple)):
        merged: DefaultDict[str, Any] = collections.defaultdict(dict)

        for raw_datum in raw_hardware:
            components = tmt.hardware.ConstraintComponents.from_spec(raw_datum)

            if components.child_name:
                merged[components.name][components.child_name] = \
                    f'{components.operator} {components.value}'

            else:
                merged[components.name] = f'{components.operator} {components.value}'

        return tmt.hardware.Hardware.from_spec(dict(merged))

    # From fmf
    return tmt.hardware.Hardware.from_spec(raw_hardware)


@dataclasses.dataclass
class GuestData(tmt.utils.SerializableContainer):
    """
    Keys necessary to describe, create, save and restore a guest.

    Very basic set of keys shared across all known guest classes.
    """

    # guest role in the multihost scenario
    role: Optional[str] = None
    # hostname or ip address
    guest: Optional[str] = None

    facts: GuestFacts = field(
        default_factory=GuestFacts,
        serialize=lambda facts: facts.to_serialized(),  # type: ignore[attr-defined]
        unserialize=lambda serialized: GuestFacts.from_serialized(serialized)
        )

    hardware: Optional[tmt.hardware.Hardware] = field(
        default=cast(Optional[tmt.hardware.Hardware], None),
        option='--hardware',
        help='Add a hardware requirement.',
        metavar='KEY=VALUE',
        multiple=True,
        normalize=normalize_hardware,
        serialize=lambda hardware: hardware.to_spec() if hardware else None,
        unserialize=lambda serialized: tmt.hardware.Hardware.from_spec(serialized)
        if serialized is not None else None)

    def show(
            self,
            *,
            keys: Optional[List[str]] = None,
            verbose: int = 0,
            logger: tmt.log.Logger) -> None:
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

            elif isinstance(value, tmt.hardware.Hardware):
                printable_value = tmt.utils.dict_to_yaml(value.to_spec())

            else:
                printable_value = str(value)

            logger.info(tmt.utils.key_to_option(key), printable_value, color='green')


class Guest(tmt.utils.Common):
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

    These are by default imported into instance attributes.
    """

    # Used by save() to construct the correct container for keys.
    _data_class: Type[GuestData] = GuestData

    role: Optional[str]
    guest: Optional[str]

    hardware: Optional[tmt.hardware.Hardware]

    # Flag to indicate localhost guest, requires special handling
    localhost = False

    # TODO: do we need this list? Can whatever code is using it use _data_class directly?
    # List of supported keys
    # (used for import/export to/from attributes during load and save)
    @property
    def _keys(self) -> List[str]:
        return list(self._data_class.keys())

    def __init__(self,
                 *,
                 data: GuestData,
                 name: Optional[str] = None,
                 parent: Optional[tmt.utils.Common] = None,
                 logger: tmt.log.Logger) -> None:
        """ Initialize guest data """
        super().__init__(logger=logger, parent=parent, name=name)

        self.load(data)

    def _random_name(self, prefix: str = '', length: int = 16) -> str:
        """ Generate a random name """
        # Append at least 5 random characters
        min_random_part = max(5, length - len(prefix))
        name = prefix + ''.join(
            random.choices(string.ascii_letters, k=min_random_part))
        # Return tail (containing random characters) of name
        return name[-length:]

    def _tmt_name(self) -> str:
        """ Generate a name prefixed with tmt run id """
        # FIXME: cast() - https://github.com/teemtee/tmt/issues/1372
        parent = cast(Provision, self.parent)

        assert parent.plan.my_run is not None  # narrow type
        assert parent.plan.my_run.workdir is not None  # narrow type
        run_id = parent.plan.my_run.workdir.name
        return self._random_name(prefix=f"tmt-{run_id[-3:]}-")

    @cached_property
    def multihost_name(self) -> str:
        """ Return guest's multihost name, i.e. name and its role """

        return format_guest_full_name(self.name, self.role)

    @property
    def is_ready(self) -> bool:
        """ Detect guest is ready or not """

        raise NotImplementedError

    @classmethod
    def options(cls, how: Optional[str] = None) -> List[tmt.options.ClickOptionDecoratorType]:
        """ Prepare command line options related to guests """
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
        return self._data_class.extract_from(self)

    def wake(self) -> None:
        """
        Wake up the guest

        Perform any actions necessary after step wake up to be able to
        attach to a running guest instance and execute commands. Called
        after load() is completed so all guest data should be prepared.
        """
        self.debug(f"Doing nothing to wake up guest '{self.guest}'.")

    def start(self) -> None:
        """
        Start the guest

        Get a new guest instance running. This should include preparing
        any configuration necessary to get it started. Called after
        load() is completed so all guest data should be available.
        """
        self.debug(f"Doing nothing to start guest '{self.guest}'.")

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
    def facts(self, facts: Union[GuestFacts, Dict[str, Any]]) -> None:
        if isinstance(facts, GuestFacts):
            self.__dict__['facts'] = facts

        else:
            self.__dict__['facts'] = GuestFacts.from_serialized(facts)

    def details(self) -> None:
        """ Show guest details such as distro and kernel """

        self.info('multihost name', self.multihost_name, 'green')

        # Skip distro & kernel check in dry mode
        if self.opt('dry'):
            return

        self.info('arch', self.facts.arch or 'unknown', 'green')
        self.info('distro', self.facts.distro or 'unknown', 'green')
        self.verbose('kernel', self.facts.kernel_release or 'unknown', 'green')
        self.verbose(
            'package manager',
            self.facts.package_manager.value if self.facts.package_manager else 'unknown',
            'green')
        self.verbose('selinux', 'yes' if self.facts.has_selinux else 'no', 'green')
        self.verbose('is superuser', 'yes' if self.facts.is_superuser else 'no', 'green')

    def _ansible_verbosity(self) -> List[str]:
        """ Prepare verbose level based on the --debug option count """
        if self.debug_level < 3:
            return []
        return ['-' + (self.debug_level - 2) * 'v']

    @staticmethod
    def _ansible_extra_args(extra_args: Optional[str]) -> List[str]:
        """ Prepare extra arguments for ansible-playbook"""
        if extra_args is None:
            return []
        return shlex.split(str(extra_args))

    def _ansible_summary(self, output: Optional[str]) -> None:
        """ Check the output for ansible result summary numbers """
        if not output:
            return
        keys = 'ok changed unreachable failed skipped rescued ignored'.split()
        for key in keys:
            matched = re.search(rf'^.*\s:\s.*{key}=(\d+).*$', output, re.M)
            if matched and int(matched.group(1)) > 0:
                tasks = fmf.utils.listed(matched.group(1), 'task')
                self.verbose(key, tasks, 'green')

    def _ansible_playbook_path(self, playbook: Path) -> Path:
        """ Prepare full ansible playbook path """
        self.debug(f"Applying playbook '{playbook}' on guest '{self.guest}'.")
        # FIXME: cast() - https://github.com/teemtee/tmt/issues/1372
        parent = cast(Provision, self.parent)
        assert parent.plan.my_run is not None  # narrow type
        assert parent.plan.my_run.tree is not None  # narrow type
        assert parent.plan.my_run.tree.root is not None  # narrow type
        # Playbook paths should be relative to the metadata tree root
        playbook = parent.plan.my_run.tree.root / playbook.unrooted()
        self.debug(f"Playbook full path: '{playbook}'", level=2)
        return playbook

    def _prepare_environment(
        self,
        execute_environment: Optional[tmt.utils.EnvironmentType] = None
            ) -> tmt.utils.EnvironmentType:
        """ Prepare dict of environment variables """
        # Prepare environment variables so they can be correctly passed
        # to shell. Create a copy to prevent modifying source.
        environment: tmt.utils.EnvironmentType = {}
        environment.update(execute_environment or {})
        # Plan environment and variables provided on the command line
        # override environment provided to execute().
        # FIXME: cast() - https://github.com/teemtee/tmt/issues/1372
        parent = cast(Provision, self.parent)
        environment.update(parent.plan.environment)
        return environment

    @staticmethod
    def _export_environment(environment: tmt.utils.EnvironmentType) -> List[ShellScript]:
        """ Prepare shell export of environment variables """
        if not environment:
            return []
        return [
            ShellScript(f'export {variable}')
            for variable in tmt.utils.shell_variables(environment)
            ]

    def _run_guest_command(
            self,
            command: Command,
            friendly_command: Optional[str] = None,
            silent: bool = False,
            cwd: Optional[Path] = None,
            env: Optional[tmt.utils.EnvironmentType] = None,
            interactive: bool = False,
            log: Optional[tmt.log.LoggingFunction] = None,
            **kwargs: Any) -> tmt.utils.CommandOutput:
        """
        Run a command, local or remote, related to the guest.

        A rather thin wrapper of :py:meth:`run` whose purpose is to be a single
        point through all commands related to a guest must go through. We expect
        consistent logging from such commands, be it an ``ansible-playbook`
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
            log=log if log else self._command_verbose_logger,
            **kwargs)

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

        raise NotImplementedError

    def ansible(
            self,
            playbook: Path,
            extra_args: Optional[str] = None,
            friendly_command: Optional[str] = None,
            log: Optional[tmt.log.LoggingFunction] = None,
            silent: bool = False) -> None:
        """
        Run an Ansible playbook on the guest.

        A wrapper for :py:meth:`_run_ansible` which is reponsible for running
        the playbook while this method makes sure our logging is consistent.

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

        output = self._run_ansible(
            playbook,
            extra_args=extra_args,
            friendly_command=friendly_command,
            log=log if log else self._command_verbose_logger,
            silent=silent)

        self._ansible_summary(output.stdout)

    @overload
    def execute(self,
                command: tmt.utils.ShellScript,
                cwd: Optional[Path] = None,
                env: Optional[tmt.utils.EnvironmentType] = None,
                friendly_command: Optional[str] = None,
                test_session: bool = False,
                silent: bool = False,
                log: Optional[tmt.log.LoggingFunction] = None,
                interactive: bool = False,
                **kwargs: Any) -> tmt.utils.CommandOutput:
        pass

    @overload
    def execute(self,
                command: tmt.utils.Command,
                cwd: Optional[Path] = None,
                env: Optional[tmt.utils.EnvironmentType] = None,
                friendly_command: Optional[str] = None,
                test_session: bool = False,
                silent: bool = False,
                log: Optional[tmt.log.LoggingFunction] = None,
                interactive: bool = False,
                **kwargs: Any) -> tmt.utils.CommandOutput:
        pass

    def execute(self,
                command: Union[tmt.utils.Command, tmt.utils.ShellScript],
                cwd: Optional[Path] = None,
                env: Optional[tmt.utils.EnvironmentType] = None,
                friendly_command: Optional[str] = None,
                test_session: bool = False,
                silent: bool = False,
                log: Optional[tmt.log.LoggingFunction] = None,
                interactive: bool = False,
                **kwargs: Any) -> tmt.utils.CommandOutput:
        """
        Execute a command on the guest.

        :param command: either a command or a shell script to execute.
        :param cwd: if set, execute command in this directory on the guest.
        :param env: if set, set these environment variables before running the command.
        :param friendly_command: nice, human-friendly representation of the command.
        """

        raise NotImplementedError

    def push(self,
             source: Optional[Path] = None,
             destination: Optional[Path] = None,
             options: Optional[List[str]] = None,
             superuser: bool = False) -> None:
        """
        Push files to the guest
        """

        raise NotImplementedError

    def pull(self,
             source: Optional[Path] = None,
             destination: Optional[Path] = None,
             options: Optional[List[str]] = None,
             extend_options: Optional[List[str]] = None) -> None:
        """
        Pull files from the guest
        """

        raise NotImplementedError

    def stop(self) -> None:
        """
        Stop the guest

        Shut down a running guest instance so that it does not consume
        any memory or cpu resources. If needed, perform any actions
        necessary to store the instance status to disk.
        """

        raise NotImplementedError

    def reboot(
            self,
            hard: bool = False,
            command: Optional[Union[Command, ShellScript]] = None,
            timeout: Optional[int] = None) -> bool:
        """
        Reboot the guest, return True if successful

        Parameter 'hard' set to True means that guest should be
        rebooted by way which is not clean in sense that data can be
        lost. When set to False reboot should be done gracefully.

        Use the 'command' parameter to specify a custom reboot command
        instead of the default 'reboot'.

        Parameter 'timeout' can be used to specify time (in seconds) to
        wait for the guest to come back up after rebooting.
        """

        raise NotImplementedError

    def reconnect(
            self,
            timeout: Optional[int] = None,
            tick: float = RECONNECT_WAIT_TICK,
            tick_increase: float = RECONNECT_WAIT_TICK_INCREASE
            ) -> bool:
        """
        Ensure the connection to the guest is working

        The default timeout is 5 minutes. Custom number of seconds can be
        provided in the `timeout` parameter. This may be useful when long
        operations (such as system upgrade) are performed.
        """
        # The default is handled here rather than in the argument so that
        # the caller can pass in None as an argument (i.e. don't care value)
        timeout = timeout or CONNECTION_TIMEOUT
        self.debug("Wait for a connection to the guest.")

        def try_whoami() -> None:
            try:
                self.execute(Command('whoami'), silent=True)

            except tmt.utils.RunError:
                raise tmt.utils.WaitingIncompleteError

        try:
            tmt.utils.wait(
                self,
                try_whoami,
                datetime.timedelta(seconds=timeout),
                tick=tick,
                tick_increase=tick_increase)

        except tmt.utils.WaitingTimedOutError:
            self.debug("Connection to guest failed after reboot.")
            return False

        return True

    def remove(self) -> None:
        """
        Remove the guest

        Completely remove all guest instance data so that it does not
        consume any disk resources.
        """
        self.debug(f"Doing nothing to remove guest '{self.guest}'.")

    def _check_rsync(self) -> CheckRsyncOutcome:
        """
        Make sure that rsync is installed on the guest

        On read-only distros install it under the '/root/pkg' directory.
        Returns 'already installed' when rsync is already present.
        """

        # Check for rsync (nothing to do if already installed)
        self.debug("Ensure that rsync is installed on the guest.")
        try:
            self.execute(Command('rsync', '--version'))
            return CheckRsyncOutcome.ALREADY_INSTALLED
        except tmt.utils.RunError:
            pass

        # Check the package manager
        self.debug("Check the package manager.")
        try:
            self.execute(Command('dnf', '--version'))
            package_manager = "dnf"
        except tmt.utils.RunError:
            package_manager = "yum"

        # Install under '/root/pkg' for read-only distros
        # (for now the check is based on 'rpm-ostree' presence)
        # FIXME: Find a better way how to detect read-only distros
        self.debug("Check for a read-only distro.")
        try:
            self.execute(Command('rpm-ostree', '--version'))
            readonly = (
                " --installroot=/root/pkg --releasever / "
                "&& ln -sf /root/pkg/bin/rsync /usr/local/bin/rsync")
        except tmt.utils.RunError:
            readonly = ""

        # Install the rsync
        self.execute(ShellScript(f"{package_manager} install -y rsync" + readonly))

        return CheckRsyncOutcome.INSTALLED

    @classmethod
    def requires(cls) -> List['tmt.base.Dependency']:
        """ All requirements of the guest implementation """
        return []


@dataclasses.dataclass
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
        help='Use specific port to connect to.',
        normalize=tmt.utils.normalize_optional_int)
    user: Optional[str] = field(
        default=None,
        option=('-u', '--user'),
        metavar='USERNAME',
        help='Username to use for all guest operations.')
    key: List[str] = field(
        default_factory=list,
        option=('-k', '--key'),
        metavar='PATH',
        help='Private key for login into the guest system.',
        normalize=tmt.utils.normalize_string_list)
    password: Optional[str] = field(
        default=None,
        option=('-p', '--password'),
        metavar='PASSWORD',
        help='Password for login into the guest system.')
    ssh_option: List[str] = field(
        default_factory=list,
        option='--ssh-option',
        metavar="OPTION",
        multiple=True,
        help="Specify an additional SSH option. "
        "Value is passed to SSH's -o option, see ssh_config(5) for "
        "supported options. Can be specified multiple times.",
        normalize=tmt.utils.normalize_string_list)


class GuestSsh(Guest):
    """
    Guest provisioned for test execution, capable of accepting SSH connections

    The following keys are expected in the 'data' dictionary::

        role ....... guest role in the multihost scenario (inherited)
        guest ...... hostname or ip address (inherited)
        port ....... port to connect to
        user ....... user name to log in
        key ........ path to the private key (str or list)
        password ... password

    These are by default imported into instance attributes.
    """

    _data_class: Type[GuestData] = GuestSshData

    port: Optional[int]
    user: Optional[str]
    key: List[Path]
    password: Optional[str]
    ssh_option: List[str]

    # Master ssh connection process and socket path
    _ssh_master_process: Optional['subprocess.Popen[bytes]'] = None
    _ssh_socket_path: Optional[Path] = None

    def _ssh_guest(self) -> str:
        """ Return user@guest """
        return f'{self.user}@{self.guest}'

    def _ssh_socket(self) -> Path:
        """ Prepare path to the master connection socket """
        if not self._ssh_socket_path:
            # Use '/run/user/uid' if it exists, '/tmp' otherwise
            run_dir = Path(f"/run/user/{os.getuid()}")
            socket_dir = run_dir / "tmt" if run_dir.is_dir() else Path("/tmp")
            socket_dir.mkdir(exist_ok=True)
            self._ssh_socket_path = Path(tempfile.mktemp(dir=socket_dir))
        return self._ssh_socket_path

    def _ssh_options(self) -> Command:
        """ Return common ssh options (list or joined) """
        options = [
            '-oForwardX11=no',
            '-oStrictHostKeyChecking=no',
            '-oUserKnownHostsFile=/dev/null',
            # Prevent ssh from disconnecting if no data has been
            # received from the server for a long time (#868).
            '-oServerAliveInterval=60',
            '-oServerAliveCountMax=5',
            ]
        if self.key or self.password:
            # Skip ssh-agent (it adds additional identities)
            options.append('-oIdentitiesOnly=yes')
        if self.port:
            options.append(f'-p{self.port}')
        if self.key:
            for key in self.key:
                options.extend(['-i', str(key)])
        if self.password:
            options.extend(['-oPasswordAuthentication=yes'])

        # Use the shared master connection
        options.append(f'-S{self._ssh_socket()}')

        options.extend([f'-o{option}' for option in self.ssh_option])

        return Command(*options)

    def _ssh_master_connection(self, command: Command) -> None:
        """ Check/create the master ssh connection """
        if self._ssh_master_process:
            return

        # Do not modify the original command...
        ssh_master_command = command + self._ssh_options() + Command("-MNnT", self._ssh_guest())
        self.debug(f"Create the master ssh connection: {ssh_master_command}")
        self._ssh_master_process = subprocess.Popen(
            ssh_master_command.to_popen(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL)

    def _ssh_command(self) -> Command:
        """ Prepare an ssh command line for execution """
        command = Command(
            *(["sshpass", "-p", self.password] if self.password else []),
            "ssh"
            )

        # Check the master connection
        self._ssh_master_connection(command)

        return command + self._ssh_options()

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

        ansible_command = Command('ansible-playbook', *self._ansible_verbosity())

        if extra_args:
            ansible_command += self._ansible_extra_args(extra_args)

        ansible_command += Command(
            '--ssh-common-args', self._ssh_options().to_element(),
            '-i', f'{self._ssh_guest()},',
            str(playbook))

        # FIXME: cast() - https://github.com/teemtee/tmt/issues/1372
        parent = cast(Provision, self.parent)

        return self._run_guest_command(
            ansible_command,
            friendly_command=friendly_command,
            silent=silent,
            cwd=parent.plan.worktree,
            env=self._prepare_environment(),
            log=log)

    @property
    def is_ready(self) -> bool:
        """ Detect guest is ready or not """

        # Enough for now, ssh connection can be created later
        return self.guest is not None

    def execute(self,
                command: Union[tmt.utils.Command, tmt.utils.ShellScript],
                cwd: Optional[Path] = None,
                env: Optional[tmt.utils.EnvironmentType] = None,
                friendly_command: Optional[str] = None,
                test_session: bool = False,
                silent: bool = False,
                log: Optional[tmt.log.LoggingFunction] = None,
                interactive: bool = False,
                **kwargs: Any) -> tmt.utils.CommandOutput:
        """
        Execute a command on the guest.

        :param command: either a command or a shell script to execute.
        :param cwd: execute command in this directory on the guest.
        :param env: if set, set these environment variables before running the command.
        :param friendly_command: nice, human-friendly representation of the command.
        """

        # Abort if guest is unavailable
        if self.guest is None and not self.opt('dry'):
            raise tmt.utils.GeneralError('The guest is not available.')

        ssh_command: tmt.utils.Command = self._ssh_command()

        # Run in interactive mode if requested
        if interactive:
            ssh_command += Command('-t')

        # Force ssh to allocate pseudo-terminal if requested. Without a pseudo-terminal,
        # remote processes spawned by SSH would keep running after SSH process death, e.g.
        # in the case of a timeout.
        #
        # Note that polite request, `-t`, is not enough since `ssh` itself has no pseudo-terminal,
        # and a single `-t` wouldn't have the necessary effect.
        if test_session:
            ssh_command += Command('-tt')

        # Accumulate all necessary commands - they will form a "shell" script, a single
        # string passed to SSH to execute on the remote machine.
        remote_commands: ShellScript = ShellScript.from_scripts(
            self._export_environment(self._prepare_environment(env))
            )

        # Change to given directory on guest if cwd provided
        if cwd:
            remote_commands += ShellScript(f'cd {quote(str(cwd))}')

        if isinstance(command, Command):
            remote_commands += command.to_script()

        else:
            remote_commands += command

        remote_command = remote_commands.to_element()

        ssh_command += [
            self._ssh_guest(),
            remote_command
            ]

        self.debug(f"Execute command '{remote_command}' on guest '{self.guest}'.")

        return self._run_guest_command(
            ssh_command,
            log=log,
            friendly_command=friendly_command,
            silent=silent,
            cwd=cwd,
            interactive=interactive,
            **kwargs)

    def push(self,
             source: Optional[Path] = None,
             destination: Optional[Path] = None,
             options: Optional[List[str]] = None,
             superuser: bool = False) -> None:
        """
        Push files to the guest

        By default the whole plan workdir is synced to the same location
        on the guest. Use the 'source' and 'destination' to sync custom
        location and the 'options' parametr to modify default options
        which are '-Rrz --links --safe-links --delete'.

        Set 'superuser' if rsync command has to run as root or passwordless
        sudo on the Guest (e.g. pushing to r/o destination)
        """
        # Abort if guest is unavailable
        if self.guest is None and not self.opt('dry'):
            raise tmt.utils.GeneralError('The guest is not available.')

        # Prepare options and the push command
        options = options or DEFAULT_RSYNC_PUSH_OPTIONS
        if destination is None:
            destination = Path("/")
        if source is None:
            # FIXME: cast() - https://github.com/teemtee/tmt/issues/1372
            parent = cast(Provision, self.parent)

            assert parent.plan.workdir is not None

            source = parent.plan.workdir
            self.debug(f"Push workdir to guest '{self.guest}'.")
        else:
            self.debug(f"Copy '{source}' to '{destination}' on the guest.")

        def rsync() -> None:
            """ Run the rsync command """
            # In closure, mypy has hard times to reason about the state of used variables.
            assert options
            assert source
            assert destination

            cmd = ['rsync']
            if superuser and self.user != 'root':
                cmd += ['--rsync-path', 'sudo rsync']

            self._run_guest_command(Command(
                *cmd,
                *options,
                "-e", self._ssh_command().to_element(),
                str(source),
                f"{self._ssh_guest()}:{destination}"
                ), silent=True)

        # Try to push twice, check for rsync after the first failure
        try:
            rsync()
        except tmt.utils.RunError:
            try:
                if self._check_rsync() == CheckRsyncOutcome.ALREADY_INSTALLED:
                    raise
                rsync()
            except tmt.utils.RunError:
                # Provide a reasonable error to the user
                self.fail(
                    f"Failed to push workdir to the guest. This usually means "
                    f"that login as '{self.user}' to the guest does not work.")
                raise

    def pull(self,
             source: Optional[Path] = None,
             destination: Optional[Path] = None,
             options: Optional[List[str]] = None,
             extend_options: Optional[List[str]] = None) -> None:
        """
        Pull files from the guest

        By default the whole plan workdir is synced from the same
        location on the guest. Use the 'source' and 'destination' to
        sync custom location, the 'options' parameter to modify
        default options :py:data:`DEFAULT_RSYNC_PULL_OPTIONS`
        and 'extend_options' to extend them (e.g. by exclude).
        """
        # Abort if guest is unavailable
        if self.guest is None and not self.opt('dry'):
            raise tmt.utils.GeneralError('The guest is not available.')

        # Prepare options and the pull command
        options = options or DEFAULT_RSYNC_PULL_OPTIONS
        if extend_options is not None:
            options.extend(extend_options)
        if destination is None:
            destination = Path("/")
        if source is None:
            # FIXME: cast() - https://github.com/teemtee/tmt/issues/1372
            parent = cast(Provision, self.parent)

            assert parent.plan.workdir is not None

            source = parent.plan.workdir
            self.debug(f"Pull workdir from guest '{self.guest}'.")
        else:
            self.debug(f"Copy '{source}' from the guest to '{destination}'.")

        def rsync() -> None:
            """ Run the rsync command """
            # In closure, mypy has hard times to reason about the state of used variables.
            assert options
            assert source
            assert destination

            self._run_guest_command(Command(
                "rsync",
                *options,
                "-e", self._ssh_command().to_element(),
                f"{self._ssh_guest()}:{source}",
                str(destination)
                ), silent=True)

        # Try to pull twice, check for rsync after the first failure
        try:
            rsync()
        except tmt.utils.RunError:
            try:
                if self._check_rsync() == CheckRsyncOutcome.ALREADY_INSTALLED:
                    raise
                rsync()
            except tmt.utils.RunError:
                # Provide a reasonable error to the user
                self.fail(
                    f"Failed to pull workdir from the guest. "
                    f"This usually means that login as '{self.user}' "
                    f"to the guest does not work.")
                raise

    def stop(self) -> None:
        """
        Stop the guest

        Shut down a running guest instance so that it does not consume
        any memory or cpu resources. If needed, perform any actions
        necessary to store the instance status to disk.
        """

        # Close the master ssh connection
        if self._ssh_master_process:
            self.debug("Close the master ssh connection.", level=3)
            try:
                self._ssh_master_process.terminate()
                self._ssh_master_process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                pass

        # Remove the ssh socket
        if self._ssh_socket_path and self._ssh_socket_path.exists():
            self.debug(
                f"Remove ssh socket '{self._ssh_socket_path}'.", level=3)
            try:
                self._ssh_socket_path.unlink()
            except OSError as error:
                self.debug(f"Failed to remove the socket: {error}", level=3)

    def reboot(
            self,
            hard: bool = False,
            command: Optional[Union[Command, ShellScript]] = None,
            timeout: Optional[int] = None,
            tick: float = tmt.utils.DEFAULT_WAIT_TICK,
            tick_increase: float = tmt.utils.DEFAULT_WAIT_TICK_INCREASE) -> bool:
        """
        Reboot the guest, return True if reconnect was successful

        Parameter 'hard' set to True means that guest should be
        rebooted by way which is not clean in sense that data can be
        lost. When set to False reboot should be done gracefully.

        Use the 'command' parameter to specify a custom reboot command
        instead of the default 'reboot'.
        """

        if hard:
            raise tmt.utils.ProvisionError(
                "Method does not support hard reboot.")

        command = command or Command("reboot")
        self.debug(f"Reboot using the command '{command}'.")

        re_boot_time = re.compile(r'btime\s+(\d+)')

        def get_boot_time() -> int:
            """ Reads btime from /proc/stat """
            stdout = self.execute(Command("cat", "/proc/stat")).stdout
            assert stdout

            match = re_boot_time.search(stdout)

            if match is None:
                raise tmt.utils.ProvisionError('Failed to retrieve boot time from guest')

            return int(match.group(1))

        current_boot_time = get_boot_time()

        try:
            self.execute(command)
        except tmt.utils.RunError as error:
            # Connection can be closed by the remote host even before the
            # reboot command is completed. Let's ignore such errors.
            if error.returncode == 255:
                self.debug(
                    "Seems the connection was closed too fast, ignoring.")
            else:
                raise

        # Wait until we get new boot time, connection will drop and will be
        # unreachable for some time
        def check_boot_time() -> None:
            try:
                new_boot_time = get_boot_time()

                if new_boot_time != current_boot_time:
                    # Different boot time and we are reconnected
                    return

                # Same boot time, reboot didn't happen yet, retrying
                raise tmt.utils.WaitingIncompleteError

            except tmt.utils.RunError:
                self.debug('Failed to connect to the guest.')
                raise tmt.utils.WaitingIncompleteError

        timeout = timeout or CONNECTION_TIMEOUT

        try:
            tmt.utils.wait(
                self,
                check_boot_time,
                datetime.timedelta(seconds=timeout),
                tick=tick,
                tick_increase=tick_increase)

        except tmt.utils.WaitingTimedOutError:
            self.debug("Connection to guest failed after reboot.")
            return False

        self.debug("Connection to guest succeeded after reboot.")
        return True

    def remove(self) -> None:
        """
        Remove the guest

        Completely remove all guest instance data so that it does not
        consume any disk resources.
        """
        self.debug(f"Doing nothing to remove guest '{self.guest}'.")

    def _check_rsync(self) -> CheckRsyncOutcome:
        """
        Make sure that rsync is installed on the guest

        On read-only distros install it under the '/root/pkg' directory.
        Returns 'already installed' when rsync is already present.
        """

        # Check for rsync (nothing to do if already installed)
        self.debug("Ensure that rsync is installed on the guest.")
        try:
            self.execute(Command('rsync', '--version'))
            return CheckRsyncOutcome.ALREADY_INSTALLED
        except tmt.utils.RunError:
            pass

        # Check the package manager
        self.debug("Check the package manager.")
        try:
            self.execute(Command('dnf', '--version'))
            package_manager = "dnf"
        except tmt.utils.RunError:
            package_manager = "yum"

        # Install under '/root/pkg' for read-only distros
        # (for now the check is based on 'rpm-ostree' presence)
        # FIXME: Find a better way how to detect read-only distros
        self.debug("Check for a read-only distro.")
        try:
            self.execute(Command('rpm-ostree', '--version'))
            readonly = (
                " --installroot=/root/pkg --releasever / "
                "&& ln -sf /root/pkg/bin/rsync /usr/local/bin/rsync")
        except tmt.utils.RunError:
            readonly = ""

        # Install the rsync
        self.execute(ShellScript(f"{package_manager} install -y rsync" + readonly))

        return CheckRsyncOutcome.INSTALLED


@dataclasses.dataclass
class ProvisionStepData(tmt.steps.StepData):
    hardware: Optional[tmt.hardware.Hardware] = field(
        default=cast(Optional[tmt.hardware.Hardware], None),
        normalize=normalize_hardware,
        serialize=lambda hardware: hardware.to_spec() if hardware else None,
        unserialize=lambda serialized: tmt.hardware.Hardware.from_spec(serialized)
        if serialized is not None else None)


class ProvisionPlugin(tmt.steps.GuestlessPlugin):
    """ Common parent of provision plugins """

    _data_class = ProvisionStepData
    _guest_class = Guest

    # Default implementation for provision is a virtual machine
    how = 'virtual'

    # Methods ("how: ..." implementations) registered for the same step.
    _supported_methods: PluginRegistry[tmt.steps.Method] = PluginRegistry()

    # TODO: Generics would provide a better type, https://github.com/teemtee/tmt/issues/1437
    _guest: Optional[Guest] = None

    @classmethod
    def base_command(
            cls,
            usage: str,
            method_class: Optional[Type[click.Command]] = None) -> click.Command:
        """ Create base click command (common for all provision plugins) """

        # Prepare general usage message for the step
        if method_class:
            usage = Provision.usage(method_overview=usage)

        # Create the command
        @click.command(cls=method_class, help=usage)
        @click.pass_context
        @option(
            '-h', '--how', metavar='METHOD',
            help='Use specified method for provisioning.')
        @tmt.steps.PHASE_OPTIONS
        def provision(context: 'tmt.cli.Context', **kwargs: Any) -> None:
            context.obj.steps.add('provision')
            Provision.store_cli_invocation(context)

        return provision

    # TODO: this might be needed until https://github.com/teemtee/tmt/issues/1696 is resolved
    def opt(self, option: str, default: Optional[Any] = None) -> Any:
        """ Get an option from the command line options """

        if option == 'ssh-option':
            value = super().opt(option, default=default)

            if isinstance(value, tuple):
                return list(value)

            return value

        return super().opt(option, default=default)

    def wake(self, data: Optional[GuestData] = None) -> None:
        """
        Wake up the plugin

        Override data with command line options.
        Wake up the guest based on provided guest data.
        """
        super().wake()

        if data is not None:
            guest = self._guest_class(
                logger=self._logger,
                data=data,
                name=self.name,
                parent=self.step)
            guest.wake()
            self._guest = guest

    def guest(self) -> Optional[Guest]:
        """
        Return provisioned guest

        Each ProvisionPlugin has to implement this method.
        Should return a provisioned Guest() instance.
        """
        raise NotImplementedError

    def requires(self) -> List['tmt.base.Dependency']:
        """
        All requirements of the guest implementation.

        Provide a list of requirements for the workdir sync.

        By default, plugin's guest class, :py:attr:`ProvisionPlugin._guest_class`,
        is asked to provide the list of required packages via
        :py:meth:`Guest.requires` method.

        :returns: a list of requirements.
        """

        return self._guest_class.requires()

    @classmethod
    def options(cls, how: Optional[str] = None) -> List[tmt.options.ClickOptionDecoratorType]:
        """ Return list of options. """
        return super().options(how) + cls._guest_class.options(how)

    @classmethod
    def clean_images(cls, clean: 'tmt.base.Clean', dry: bool) -> bool:
        """ Remove the images of one particular plugin """
        return True

    def show(self, keys: Optional[List[str]] = None) -> None:
        keys = keys or list(set(self.data.keys()))

        show_hardware = 'hardware' in keys

        if show_hardware:
            keys.remove('hardware')

        super().show(keys=keys)

        if show_hardware:
            hardware: Optional[tmt.hardware.Hardware] = self.get('hardware')

            if hardware:
                echo(tmt.utils.format('hardware', tmt.utils.dict_to_yaml(hardware.to_spec())))


class Provision(tmt.steps.Step):
    """ Provision an environment for testing or use localhost. """

    # Default implementation for provision is a virtual machine
    DEFAULT_HOW = 'virtual'

    _plugin_base_class = ProvisionPlugin

    _preserved_workdir_members = ['step.yaml', 'guests.yaml']

    def __init__(
            self,
            *,
            plan: 'tmt.Plan',
            data: tmt.steps.RawStepDataArgument,
            logger: tmt.log.Logger) -> None:
        """ Initialize provision step data """
        super().__init__(plan=plan, data=data, logger=logger)

        # List of provisioned guests and loaded guest data
        self._guests: List[Guest] = []
        self._guest_data: Dict[str, GuestData] = {}
        self.is_multihost = False

    def load(self) -> None:
        """ Load guest data from the workdir """
        super().load()
        try:
            raw_guest_data = tmt.utils.yaml_to_dict(self.read(Path('guests.yaml')))

            self._guest_data = {
                name: tmt.utils.SerializableContainer.unserialize(guest_data, self._logger)
                for name, guest_data in raw_guest_data.items()
                }

        except tmt.utils.FileError:
            self.debug('Provisioned guests not found.', level=2)

    def save(self) -> None:
        """ Save guest data to the workdir """
        super().save()
        try:
            raw_guest_data = {guest.name: guest.save().to_serialized()
                              for guest in self.guests()}

            self.write(Path('guests.yaml'), tmt.utils.dict_to_yaml(raw_guest_data))
        except tmt.utils.FileError:
            self.debug('Failed to save provisioned guests.')

    def wake(self) -> None:
        """ Wake up the step (process workdir and command line) """
        super().wake()

        # Choose the right plugin and wake it up
        for data in self.data:
            # FIXME: cast() - see https://github.com/teemtee/tmt/issues/1599
            plugin = cast(ProvisionPlugin, ProvisionPlugin.delegate(self, data=data))
            self._phases.append(plugin)
            # If guest data loaded, perform a complete wake up
            plugin.wake(data=self._guest_data.get(plugin.name))

            guest = plugin.guest()
            if guest:
                self._guests.append(guest)

        # Nothing more to do if already done
        if self.status() == 'done':
            self.debug(
                'Provision wake up complete (already done before).', level=2)
        # Save status and step data (now we know what to do)
        else:
            self.status('todo')
            self.save()

    def summary(self) -> None:
        """ Give a concise summary of the provisioning """
        # Summary of provisioned guests
        guests = fmf.utils.listed(self.guests(), 'guest')
        self.info('summary', f'{guests} provisioned', 'green', shift=1)
        # Guest list in verbose mode
        for guest in self.guests():
            if not guest.name.startswith(tmt.utils.DEFAULT_NAME):
                self.verbose(guest.name, color='red', shift=2)

    def go(self) -> None:
        """ Provision all guests"""
        super().go()

        # Nothing more to do if already done
        if self.status() == 'done':
            self.info('status', 'done', 'green', shift=1)
            self.summary()
            self.actions()
            return

        # Provision guests
        self._guests = []
        save = True
        self.is_multihost = sum(isinstance(phase, ProvisionPlugin) for phase in self.phases()) > 1
        try:
            for phase in self.phases(classes=(Action, ProvisionPlugin)):
                try:
                    if isinstance(phase, Action):
                        phase.go()

                    elif isinstance(phase, ProvisionPlugin):
                        phase.go()

                        guest = phase.guest()
                        if guest:
                            guest.details()

                    if self.is_multihost:
                        self.info('')
                except (tmt.utils.RunError, tmt.utils.ProvisionError) as error:
                    self.fail(str(error))
                    raise
                finally:
                    if isinstance(phase, ProvisionPlugin):
                        guest = phase.guest()
                        if guest and (guest.is_ready or self.opt('dry')):
                            self._guests.append(guest)

            # Give a summary, update status and save
            self.summary()
            self.status('done')
        except (SystemExit, tmt.utils.SpecificationError) as error:
            # A plugin will only raise SystemExit if the exit is really desired
            # and no other actions should be done. An example of this is
            # listing available images. In such case, the workdir is deleted
            # as it's redundant and save() would throw an error.
            save = False
            raise error
        finally:
            if save:
                self.save()

    def guests(self) -> List[Guest]:
        """ Return the list of all provisioned guests """
        return self._guests
