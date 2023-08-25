import asyncio
import dataclasses
import datetime
import logging
import os
from contextlib import suppress
from functools import wraps
from typing import Any, Dict, List, Optional, Tuple, TypedDict, cast

import tmt
import tmt.hardware
import tmt.log
import tmt.options
import tmt.steps
import tmt.steps.provision
import tmt.utils
from tmt.utils import ProvisionError, field, updatable_message

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
DEFAULT_IMAGE = 'fedora'
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


SUPPORTED_HARDWARE_CONSTRAINTS: List[str] = [
    'cpu.processors',
    'cpu.model',
    'disk.size',
    'hostname',
    'memory'
    ]


# Mapping of HW requirement operators to their Beaker representation.
OPERATOR_SIGN_TO_OPERATOR = {
    tmt.hardware.Operator.EQ: '==',
    tmt.hardware.Operator.NEQ: '!=',
    tmt.hardware.Operator.GT: '>',
    tmt.hardware.Operator.GTE: '>=',
    tmt.hardware.Operator.LT: '<',
    tmt.hardware.Operator.LTE: '<=',
    }


def operator_to_beaker_op(operator: tmt.hardware.Operator, value: str) -> Tuple[str, str, bool]:
    """
    Convert constraint operator to Beaker "op".

    :param operator: operator to convert.
    :param value: value operator works with. It shall be a string representation
        of the the constraint value, as converted for the Beaker job XML.
    :returns: tuple of three items: Beaker operator, fit for ``op`` attribute
        of XML filters, a value to go with it instead of the input one, and
        a boolean signalizing whether the filter, constructed by the caller,
        should be negated.
    """

    if operator in OPERATOR_SIGN_TO_OPERATOR:
        return OPERATOR_SIGN_TO_OPERATOR[operator], value, True

    # MATCH has special handling - convert the pattern to a wildcard form -
    # and that may be weird :/
    if operator == tmt.hardware.Operator.MATCH:
        return 'like', value.replace('.*', '%').replace('.+', '%'), False

    if operator == tmt.hardware.Operator.NOTMATCH:
        return 'like', value.replace('.*', '%').replace('.+', '%'), True

    raise ProvisionError(f"Hardware requirement operator '{operator}' is not supported.")


# Transcription of our HW constraints into Mrack's own representation. It's based
# on dictionaries, and it's slightly weird. There is no distinction between elements
# that do not have attributes, like <and/>, and elements that must have them, like
# <memory/> and other binary operations. Also, there is no distinction betwen
# element attribute and child element, both are specified as dictionary key, just
# the former would be a string, the latter another, nested, dictionary.
#
# This makes it harder for us to enforce correct structure of the transcribed tree.
# Therefore adding a thin layer of containers that describe what Mrack is willing
# to accept, but with strict type annotations; the layer is aware of how to convert
# its components into dictionaries.
@dataclasses.dataclass
class MrackBaseHWElement:
    """ Base for Mrack hardware requirement elements """

    # Only a name is defined, as it's the only property shared across all element
    # types.
    name: str

    def to_mrack(self) -> Dict[str, Any]:
        """ Convert the element to Mrack-compatible dictionary tree """
        raise NotImplementedError


@dataclasses.dataclass
class MrackHWElement(MrackBaseHWElement):
    """
    An element with name and attributes.

    This type of element is not allowed to have any child elements.
    """

    attributes: Dict[str, str] = dataclasses.field(default_factory=dict)

    def to_mrack(self) -> Dict[str, Any]:
        return {
            self.name: self.attributes
            }


@dataclasses.dataclass(init=False)
class MrackHWBinOp(MrackHWElement):
    """ An element describing a binary operation, a "check" """

    def __init__(self, name: str, operator: str, value: str) -> None:
        super().__init__(name)

        self.attributes = {
            '_op': operator,
            '_value': value
            }


@dataclasses.dataclass
class MrackHWGroup(MrackBaseHWElement):
    """
    An element with child elements.

    This type of element is not allowed to have any attributes.
    """

    children: List[MrackBaseHWElement] = dataclasses.field(default_factory=list)

    def to_mrack(self) -> Dict[str, Any]:
        # Another unexpected behavior of mrack dictionary tree: if there is just
        # a single child, it is "packed" into its parent as a key/dict item.
        if len(self.children) == 1 and self.name not in ('and', 'or'):
            return {
                self.name: self.children[0].to_mrack()
                }

        return {
            self.name: [child.to_mrack() for child in self.children]
            }


@dataclasses.dataclass
class MrackHWAndGroup(MrackHWGroup):
    """ Represents ``<and/>`` element """

    name: str = 'and'


@dataclasses.dataclass
class MrackHWOrGroup(MrackHWGroup):
    """ Represents ``<or/>`` element """

    name: str = 'or'


@dataclasses.dataclass
class MrackHWNotGroup(MrackHWGroup):
    """ Represents ``<not/>`` element """

    name: str = 'not'


def constraint_to_beaker_filter(
        constraint: tmt.hardware.BaseConstraint,
        logger: tmt.log.Logger) -> MrackBaseHWElement:
    """ Convert a hardware constraint into a Mrack-compatible filter """

    if isinstance(constraint, tmt.hardware.And):
        return MrackHWAndGroup(
            children=[
                constraint_to_beaker_filter(child_constraint, logger)
                for child_constraint in constraint.constraints
                ]
            )

    if isinstance(constraint, tmt.hardware.Or):
        return MrackHWOrGroup(
            children=[
                constraint_to_beaker_filter(child_constraint, logger)
                for child_constraint in constraint.constraints
                ]
            )

    assert isinstance(constraint, tmt.hardware.Constraint)

    name, _, child_name = constraint.expand_name()

    if name == 'memory':
        beaker_operator, actual_value, _ = operator_to_beaker_op(
            constraint.operator,
            str(int(cast('tmt.hardware.Size', constraint.value).to('MiB').magnitude)))

        return MrackHWGroup(
            'system',
            children=[MrackHWBinOp('memory', beaker_operator, actual_value)])

    if name == "disk" and child_name == 'size':
        beaker_operator, actual_value, _ = operator_to_beaker_op(
            constraint.operator,
            str(int(cast('tmt.hardware.Size', constraint.value).to('B').magnitude))
            )

        return MrackHWGroup(
            'disk',
            children=[MrackHWBinOp('size', beaker_operator, actual_value)])

    if name == 'hostname':
        assert isinstance(constraint.value, str)

        beaker_operator, actual_value, negate = operator_to_beaker_op(
            constraint.operator,
            constraint.value)

        if negate:
            return MrackHWNotGroup(children=[
                MrackHWBinOp('hostname', beaker_operator, actual_value)
                ])

        return MrackHWBinOp(
            'hostname',
            beaker_operator,
            actual_value)

    if name == "cpu":
        beaker_operator, actual_value, _ = operator_to_beaker_op(
            constraint.operator,
            str(constraint.value))

        if child_name == 'processors':
            return MrackHWGroup(
                'cpu',
                children=[MrackHWBinOp('cpu_count', beaker_operator, actual_value)])

        if child_name == 'model':
            return MrackHWGroup(
                'cpu',
                children=[MrackHWBinOp('model', beaker_operator, actual_value)])

    # Unsupported constraint has been already logged via report_support(). Make
    # sure user is aware it would have no effect, and since we have to return
    # something, return an empty `or` group - no harm done, composable with other
    # elements.
    logger.warn(f"Hardware requirement '{constraint.printable_name}' will have no effect.")

    return MrackHWOrGroup()


def import_and_load_mrack_deps(workdir: Any, name: str, logger: tmt.log.Logger) -> None:
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

        with suppress(OSError):
            os.remove("mrack.log")

        logging.FileHandler(str(f"{workdir}/{name}-mrack.log"))

        providers.register(BEAKER, BeakerProvider)

    except ImportError:
        raise ProvisionError("Install 'mrack' to provision using this method.")

    # ignore the misc because mrack sources are not typed and result into
    # error: Class cannot subclass "BeakerTransformer" (has type "Any")
    # as mypy does not have type information for the BeakerTransformer class
    class TmtBeakerTransformer(BeakerTransformer):  # type: ignore[misc]
        def _translate_tmt_hw(self, hw: tmt.hardware.Hardware) -> Dict[str, Any]:
            """ Return hw requirements from given hw dictionary """

            assert hw.constraint

            transformed = MrackHWAndGroup(
                children=[
                    constraint_to_beaker_filter(constraint, logger)
                    for constraint in hw.constraint.variant()
                    ])

            logger.debug('Transformed hardware', tmt.utils.dict_to_yaml(transformed.to_mrack()))

            return {
                'hostRequires': transformed.to_mrack()
                }

        def create_host_requirement(self, host: Dict[str, Any]) -> Dict[str, Any]:
            """ Create single input for Beaker provisioner """
            hardware = cast(Optional[tmt.hardware.Hardware], host.get('hardware'))
            if hardware and hardware.constraint:
                host.update({"beaker": self._translate_tmt_hw(hardware)})
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
    # Override parent class with our defaults
    user: Optional[str] = field(
        default=DEFAULT_USER,
        option=('-u', '--user'),
        metavar='USERNAME',
        help='Username to use for all guest operations.'
        )

    # Guest request properties
    arch: str = field(
        default=DEFAULT_ARCH,
        option='--arch',
        metavar='ARCH',
        help='Architecture to provision.')
    image: Optional[str] = field(
        default=DEFAULT_IMAGE,
        option='--image',
        metavar='COMPOSE',
        help='Image (distro or "compose" in Beaker terminology) to provision.')

    # Provided in Beaker job
    job_id: Optional[str] = None

    # Timeouts and deadlines
    provision_timeout: int = field(
        default=DEFAULT_PROVISION_TIMEOUT,
        option='--provision-timeout',
        metavar='SECONDS',
        help=f'How long to wait for provisioning to complete, '
        f'{DEFAULT_PROVISION_TIMEOUT} seconds by default.',
        normalize=tmt.utils.normalize_int)
    provision_tick: int = field(
        default=DEFAULT_PROVISION_TICK,
        option='--provision-tick',
        metavar='SECONDS',
        help=f'How often check Beaker for provisioning status, '
        f'{DEFAULT_PROVISION_TICK} seconds by default.',
        normalize=tmt.utils.normalize_int)


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


class GuestBeaker(tmt.steps.provision.GuestSsh):
    """ Beaker guest instance """
    _data_class = BeakerGuestData

    # Guest request properties
    arch: str
    image: str = "fedora-latest"
    hardware: Optional[tmt.hardware.Hardware] = None

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

                raise tmt.utils.WaitingIncompleteError

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
        import_and_load_mrack_deps(self.workdir, self.name, self._logger)

        super().go()

        data = BeakerGuestData(
            arch=self.get('arch'),
            image=self.get('image'),
            hardware=self.get('hardware'),
            user=self.get('user'),
            provision_timeout=self.get('provision-timeout'),
            provision_tick=self.get('provision-tick'),
            )

        data.show(verbose=self.verbosity_level, logger=self._logger)

        if data.hardware:
            data.hardware.report_support(
                names=SUPPORTED_HARDWARE_CONSTRAINTS,
                logger=self._logger)

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
