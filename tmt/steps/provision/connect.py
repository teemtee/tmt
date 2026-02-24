from typing import Any, Optional, Union

import tmt
import tmt.guest
import tmt.steps
import tmt.steps.provision
import tmt.utils
from tmt.container import container, field
from tmt.guest import RebootMode
from tmt.utils import Command, ShellScript
from tmt.utils.wait import Waiting


@container
class ConnectGuestData(tmt.guest.GuestSshData):
    # Connect plugin actually allows `guest` key to be controlled by an option.
    _OPTIONLESS_FIELDS = tuple(
        key for key in tmt.guest.GuestSshData._OPTIONLESS_FIELDS if key != 'guest'
    )

    # Override parent class with our defaults
    guest: Optional[str] = field(
        default=None,
        option=('-g', '--guest'),
        metavar='HOSTNAME|IP',
        help='A preexisting machine to connect to.',
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
    systemd_soft_reboot: Optional[ShellScript] = field(
        default=None,
        option='--systemd-soft-reboot',
        metavar='COMMAND',
        help="""
             If specified, the command, executed on the runner, would be used
             for systemd soft-reboot of the guest.
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


class GuestConnect(tmt.guest.GuestSsh):
    _data_class = ConnectGuestData

    soft_reboot: Optional[ShellScript]
    systemd_soft_reboot: Optional[ShellScript]
    hard_reboot: Optional[ShellScript]

    def reboot(
        self,
        mode: RebootMode = RebootMode.SOFT,
        command: Optional[Union[Command, ShellScript]] = None,
        waiting: Optional[Waiting] = None,
    ) -> bool:
        """
        Reboot the guest, and wait for the guest to recover.

        Plugin will use special commands if specified via ``soft-reboot``,
        ``systemd-soft-reboot``, and ``hard-reboot`` keys to perform the
        :py:attr:`RebootMode.SOFT`, :py:attr:`RebootMode.SYSTEMD_SOFT`,
        and :py:attr:`RebootMode.HARD` reboot modes, respectively.

        .. warning::

            Unlike ``command``, these commands would be executed on
            the runner, **not** on the guest.

        :param mode: which boot mode to perform.
        :param command: a command to run on the guest to trigger the
            reboot. Only usable when mode is not
            :py:attr:`RebootMode.HARD`.
        :param waiting: deadline for the reboot.
        :returns: ``True`` if the reboot succeeded, ``False`` otherwise.
        """

        waiting = waiting or tmt.guest.default_reboot_waiting()

        if mode == RebootMode.HARD:
            if self.hard_reboot is None:
                raise tmt.guest.RebootModeNotSupportedError(guest=self, mode=mode)

            self.debug(f"Hard reboot using the hard reboot command '{self.hard_reboot}'.")

            # ignore[union-attr]: mypy still considers `self.hard_reboot` as possibly
            # being `None`, missing the explicit check above.
            return self.perform_reboot(
                mode,
                lambda: self._run_guest_command(self.hard_reboot.to_shell_command()),  # type: ignore[union-attr]
                waiting,
            )

        if command is not None:
            return super().reboot(
                mode=mode,
                command=command,
                waiting=waiting,
            )

        if mode == RebootMode.SOFT and self.soft_reboot is not None:
            self.debug(f"Soft reboot using the soft reboot command '{self.soft_reboot}'.")

            # ignore[union-attr]: mypy still considers `self.soft_reboot` as possibly
            # being `None`, missing the explicit check above.
            return self.perform_reboot(
                mode,
                lambda: self._run_guest_command(self.soft_reboot.to_shell_command()),  # type: ignore[union-attr]
                waiting,
            )

        if mode == RebootMode.SYSTEMD_SOFT and self.systemd_soft_reboot is not None:
            self.debug(
                "Systemd soft-reboot using the systemd"
                f" soft-reboot command '{self.systemd_soft_reboot}'."
            )

            # ignore[union-attr]: mypy still considers `self.systemd_soft_reboot` as possibly
            # being `None`, missing the explicit check above.
            return self.perform_reboot(
                mode,
                lambda: self._run_guest_command(self.systemd_soft_reboot.to_shell_command()),  # type: ignore[union-attr]
                waiting,
            )

        return super().reboot(mode=mode, waiting=waiting)

    def start(self) -> None:
        """
        Start the guest
        """

        self.debug(f"Doing nothing to start guest '{self.primary_address}'.")

        self.verbose('primary address', self.primary_address, 'green')
        self.verbose('topology address', self.topology_address, 'green')

        self.assert_reachable()


@tmt.steps.provides_method('connect')
class ProvisionConnect(tmt.steps.provision.ProvisionPlugin[ProvisionConnectData]):
    #
    # This plugin docstring has been reviewed and updated to follow
    # our documentation best practices. When changing it, please make
    # sure new changes are following them as well.
    #
    # https://tmt.readthedocs.io/en/stable/contribute.html#docs
    #
    """
    Connect to a provisioned guest using SSH.

    Do not provision any system, tests will be executed directly on the
    machine that has been already provisioned. Use provided
    authentication information to connect to it over SSH.



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

    To support hard reboot of a guest, ``hard-reboot`` must be set to
    an executable command or script. Without this key set, hard reboot
    will remain unsupported and result in an error. In comparison,
    ``soft-reboot`` and ``systemd-soft-reboot`` are optional, but if set,
    the given commands will be preferred over the default soft and systemd
    soft-reboot commands:

    .. code-block:: yaml

        provision:
          how: connect
          hard-reboot: virsh reboot my-example-vm
          systemd-soft-reboot: ssh root@my-example-vm 'systemd soft-reboot'
          soft-reboot: ssh root@my-example-vm 'shutdown -r now'

    .. code-block:: shell

        provision --how connect \\
                  --hard-reboot="virsh reboot my-example-vm" \\
                  --systemd-soft-reboot="ssh root@my-example-vm 'systemd soft-reboot'"
                  --soft-reboot="ssh root@my-example-vm 'shutdown -r now'"

    .. warning::

        ``hard-reboot``, ``systemd-soft-reboot``, and ``soft-reboot``
        commands are executed on the runner, not on the guest.
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

        if (
            any((self.data.soft_reboot, self.data.systemd_soft_reboot, self.data.hard_reboot))
            and not self.is_feeling_safe
        ):
            raise tmt.utils.GeneralError(
                "Custom soft, systemd soft, and hard reboot commands are allowed "
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
        self._guest.start()
        self._guest.setup()
