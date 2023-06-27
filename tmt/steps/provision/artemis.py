import dataclasses
import datetime
import sys
from typing import Any, Dict, Optional, cast

import requests

import tmt
import tmt.log
import tmt.options
import tmt.steps
import tmt.steps.provision
import tmt.utils
from tmt.utils import ProvisionError, field, retry_session, updatable_message

if sys.version_info >= (3, 8):
    from typing import TypedDict
else:
    from typing_extensions import TypedDict


# List of Artemis API versions supported and understood by this plugin.
# Since API gains support for new features over time, it is important to
# know when particular feature became available, and avoid using it with
# older APIs.
SUPPORTED_API_VERSIONS = (
    # NEW: fixed virtualization.hypervisor enum
    '0.0.58',
    # NEW: added user defined watchdog delay
    '0.0.56',
    # NEW: no change, fixes issues with validation
    '0.0.55',
    # NEW: added Kickstart specification
    '0.0.53',
    # NEW: added compatible HW constraint
    '0.0.48',
    # NEW: added missing cpu.processors constraint
    '0.0.47',
    # NEW: added new CPU constraints
    '0.0.46',
    # NEW: added hostname HW constraint
    '0.0.38',
    # NEW: virtualization HW constraint
    '0.0.37',
    # NEW: boot.method HW constraint
    '0.0.32',
    # NEW: network HW constraint
    '0.0.28'
    )


# The default Artemis API version - the most recent supported versions
# should be perfectly fine.
DEFAULT_API_VERSION = SUPPORTED_API_VERSIONS[0]

DEFAULT_API_URL = 'http://127.0.0.1:8001'
DEFAULT_USER = 'root'
DEFAULT_ARCH = 'x86_64'
DEFAULT_PRIORITY_GROUP = 'default-priority'
DEFAULT_KEYNAME = 'default'
DEFAULT_PROVISION_TIMEOUT = 600
DEFAULT_PROVISION_TICK = 60
DEFAULT_API_TIMEOUT = 10
DEFAULT_API_RETRIES = 10
# Should lead to delays of 0.5, 1, 2, 4, 8, 16, 32, 64, 128, 256 seconds
DEFAULT_RETRY_BACKOFF_FACTOR = 1


def _normalize_user_data(
        key_address: str,
        raw_value: Any,
        logger: tmt.log.Logger) -> Dict[str, str]:
    if isinstance(raw_value, dict):
        return {
            str(key).strip(): str(value).strip() for key, value in raw_value.items()
            }

    if isinstance(raw_value, (list, tuple)):
        user_data = {}

        for datum in raw_value:
            try:
                key, value = datum.split('=', 1)

            except ValueError as exc:
                raise tmt.utils.NormalizationError(
                    key_address, datum, 'a KEY=VALUE string') from exc

            user_data[key.strip()] = value.strip()

        return user_data

    raise tmt.utils.NormalizationError(
        key_address, value, 'a dictionary or a list of KEY=VALUE strings')


@dataclasses.dataclass
class ArtemisGuestData(tmt.steps.provision.GuestSshData):
    # Override parent class with our defaults
    user: str = DEFAULT_USER

    # API
    api_url: str = field(
        default=DEFAULT_API_URL,
        option='--api-url',
        metavar='URL',
        help="Artemis API URL.")
    api_version: str = field(
        default=DEFAULT_API_VERSION,
        option='--api-version',
        metavar='X.Y.Z',
        help="Artemis API version to use.",
        choices=SUPPORTED_API_VERSIONS)

    # Guest request properties
    arch: str = field(
        default=DEFAULT_ARCH,
        option='--arch',
        metavar='ARCH',
        help='Architecture to provision.')
    image: Optional[str] = field(
        default=None,
        option='--image',
        metavar='COMPOSE',
        help='Image (or "compose" in Artemis terminology) to provision.')
    hardware: Optional[Any] = None
    pool: Optional[str] = field(
        default=None,
        option='--pool',
        metavar='NAME',
        help='Pool to enforce.')
    priority_group: str = field(
        default=DEFAULT_PRIORITY_GROUP,
        option='--priority-group',
        metavar='NAME',
        help='Provisioning priority group.')
    keyname: str = field(
        default=DEFAULT_KEYNAME,
        option='--keyname',
        metavar='NAME',
        help='SSH key name.')
    user_data: Dict[str, str] = field(
        default_factory=dict,
        option='--user-data',
        metavar='KEY=VALUE',
        help='Optional data to attach to guest.',
        multiple=True,
        normalize=_normalize_user_data)
    kickstart: Dict[str, str] = field(
        default_factory=dict,
        option='--kickstart',
        metavar='KEY=VALUE',
        help='Optional Beaker kickstart to use when provisioning the guest.',
        multiple=True,
        normalize=_normalize_user_data)

    # Provided by Artemis response
    guestname: Optional[str] = None

    # Timeouts and deadlines
    provision_timeout: int = field(
        default=DEFAULT_PROVISION_TIMEOUT,
        option='--provision-timeout',
        metavar='SECONDS',
        help='How long to wait for provisioning to complete, '
        f'{DEFAULT_PROVISION_TIMEOUT} seconds by default.',
        normalize=tmt.utils.normalize_int)
    provision_tick: int = field(
        default=DEFAULT_PROVISION_TICK,
        option='--provision-tick',
        metavar='SECONDS',
        help=f'How often check Artemis API for provisioning status, '
        f'{DEFAULT_PROVISION_TICK} seconds by default.',
        normalize=tmt.utils.normalize_int)
    api_timeout: int = field(
        default=DEFAULT_API_TIMEOUT,
        option='--api-timeout',
        metavar='SECONDS',
        help=f'How long to wait for API operations to complete, '
        f'{DEFAULT_API_TIMEOUT} seconds by default.',
        normalize=tmt.utils.normalize_int)
    api_retries: int = field(
        default=DEFAULT_API_RETRIES,
        option='--api-retries',
        metavar='COUNT',
        help=f'How many attempts to use when talking to API, '
        f'{DEFAULT_API_RETRIES} by default.',
        normalize=tmt.utils.normalize_int)
    api_retry_backoff_factor: int = field(
        default=DEFAULT_RETRY_BACKOFF_FACTOR,
        option='--api-retry-backoff-factor',
        metavar='COUNT',
        help=f'A factor for exponential API retry backoff, '
        f'{DEFAULT_RETRY_BACKOFF_FACTOR} by default.',
        normalize=tmt.utils.normalize_int)
    # Artemis core already contains default values
    watchdog_dispatch_delay: Optional[int] = field(
        default=cast(Optional[int], None),
        option='--watchdog-dispatch-delay',
        metavar='SECONDS',
        help='How long (seconds) before the guest "is-alive" watchdog is dispatched. '
        'The dispatch timer starts once the guest is successfully provisioned.',
        normalize=tmt.utils.normalize_optional_int)
    watchdog_period_delay: Optional[int] = field(
        default=cast(Optional[int], None),
        option='--watchdog-period-delay',
        metavar='SECONDS',
        help='How often (seconds) check that the guest "is-alive".',
        normalize=tmt.utils.normalize_optional_int)


@dataclasses.dataclass
class ProvisionArtemisData(ArtemisGuestData, tmt.steps.provision.ProvisionStepData):
    pass


GUEST_STATE_COLOR_DEFAULT = 'green'

GUEST_STATE_COLORS = {
    'routing': 'yellow',
    'provisioning': 'magenta',
    'promised': 'blue',
    'preparing': 'cyan',
    'cancelled': 'red',
    'error': 'red'
    }


# Type annotation for Artemis API `GET /guests/$guestname` response.
# Partial, not all fields necessary since plugin ignores most of them.
class GuestInspectType(TypedDict):
    state: str
    address: Optional[str]


class ArtemisAPI:
    def __init__(self, guest: 'GuestArtemis') -> None:
        self._guest = guest

        self.http_session = retry_session.create(
            retries=guest.api_retries,
            backoff_factor=guest.api_retry_backoff_factor,
            allowed_methods=('HEAD', 'GET', 'POST', 'DELETE', 'PUT'),
            status_forcelist=(
                429,  # Too Many Requests
                500,  # Internal Server Error
                502,  # Bad Gateway
                503,  # Service Unavailable
                504   # Gateway Timeout
                ),
            timeout=guest.api_timeout
            )

    def query(
            self,
            path: str,
            method: str = 'get',
            request_kwargs: Optional[Dict[str, Any]] = None
            ) -> requests.Response:
        """
        Base helper for Artemis API queries.

        Trivial dispatcher per method, returning retrieved response.

        :param path: API path to contact.
        :param method: HTTP method to use.
        :param request_kwargs: optional request options, as supported by
            :py:mod:`requests` library.
        """

        request_kwargs = request_kwargs or {}

        url = f'{self._guest.api_url}{path}'

        if method == 'get':
            return self.http_session.get(url, **request_kwargs)

        if method == 'post':
            return self.http_session.post(url, **request_kwargs)

        if method == 'delete':
            return self.http_session.delete(url, **request_kwargs)

        if method == 'put':
            return self.http_session.put(url, **request_kwargs)

        raise tmt.utils.GeneralError(
            f'Unsupported Artemis API method.\n{method}')

    def create(
            self,
            path: str,
            data: Dict[str, Any],
            request_kwargs: Optional[Dict[str, Any]] = None
            ) -> requests.Response:
        """
        Create - or request creation of - a resource.

        :param path: API path to contact.
        :param data: optional key/value data to send with the request.
        :param request_kwargs: optional request options, as supported by
            :py:mod:`requests` library.
        """

        request_kwargs = request_kwargs or {}
        request_kwargs['json'] = data

        return self.query(path, method='post', request_kwargs=request_kwargs)

    def inspect(
            self,
            path: str,
            params: Optional[Dict[str, Any]] = None,
            request_kwargs: Optional[Dict[str, Any]] = None
            ) -> requests.Response:
        """
        Inspect a resource.

        :param path: API path to contact.
        :param params: optional key/value query parameters.
        :param request_kwargs: optional request options, as supported by
            :py:mod:`requests` library.
        """

        request_kwargs = request_kwargs or {}

        if params:
            request_kwargs['params'] = params

        return self.query(path, request_kwargs=request_kwargs)

    def delete(
            self,
            path: str,
            request_kwargs: Optional[Dict[str, Any]] = None
            ) -> requests.Response:
        """
        Delete - or request removal of - a resource.

        :param path: API path to contact.
        :param request_kwargs: optional request options, as supported by
            :py:mod:`requests` library.
        """

        return self.query(path, method='delete', request_kwargs=request_kwargs)


class GuestArtemis(tmt.GuestSsh):
    """
    Artemis guest instance

    The following keys are expected in the 'data' dictionary:
    """

    _data_class = ArtemisGuestData

    # API
    api_url: str
    api_version: str

    # Guest request properties
    arch: str
    image: str
    hardware: Optional[Any]
    pool: Optional[str]
    priority_group: str
    keyname: str
    user_data: Dict[str, str]
    kickstart: Dict[str, str]

    # Provided by Artemis response
    guestname: Optional[str]

    # Timeouts and deadlines
    provision_timeout: int
    provision_tick: int
    api_timeout: int
    api_retries: int
    api_retry_backoff_factor: int
    watchdog_dispatch_delay: Optional[int]
    watchdog_period_delay: Optional[int]

    _api: Optional[ArtemisAPI] = None

    @property
    def api(self) -> ArtemisAPI:
        if self._api is None:
            self._api = ArtemisAPI(self)

        return self._api

    @property
    def is_ready(self) -> bool:
        """ Detect the guest is ready or not """

        # FIXME: A more robust solution should be provided. Currently just
        #        return True if self.guest is not None
        return self.guest is not None

    def _create(self) -> None:
        environment: Dict[str, Any] = {
            'hw': {
                'arch': self.arch
                },
            'os': {
                'compose': self.image
                }
            }

        if self.api_version >= "0.0.53":
            environment['kickstart'] = self.kickstart

        elif self.kickstart:
            raise ProvisionError(f"API version '{self.api_version}' does not support kickstart.")

        data: Dict[str, Any] = {
            'environment': environment,
            'keyname': self.keyname,
            'priority_group': self.priority_group,
            'user_data': self.user_data
            }

        if self.pool:
            environment['pool'] = self.pool

        if self.hardware is not None:
            assert isinstance(self.hardware, dict)

            environment['hw']['constraints'] = self.hardware

        if self.api_version >= "0.0.56":
            if self.watchdog_dispatch_delay:
                data['watchdog_dispatch_delay'] = self.watchdog_dispatch_delay
            if self.watchdog_period_delay:
                data['watchdog_period_delay'] = self.watchdog_period_delay

        elif any([self.watchdog_dispatch_delay, self.watchdog_period_delay]):
            raise ProvisionError(
                f"API version '{self.api_version}' does not support watchdog specification.")

        # TODO: snapshots
        # TODO: spot instance
        # TODO: post-install script
        # TODO: log types

        response = self.api.create('/guests/', data)

        if response.status_code == 201:
            self.info('guest', 'has been requested', 'green')

        else:
            raise ProvisionError(
                f"Failed to create, "
                f"unhandled API response '{response.status_code}'.")

        self.guestname = response.json()['guestname']
        self.info('guestname', self.guestname, 'green')

        with updatable_message(
                'state', indent_level=self._level()) as progress_message:

            def get_new_state() -> GuestInspectType:
                response = self.api.inspect(f'/guests/{self.guestname}')

                if response.status_code != 200:
                    raise ProvisionError(
                        f"Failed to create, "
                        f"unhandled API response '{response.status_code}'.")

                current = cast(GuestInspectType, response.json())
                state = current['state']
                state_color = GUEST_STATE_COLORS.get(
                    state, GUEST_STATE_COLOR_DEFAULT)

                progress_message.update(state, color=state_color)

                if state == 'error':
                    raise ProvisionError(
                        'Failed to create, provisioning failed.')

                if state == 'ready':
                    return current

                raise tmt.utils.WaitingIncompleteError

            try:
                guest_info = tmt.utils.wait(
                    self, get_new_state, datetime.timedelta(
                        seconds=self.provision_timeout), tick=self.provision_tick)

            except tmt.utils.WaitingTimedOutError:
                # The provisioning chain has been already started, make sure we
                # remove the guest.
                self.remove()

                raise ProvisionError(
                    f'Failed to provision in the given amount '
                    f'of time (--provision-timeout={self.provision_timeout}).')

        self.guest = guest_info['address']
        self.info('address', self.guest, 'green')

    def start(self) -> None:
        """
        Start the guest

        Get a new guest instance running. This should include preparing
        any configuration necessary to get it started. Called after
        load() is completed so all guest data should be available.
        """

        if self.guestname is None or self.guest is None:
            self._create()

    def remove(self) -> None:
        """ Remove the guest """

        if self.guestname is None:
            return

        response = self.api.delete(f'/guests/{self.guestname}')

        if response.status_code == 404:
            self.info('guest', 'no longer exists', 'red')

        elif response.status_code == 409:
            self.info('guest', 'has existing snapshots', 'red')

        elif response.ok:
            self.info('guest', 'has been removed', 'green')

        else:
            self.info(
                'guest',
                f"Failed to remove, "
                f"unhandled API response '{response.status_code}'.")


@tmt.steps.provides_method('artemis')
class ProvisionArtemis(tmt.steps.provision.ProvisionPlugin):
    """
    Provision guest using Artemis backend

    Minimal configuration could look like this:

        provision:
            how: artemis
            image: Fedora
            api-url: https://your-artemis.com/

    Note that the actual value of "image" depends on what images - or
    "composes" as Artemis calls them - supports and can deliver.

    Note that "api-url" can be also given via TMT_PLUGIN_PROVISION_ARTEMIS_API_URL
    environment variable.

    Full configuration example:

        provision:
            how: artemis

            # Artemis API
            api-url: https://your-artemis.com/
            api-version: 0.0.32

            # Mandatory environment properties
            image: Fedora

            # Optional environment properties
            arch: aarch64
            pool: optional-pool-name

            # Provisioning process control (optional)
            priority-group: custom-priority-group
            keyname: custom-SSH-key-name

            # Labels to be attached to guest request (optional)
            user-data:
                foo: bar

            # Timeouts and deadlines (optional)
            provision-timeout: 3600
            provision-tick: 10
            api-timeout: 600
            api-retries: 5
            api-retry-backoff-factor: 1
    """

    _data_class = ProvisionArtemisData
    _guest_class = GuestArtemis

    # Guest instance
    _guest = None

    def go(self) -> None:
        """ Provision the guest """
        super().go()

        api_version = self.get('api-version')

        if api_version not in SUPPORTED_API_VERSIONS:
            raise ProvisionError(f"API version '{api_version}' not supported.")

        try:
            user_data = {
                key.strip(): value.strip()
                for key, value in (
                    pair.split('=', 1)
                    for pair in self.get('user-data')
                    )
                }

        except ValueError:
            raise ProvisionError('Cannot parse user-data.')

        data = ArtemisGuestData(
            api_url=self.get('api-url'),
            api_version=api_version,
            arch=self.get('arch'),
            image=self.get('image'),
            hardware=self.get('hardware'),
            kickstart=self.get('kickstart'),
            pool=self.get('pool'),
            priority_group=self.get('priority-group'),
            keyname=self.get('keyname'),
            user_data=user_data,
            user=self.get('user'),
            provision_timeout=self.get('provision-timeout'),
            provision_tick=self.get('provision-tick'),
            api_timeout=self.get('api-timeout'),
            api_retries=self.get('api-retries'),
            api_retry_backoff_factor=self.get('api-retry-backoff-factor'),
            watchdog_dispatch_delay=self.get('watchdog-dispatch-delay'),
            watchdog_period_delay=self.get('watchdog-period-delay'),
            ssh_option=self.get('ssh-option')
            )

        data.show(verbose=self.get('verbose'), logger=self._logger)

        self._guest = GuestArtemis(
            logger=self._logger,
            data=data,
            name=self.name,
            parent=self.step)
        self._guest.start()

    def guest(self) -> Optional[GuestArtemis]:
        """ Return the provisioned guest """
        return self._guest
