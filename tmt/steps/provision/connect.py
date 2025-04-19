from typing import Any, Optional, Union

import tmt
import tmt.steps
import tmt.steps.provision
import tmt.utils
from tmt.container import container, field
from tmt.utils import Command, ShellScript
from tmt.utils.wait import Waiting

DEFAULT_USER = "root"


@container
class ConnectGuestData(tmt.steps.provision.GuestSshData):
    # Connect plugin actually allows `guest` key to be controlled by an option.
    _OPTIONLESS_FIELDS = tuple(
        key for key in tmt.steps.provision.GuestSshData._OPTIONLESS_FIELDS if key != 'guest'
    )

    # Override parent class with our defaults
    guest: Optional[str] = field(
        default=None,
        option=('-g', '--guest'),
        metavar='GUEST',
        help='Select remote host to connect to (hostname or ip).',
    )

    user: str = field(
        default=DEFAULT_USER,
        option=('-u', '--user'),
        metavar='USERNAME',
        help='Username to use for all guest operations.',
    )

    soft_reboot: Optional[ShellScript] = field(
        default=None,
        option='--soft-reboot',
        metavar='COMMAND',
        help="""
             If specified, the command, executed on the runner, would be used
             for soft reboot of the guest.
             """,
        normalize=tmt.utils.normalize_shell_script,
        serialize=lambda value: str(value) if isinstance(value, ShellScript) else None,
        unserialize=lambda serialized: None if serialized is None else ShellScript(serialized),
    )
    hard_reboot: Optional[ShellScript] = field(
        default=None,
        option='--hard-reboot',
        help="""
             If specified, the command, executed on the runner, would be used
             for hard reboot of the guest.
             """,
        metavar='COMMAND',
        normalize=tmt.utils.normalize_shell_script,
        serialize=lambda value: str(value) if isinstance(value, ShellScript) else None,
        unserialize=lambda serialized: None if serialized is None else ShellScript(serialized),
    )

    @classmethod
    def from_plugin(
        cls: type['ConnectGuestData'],
        container: 'ProvisionConnect',  # type: ignore[override]
    ) -> 'ConnectGuestData':
        options: dict[str, Any] = {
            key: container.get(option)
            # SIM118: Use `{key} in {dict}` instead of `{key} in {dict}.keys()`.
            # "Type[ArtemisGuestData]" has no attribute "__iter__" (not iterable)
            for key, option in cls.options()
        }

        options['primary_address'] = options['topology_address'] = options.pop('guest')

        return ConnectGuestData(**options)


@container
class ProvisionConnectData(ConnectGuestData, tmt.steps.provision.ProvisionStepData):
    pass


class GuestConnect(tmt.steps.provision.GuestSsh):
    _data_class = ConnectGuestData

    soft_reboot: Optional[ShellScript]
    hard_reboot: Optional[ShellScript]

    def reboot(
        self,
        hard: bool = False,
        command: Optional[Union[Command, ShellScript]] = None,
        waiting: Optional[Waiting] = None,
    ) -> bool:
        """
        Reboot the guest, and wait for the guest to recover.

        .. note::

           Custom reboot command can be used only in combination with a
           soft reboot. If both ``hard`` and ``command`` are set, a hard
           reboot will be requested, and ``command`` will be ignored.

        :param hard: if set, force the reboot. This may result in a loss of
            data. The default of ``False`` will attempt a graceful reboot.

            Plugin will use :py:attr:`ConnectGuestData.hard_reboot`,
            set via ``hard-reboot`` key. Unlike ``command``, this command
            would be executed on the runner, **not** on the guest.
        :param command: a command to run on the guest to trigger the
            reboot. If ``hard`` is also set, ``command`` is ignored.

            If not set, plugin would try to use
            :py:attr:`ConnectGuestData.soft_reboot`, set via
            ``soft-reboot`` key. Unlike ``command``,
            this command would be executed on the runner, **not** on the
            guest.
        :param timeout: amount of time in which the guest must become available
            again.
        :param tick: how many seconds to wait between two consecutive attempts
            of contacting the guest.
        :param tick_increase: a multiplier applied to ``tick`` after every
            attempt.
        :returns: ``True`` if the reboot succeeded, ``False`` otherwise.
        """

        waiting = waiting or tmt.steps.provision.default_reboot_waiting()

        if hard:
            if self.hard_reboot is None:
                raise tmt.steps.provision.RebootModeNotSupportedError(guest=self, hard=True)

            self.debug(f"Hard reboot using the hard reboot command '{self.hard_reboot}'.")

            # ignore[union-attr]: mypy still considers `self.hard_reboot` as possibly
            # being `None`, missing the explicit check above.
            return self.perform_reboot(
                lambda: self._run_guest_command(self.hard_reboot.to_shell_command()),  # type: ignore[union-attr]
                waiting,
                fetch_boot_time=False,
            )

        if command is not None:
            return super().reboot(
                hard=False,
                command=command,
                waiting=waiting,
            )

        if self.soft_reboot is not None:
            self.debug(f"Soft reboot using the soft reboot command '{self.soft_reboot}'.")

            # ignore[union-attr]: mypy still considers `self.soft_reboot` as possibly
            # being `None`, missing the explicit check above.
            return self.perform_reboot(
                lambda: self._run_guest_command(self.soft_reboot.to_shell_command()),  # type: ignore[union-attr]
                waiting,
            )

        return super().reboot(hard=False, waiting=waiting)

    def start(self) -> None:
        """
        Start the guest
        """

        self.debug(f"Doing nothing to start guest '{self.primary_address}'.")

        self.verbose('primary address', self.primary_address, 'green')
        self.verbose('topology address', self.topology_address, 'green')


@tmt.steps.provides_method('connect')
class ProvisionConnect(tmt.steps.provision.ProvisionPlugin[ProvisionConnectData]):
    """
    Connect to a provisioned guest using SSH.

    Do not provision a new system. Instead, use provided
    authentication data to connect to a running machine.

    Private key authentication (using ``sudo`` to run scripts):

    .. code-block:: yaml

        provision:
            how: connect
            guest: host.example.org
            user: fedora
            become: true
            key: /home/psss/.ssh/example_rsa

    Password authentication:

    .. code-block:: yaml

        provision:
            how: connect
            guest: host.example.org
            user: root
            password: secret

    User defaults to ``root``, so if you have private key correctly set
    the minimal configuration can look like this:

    .. code-block:: yaml

        provision:
            how: connect
            guest: host.example.org

    To trigger a hard reboot of a guest, ``hard-reboot`` must be set to
    an executable command or script. Without this key set, hard reboot
    will remain unsupported and result in an error. In comparison,
    ``soft-reboot`` is optional, it will be preferred over the default
    soft reboot command, ``reboot``:

    .. code-block:: yaml

        provision:
          how: connect
          hard-reboot: virsh reboot my-example-vm
          soft-reboot: ssh root@my-example-vm 'shutdown -r now'

    .. warning::

        Both ``hard-reboot`` and ``soft-reboot`` commands are executed
        on the runner, not on the guest.
    """

    _data_class = ProvisionConnectData
    _guest_class = GuestConnect

    _thread_safe = True

    # Guest instance
    _guest = None

    def go(self, *, logger: Optional[tmt.log.Logger] = None) -> None:
        """
        Prepare the connection
        """

        super().go(logger=logger)

        # Check guest and auth info
        if not self.data.guest:
            raise tmt.utils.SpecificationError('Provide a host name or an ip address to connect.')

        if (self.data.soft_reboot or self.data.hard_reboot) and not self.is_feeling_safe:
            raise tmt.utils.GeneralError(
                "Custom soft and hard reboot commands are allowed "
                "only with the '--feeling-safe' option."
            )

        data = ConnectGuestData.from_plugin(self)

        data.show(verbose=self.verbosity_level, logger=self._logger)

        if data.password:
            self.debug('Using password authentication.')

        else:
            self.debug('Using private key authentication.')

        if data.hardware and data.hardware.constraint:
            self.warn("The 'connect' provision plugin does not support hardware requirements.")

        # And finally create the guest
        self._guest = GuestConnect(
            logger=self._logger, data=data, name=self.name, parent=self.step
        )
        self._guest.setup()
