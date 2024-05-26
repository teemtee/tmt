import dataclasses
from typing import Any, Optional, Union

import tmt
import tmt.steps
import tmt.steps.provision
import tmt.utils
from tmt.utils import Command, ShellScript, field

DEFAULT_USER = "root"


@dataclasses.dataclass
class ConnectGuestData(tmt.steps.provision.GuestSshData):
    # Connect plugin actually allows `guest` key to be controlled by an option.
    _OPTIONLESS_FIELDS = tuple(
        key for key in tmt.steps.provision.GuestSshData._OPTIONLESS_FIELDS
        if key != 'guest'
        )

    # Override parent class with our defaults
    guest: Optional[str] = field(
        default=None,
        option=('-g', '--guest'),
        metavar='GUEST',
        help='Select remote host to connect to (hostname or ip).'
        )

    user: str = field(
        default=DEFAULT_USER,
        option=('-u', '--user'),
        metavar='USERNAME',
        help='Username to use for all guest operations.')

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
        unserialize=lambda serialized: None if serialized is None else ShellScript(serialized)
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
        unserialize=lambda serialized: None if serialized is None else ShellScript(serialized)
        )

    @classmethod
    def from_plugin(
            cls: type['ConnectGuestData'],
            container: 'ProvisionConnect') -> 'ConnectGuestData':  # type: ignore[override]

        options: dict[str, Any] = {
            key: container.get(option)
            # SIM118: Use `{key} in {dict}` instead of `{key} in {dict}.keys()`.
            # "Type[ArtemisGuestData]" has no attribute "__iter__" (not iterable)
            for key, option in cls.options()
            }

        options['primary_address'] = options['topology_address'] = options.pop('guest')

        return ConnectGuestData(**options)


@dataclasses.dataclass
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
            timeout: Optional[int] = None,
            tick: float = tmt.utils.DEFAULT_WAIT_TICK,
            tick_increase: float = tmt.utils.DEFAULT_WAIT_TICK_INCREASE) -> bool:
        """
        Reboot the guest, and wait for the guest to recover.

        :param hard: if set, force the reboot. This may result in a loss of
            data. The default of ``False`` will attempt a graceful reboot.
        :param command: a command to run on the guest to trigger the reboot.
            If not set, plugin would try to use
            :py:attr:`ConnectGuestData.soft_reboot` or
            :py:attr:`ConnectGuestData.hard_reboot` (``--soft-reboot`` and
            ``--hard-reboot``, respectively), if specified. Unlike ``command``,
            these would be executed on the runner, **not** on the guest.
        :param timeout: amount of time in which the guest must become available
            again.
        :param tick: how many seconds to wait between two consecutive attempts
            of contacting the guest.
        :param tick_increase: a multiplier applied to ``tick`` after every
            attempt.
        :returns: ``True`` if the reboot succeeded, ``False`` otherwise.
        """

        if not command:
            if hard and self.hard_reboot is not None:
                self.debug(f"Reboot using the hard reboot command '{self.hard_reboot}'.")

                # ignore[union-attr]: mypy still considers `self.hard_reboot` as possibly
                # being `None`, missing the explicit check above.
                return self.perform_reboot(
                    lambda: self._run_guest_command(
                        self.hard_reboot.to_shell_command()),  # type: ignore[union-attr]
                    timeout=timeout,
                    tick=tick,
                    tick_increase=tick_increase,
                    hard=True)

            if not hard and self.soft_reboot is not None:
                self.debug(f"Reboot using the soft reboot command '{self.soft_reboot}'.")

                # ignore[union-attr]: mypy still considers `self.soft_reboot` as possibly
                # being `None`, missing the explicit check above.
                return self.perform_reboot(
                    lambda: self._run_guest_command(
                        self.soft_reboot.to_shell_command()),  # type: ignore[union-attr]
                    timeout=timeout,
                    tick=tick,
                    tick_increase=tick_increase)

        return super().reboot(
            hard=hard,
            command=command,
            timeout=timeout,
            tick=tick,
            tick_increase=tick_increase)

    def start(self) -> None:
        """ Start the guest """

        self.debug(f"Doing nothing to start guest '{self.primary_address}'.")

        self.verbose('primary address', self.primary_address, 'green')
        self.verbose('topology address', self.topology_address, 'green')


@tmt.steps.provides_method('connect')
class ProvisionConnect(tmt.steps.provision.ProvisionPlugin[ProvisionConnectData]):
    """
    Connect to a provisioned guest using SSH.

    Private key authentication:

    .. code-block:: yaml

        provision:
            how: connect
            guest: host.example.org
            user: root
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
    """

    _data_class = ProvisionConnectData
    _guest_class = GuestConnect

    _thread_safe = True

    # Guest instance
    _guest = None

    def go(self, *, logger: Optional[tmt.log.Logger] = None) -> None:
        """ Prepare the connection """
        super().go(logger=logger)

        # Check guest and auth info
        if not self.data.guest:
            raise tmt.utils.SpecificationError(
                'Provide a host name or an ip address to connect.')

        if (self.data.soft_reboot or self.data.hard_reboot) and not self.is_feeling_safe:
            raise tmt.utils.GeneralError(
                "Custom soft and hard reboot commands are allowed "
                "only with the '--feeling-safe' option.")

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
            logger=self._logger,
            data=data,
            name=self.name,
            parent=self.step)
        self._guest.setup()

    def guest(self) -> Optional[tmt.GuestSsh]:
        """ Return the provisioned guest """
        return self._guest
