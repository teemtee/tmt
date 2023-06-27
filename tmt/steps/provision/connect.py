import dataclasses
from typing import Optional

import tmt
import tmt.steps
import tmt.steps.provision
import tmt.utils
from tmt.utils import field

DEFAULT_USER = "root"


@dataclasses.dataclass
class ConnectGuestData(tmt.steps.provision.GuestSshData):
    guest: Optional[str] = field(
        default=None,
        option=('-g', '--guest'),
        metavar='GUEST',
        help='Select remote host to connect to (hostname or ip).'
        )
    user: Optional[str] = field(
        default=DEFAULT_USER,
        option=('-u', '--user'),
        metavar='USERNAME',
        help='Username to use for all guest operations.'
        )


@dataclasses.dataclass
class ProvisionConnectData(ConnectGuestData, tmt.steps.provision.ProvisionStepData):
    pass


@tmt.steps.provides_method('connect')
class ProvisionConnect(tmt.steps.provision.ProvisionPlugin):
    """
    Connect to a provisioned guest using ssh

    Private key authentication:

        provision:
            how: connect
            guest: host.example.org
            user: root
            key: /home/psss/.ssh/example_rsa

    Password authentication:

        provision:
            how: connect
            guest: host.example.org
            user: root
            password: secret

    User defaults to 'root', so if you have private key correctly set
    the minimal configuration can look like this:

        provision:
            how: connect
            guest: host.example.org
    """

    _data_class = ProvisionConnectData
    _guest_class = tmt.steps.provision.GuestSsh

    # Guest instance
    _guest = None

    def go(self) -> None:
        """ Prepare the connection """
        super().go()

        # Check guest and auth info
        if not self.get('guest'):
            raise tmt.utils.SpecificationError(
                'Provide a host name or an ip address to connect.')

        data = ConnectGuestData(
            role=self.get('role'),
            guest=self.get('guest'),
            user=self.get('user'),
            port=self.get('port'),
            password=self.get('password'),
            ssh_option=self.get('ssh-option'),
            key=self.get('key')
            )

        data.show(verbose=self.get('verbose'), logger=self._logger)

        if data.password:
            self.debug('Using password authentication.')

        else:
            self.debug('Using private key authentication.')

        # And finally create the guest
        self._guest = tmt.GuestSsh(
            logger=self._logger,
            data=data,
            name=self.name,
            parent=self.step)

    def guest(self) -> Optional[tmt.GuestSsh]:
        """ Return the provisioned guest """
        return self._guest
