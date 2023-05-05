import dataclasses
import datetime
import logging
import os
import sys
from typing import Any, Dict, List, Optional, Tuple, cast

import click

import tmt
import tmt.options
import tmt.steps
import tmt.steps.provision
import tmt.utils
from tmt.utils import ProvisionError, updatable_message

if sys.version_info >= (3, 8):
    from typing import TypedDict
else:
    from typing_extensions import TypedDict

import asyncio
from functools import wraps

mrack = Any
providers = Any
ProvisioningError = Any
NotAuthenticatedError = Any
BEAKER = Any
BeakerProvider = Any
BeakerTransformer = Any
TmtBeakerTransformer = Any

DEFAULT_USER = 'root'
DEFAULT_ARCH = 'x86_64'
DEFAULT_PROVISION_TIMEOUT = 3600  # 1 hour timeout at least
DEFAULT_PROVISION_TICK = 60  # poll job each minute


# Type annotation for "data" package describing a guest instance. Passed
# between load() and save() calls
GuestInspectType = TypedDict(
    'GuestInspectType', {
        "status": str,
        "system": str,
        'address': Optional[str]
        }
    )

size_translation = {
    "TB": 1000000,
    "GB": 1000,
    "MB": 1,
    "TiB": 1048576,
    "GiB": 1024,
    "MiB": 1,
    }

operators = [
    "~=",
    ">=",
    "<=",
    ">",
    "<",
    "=",
    ]


def import_and_load_mrack_deps(workdir: Any, name: str) -> None:
    """
    Import mrack module only when needed

    Until we have a separate package for each plugin.
    """
    global mrack
    global providers
    global ProvisioningError
    global NotAuthenticatedError
    global BEAKER
    global BeakerProvider
    global BeakerTransformer
    global TmtBeakerTransformer

    try:
        import mrack
        from mrack.errors import NotAuthenticatedError, ProvisioningError
        from mrack.providers import providers
        from mrack.providers.beaker import PROVISIONER_KEY as BEAKER
        from mrack.providers.beaker import BeakerProvider
        from mrack.transformers.beaker import BeakerTransformer

        # HAX remove mrack stdout and move the logfile to /tmp
        mrack.logger.removeHandler(mrack.console_handler)
        mrack.logger.removeHandler(mrack.file_handler)
        if os.stat("mrack.log"):
            os.remove("mrack.log")
        logging.FileHandler(str(f"{workdir}/{name}-mrack.log"))

        providers.register(BEAKER, BeakerProvider)

    except ImportError:
        raise ProvisionError("Install 'mrack' to provision using this method.")

    # ignore the misc because mrack sources are not typed and result into
    # error: Class cannot subclass "BeakerTransformer" (has type "Any")
    # as mypy does not have type information for the BeakerTransformer class
    class TmtBeakerTransformer(BeakerTransformer):  # type: ignore[misc]
        def _parse_amount(self, in_string: str) -> Tuple[str, int]:
            """ Return amount from given string """
            result = []
            amount = ""

            for op in operators:
                parts = in_string.split(op, maxsplit=1)
                if len(parts) != 2:
                    continue

                if parts[0]:
                    continue

                if any([op in parts[1] for op in op]):
                    continue

                result.append(op)
                amount = parts[1]
                break

            assert len(result) == 1
            assert len(amount) >= 1

            for size, multiplier in size_translation.items():
                if size not in amount:
                    continue

                result.append(str(multiplier * int(amount.split(size, maxsplit=1)[0])))
                break

            # returns operator, amount
            return result[0], int(result[1])

        def _translate_tmt_hw(self, hw: Dict[str, Any]) -> Dict[str, Any]:
            """ Return hw requirements from given hw dictionary """
            key = "_key"
            value = "_value"
            op = "_op"

            system = {}
            disks = []
            cpu = {}

            for key, val in hw.items():
                if key == "memory":
                    operator, amount = self._parse_amount(val)
                    system.update({
                        key: {
                            value: amount,
                            op: operator
                            }
                        })
                if key == "disk":
                    for dsk in val:
                        operator, disk = self._parse_amount(dsk["size"])
                        disks.append({
                            "disk": {
                                "size": {
                                    value: disk,
                                    op: operator,
                                    }
                                }
                            })
                if key == "cpu":
                    if val.get("processors"):
                        cpu.update({
                            "cpu_count": {
                                value: val["processors"],
                                op: "=",
                                }
                            })
                    if val.get("model"):
                        cpu.update({
                            "model": {
                                value: val["model"],
                                op: "=",
                                }
                            })

            and_req = []
            for rec in [system, disks, cpu]:
                if not rec:
                    continue
                if isinstance(rec, dict):
                    and_req.append(rec)
                if isinstance(rec, list):
                    and_req += rec

            host_req = {}
            if and_req:
                host_req = {
                    "hostRequires": {
                        "and": and_req
                        }
                    }

            return host_req

        def create_host_requirement(self, host: Dict[str, Any]) -> Dict[str, Any]:
            """ Create single input for Beaker provisioner """
            mrack_req: Dict[str, Any] = self._translate_tmt_hw(host.get("hardware", {}))
            host.update({"beaker": mrack_req})
            req: Dict[str, Any] = super().create_host_requirement(host)
            req.update({"whiteboard": host.get("tmt_name", req.get("whiteboard"))})
            return req


def async_run(func: Any) -> Any:
    """ Decorate click actions to run as async """
    @wraps(func)
    def update_wrapper(*args: Any, **kwargs: Any) -> Any:
        return asyncio.run(func(*args, **kwargs))

    return update_wrapper


@dataclasses.dataclass
class BeakerGuestData(tmt.steps.provision.GuestSshData):
    # Override parent class with our defaults
    user: str = DEFAULT_USER

    # Guest request properties
    arch: str = DEFAULT_ARCH
    image: Optional[str] = "fedora"
    hardware: Dict[str, Any] = dataclasses.field(default_factory=dict)

    # Provided in Beaker job
    job_id: Optional[str] = None

    # Timeouts and deadlines
    provision_timeout: int = DEFAULT_PROVISION_TIMEOUT
    provision_tick: int = DEFAULT_PROVISION_TICK


@dataclasses.dataclass
class ProvisionBeakerData(BeakerGuestData, tmt.steps.provision.ProvisionStepData):
    pass


GUEST_STATE_COLOR_DEFAULT = 'green'

GUEST_STATE_COLORS = {
    "New": "blue",
    "Scheduled": "blue",
    "Queued": "cyan",
    "Processed": "cyan",
    "Waiting": "magenta",
    "Installing": "magenta",
    "Running": "magenta",
    "Cancelled": "yellow",
    "Aborted": "yellow",
    "Reserved": "green",
    "Completed": "green",
    }


class BeakerAPI:
    # req is a requirement passed to Beaker mrack provisioner
    mrack_requirement: Dict[str, Any] = {}
    dsp_name: str = "Beaker"

    # wrapping around the __init__ with async wrapper does mangle the method
    # and mypy complains as it no longer returns None but the coroutine
    @async_run
    async def __init__(self, guest: 'GuestBeaker') -> None:  # type: ignore[misc]
        """ Initialize the API class with defaults and load the config """
        self._guest = guest

        # use global context class
        global_context = mrack.context.global_context
        mrack_config = ""

        if os.path.exists(os.path.join(os.path.dirname(__file__), "mrack/mrack.conf")):
            mrack_config = os.path.join(
                os.path.dirname(__file__),
                "mrack/mrack.conf",
                )

        if os.path.exists("/etc/tmt/mrack.conf"):
            mrack_config = "/etc/tmt/mrack.conf"

        if os.path.exists(os.path.join(os.path.expanduser("~"), ".mrack/mrack.conf")):
            mrack_config = os.path.join(os.path.expanduser("~"), ".mrack/mrack.conf")

        if os.path.exists(os.path.join(os.getcwd(), "mrack.conf")):
            mrack_config = os.path.join(os.getcwd(), "mrack.conf")

        if not mrack_config:
            raise ProvisionError("Configuration file 'mrack.conf' not found.")

        try:
            global_context.init(mrack_config)
        except mrack.errors.ConfigError as mrack_conf_err:
            raise ProvisionError(mrack_conf_err)

        self._mrack_transformer = TmtBeakerTransformer()
        try:
            await self._mrack_transformer.init(global_context.PROV_CONFIG, {})
        except NotAuthenticatedError as kinit_err:
            raise ProvisionError(kinit_err) from kinit_err
        except AttributeError as hub_err:
            raise ProvisionError(
                f"Can not use current kerberos ticket to authenticate: {hub_err}"
                ) from hub_err
        except FileNotFoundError as missing_conf_err:
            raise ProvisionError(
                f"Configuration file missing: {missing_conf_err.filename}"
                ) from missing_conf_err

        self._mrack_provider = self._mrack_transformer._provider
        self._mrack_provider.poll_sleep = DEFAULT_PROVISION_TICK

    @async_run
    async def create(
            self,
            data: Dict[str, Any],
            ) -> Any:
        """
        Create - or request creation of - a resource using mrack up.

        :param data: optional key/value data to send with the request.

        """
        mrack_requirement = self._mrack_transformer.create_host_requirement(data)
        log_msg_start = f"{self.dsp_name} [{self.mrack_requirement.get('name')}]"
        self._bkr_job_id, self._req = await self._mrack_provider.create_server(mrack_requirement)
        return self._mrack_provider._get_recipe_info(self._bkr_job_id, log_msg_start)

    @async_run
    async def inspect(
            self,
            ) -> Any:
        """ Inspect a resource (kinda wait till provisioned) """
        log_msg_start = f"{self.dsp_name} [{self.mrack_requirement.get('name')}]"
        return self._mrack_provider._get_recipe_info(self._bkr_job_id, log_msg_start)

    @async_run
    async def delete(  # destroy
            self,
            ) -> Any:
        """ Delete - or request removal of - a resource """
        return await self._mrack_provider.delete_host(self._bkr_job_id, None)


class GuestBeaker(tmt.GuestSsh):
    """ Beaker guest instance """
    _data_class = BeakerGuestData

    # Guest request properties
    arch: str
    image: str = "fedora-latest"
    hardware: Dict[str, Any] = {}

    # Provided in Beaker response
    job_id: Optional[str]

    # Timeouts and deadlines
    provision_timeout: int
    provision_tick: int
    _api: Optional[BeakerAPI] = None

    @property
    def api(self) -> BeakerAPI:
        """ Create BeakerAPI leveraging mrack """
        if self._api is None:
            self._api = BeakerAPI(self)

        return self._api

    @property
    def is_ready(self) -> bool:
        """ Check if provisioning of machine is done """
        if self.job_id is None:
            return False

        assert mrack is not None

        try:
            response = self.api.inspect()

            if response["status"] == "Aborted":
                return False

            current = cast(GuestInspectType, response)
            state = current["status"]
            if state in {"Error, Aborted", "Cancelled"}:
                return False

            if state == 'Reserved':
                return True
            else:
                return False

        except mrack.errors.MrackError:
            return False

    def _create(self, tmt_name: str) -> None:
        """ Create beaker job xml request and submit it to Beaker hub """

        data: Dict[str, Any] = {
            'tmt_name': tmt_name,
            'hardware': self.hardware,
            'name': f'{self.image}-{self.arch}',
            'os': self.image,
            'group': 'linux',
            }

        if self.arch is not None:
            data["arch"] = self.arch

        try:
            response = self.api.create(data)
        except ProvisioningError as mrack_provisioning_err:
            raise ProvisionError(
                f"Failed to create, response:\n{mrack_provisioning_err}")

        if response:
            self.info('guest', 'has been requested', 'green')

        else:
            raise ProvisionError(
                f"Failed to create, response: '{response}'.")

        self.job_id = response["id"] if not response["system"] else response["system"]
        self.info('job id', self.job_id, 'green')

        with updatable_message(
                "status", indent_level=self._level()) as progress_message:

            def get_new_state() -> GuestInspectType:
                response = self.api.inspect()

                if response["status"] == "Aborted":
                    raise ProvisionError(
                        f"Failed to create, "
                        f"unhandled API response '{response['status']}'."
                        )

                current = cast(GuestInspectType, response)
                state = current["status"]
                state_color = GUEST_STATE_COLORS.get(
                    state, GUEST_STATE_COLOR_DEFAULT
                    )

                progress_message.update(state, color=state_color)

                if state in {"Error, Aborted", "Cancelled"}:
                    raise ProvisionError(
                        'Failed to create, provisioning failed.'
                        )

                if state == 'Reserved':
                    return current

                raise tmt.utils.WaitingIncomplete()

            try:
                guest_info = tmt.utils.wait(
                    self, get_new_state, datetime.timedelta(
                        seconds=self.provision_timeout),
                    tick=self.provision_tick
                    )

            except tmt.utils.WaitingTimedOutError:
                response = self.api.delete()
                raise ProvisionError(
                    f'Failed to provision in the given amount '
                    f'of time (--provision-timeout={self.provision_timeout}).'
                    )

        self.guest = guest_info['system']
        self.info('address', self.guest, 'green')

    def start(self) -> None:
        """
        Start the guest

        Get a new guest instance running. This should include preparing
        any configuration necessary to get it started. Called after
        load() is completed so all guest data should be available.
        """

        if self.job_id is None or self.guest is None:
            self._create(self._tmt_name())

    def stop(self) -> None:
        """ Stop the guest """
        # do nothing
        return

    def remove(self) -> None:
        """ Remove the guest """

        if self.job_id is None:
            return

        self.api.delete()


@tmt.steps.provides_method('beaker')
class ProvisionBeaker(tmt.steps.provision.ProvisionPlugin):
    """
    Provision guest on Beaker system using mrack

    Minimal configuration could look like this:

        provision:
            how: beaker
            image: fedora

    """

    _data_class = ProvisionBeakerData
    _guest_class = GuestBeaker

    # Guest instance
    _guest = None

    @classmethod
    def options(cls, how: Optional[str] = None) -> List[tmt.options.ClickOptionDecoratorType]:
        """ Prepare command line options for Beaker """
        return [
            click.option(
                '--arch', metavar='ARCH',
                help='Architecture to provision.'
                ),
            click.option(
                '--image', metavar='COMPOSE',
                help='Image (distro or "compose" in Beaker terminology) '
                     'to provision.'
                ),
            click.option(
                '--provision-timeout', metavar='SECONDS',
                help=f'How long to wait for provisioning to complete, '
                     f'{DEFAULT_PROVISION_TIMEOUT} seconds by default.'
                ),
            click.option(
                '--provision-tick', metavar='SECONDS',
                help=f'How often check Beaker for provisioning status, '
                     f'{DEFAULT_PROVISION_TICK} seconds by default.',
                ),
            ] + super().options(how)

    # data argument should be a "Optional[GuestData]" type but we would like to use
    # BeakerGuestData created here ignoring the override will make mypy calm
    def wake(self, data: Optional[BeakerGuestData] = None) -> None:  # type: ignore[override]
        """ Wake up the plugin, process data, apply options """
        super().wake(data=data)

        if data:
            self._guest = GuestBeaker(
                data=data,
                name=self.name,
                parent=self.step,
                logger=self._logger,
                )

    def go(self) -> None:
        """ Provision the guest """
        import_and_load_mrack_deps(self.workdir, self.name)

        super().go()

        data = BeakerGuestData(
            arch=self.get('arch'),
            image=self.get('image'),
            hardware=self.get('hardware'),
            user=self.get('user'),
            provision_timeout=self.get('provision-timeout'),
            provision_tick=self.get('provision-tick'),
            )

        self._guest = GuestBeaker(
            data=data,
            name=self.name,
            parent=self.step,
            logger=self._logger,
            )
        self._guest.start()

    def guest(self) -> Optional[GuestBeaker]:
        """ Return the provisioned guest """
        return self._guest
