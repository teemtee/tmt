import dataclasses
from typing import List, Optional

import click

import tmt
import tmt.steps
import tmt.steps.provision
import tmt.utils
from tmt.steps.provision import GuestSshData

DEFAULT_USER = "root"


@dataclasses.dataclass
class ConnectGuestData(tmt.steps.provision.GuestSshData):
    user: str = DEFAULT_USER


@dataclasses.dataclass
class ProvisionConnectData(ConnectGuestData, tmt.steps.StepData):
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

    # Guest instance
    _guest = None

    @classmethod
    def options(cls, how: Optional[str] = None) -> List[tmt.options.ClickOptionDecoratorType]:
        """ Prepare command line options for connect """
        options = super().options(how)
        options[:0] = [
            click.option(
                '-g', '--guest', metavar='GUEST',
                help='Select remote host to connect to (hostname or ip).'),
            click.option(
                '-P', '--port', metavar='PORT',
                help='Use specific port to connect to.'),
            click.option(
                '-k', '--key', metavar='PRIVATE_KEY',
                help='Private key for login into the guest system.'),
            click.option(
                '-u', '--user', metavar='USER',
                help='Username to use for all guest operations.'),
            click.option(
                '-p', '--password', metavar='PASSWORD',
                help='Password for login into the guest system.'),
            ]
        return options

    def wake(self, data: Optional[GuestSshData] = None) -> None:  # type: ignore[override]
        """ Wake up the plugin, process data, apply options """
        super().wake(data=data)
        if data:
            self._guest = tmt.GuestSsh(data, name=self.name, parent=self.step)

    def go(self) -> None:
        """ Prepare the connection """
        super().go()

        # Check connection details
        guest = self.get('guest')
        user = self.get('user')
        key = self.get('key')
        password = self.get('password')
        port = self.get('port')

        # Check guest and auth info
        if not guest:
            raise tmt.utils.SpecificationError(
                'Provide a host name or an ip address to connect.')
        data = ConnectGuestData(
            role=self.get('role'),
            guest=guest,
            user=user
            )
        self.info('guest', guest, 'green')
        self.info('user', user, 'green')
        if port:
            self.info('port', port, 'green')
            data.port = port

        # Use provided password for authentication
        if password:
            self.info('password', password, 'green')
            self.debug('Using password authentication.')
            data.password = password
        # Default to using a private key (user can have configured one)
        else:
            self.info('key', key or 'not provided', 'green')
            self.debug('Using private key authentication.')
            # TODO: something to fix in the future, multiple --key options would help.
            # Right now, the default value is List[str], while the option is just str.
            if isinstance(key, list):
                data.key = key
            else:
                data.key = [key]

        # And finally create the guest
        self._guest = tmt.GuestSsh(data, name=self.name, parent=self.step)

    def guest(self) -> Optional[tmt.GuestSsh]:
        """ Return the provisioned guest """
        return self._guest
