
import collections
import dataclasses
import datetime
import functools
import itertools
import os
import platform
import re
import threading
import types
from collections.abc import Iterator
from string import Template
from typing import TYPE_CHECKING, Any, Optional, Union, cast

import click
import pint
import requests

import tmt
import tmt.hardware
import tmt.log
import tmt.steps
import tmt.steps.provision
import tmt.utils
from tmt.utils import (
    WORKDIR_ROOT,
    Command,
    Path,
    ProvisionError,
    ShellScript,
    configure_constant,
    field,
    retry_session,
    )

if TYPE_CHECKING:
    import tmt.base
    from tmt.hardware import Size


libvirt: Optional[types.ModuleType] = None
testcloud: Optional[types.ModuleType] = None

# To silence mypy
DomainConfiguration: Any
Workarounds: Any
X86_64ArchitectureConfiguration: Any
AArch64ArchitectureConfiguration: Any
S390xArchitectureConfiguration: Any
Ppc64leArchitectureConfiguration: Any
SystemNetworkConfiguration: Any
UserNetworkConfiguration: Any
QCow2StorageDevice: Any
RawStorageDevice: Any
TPMConfiguration: Any


def import_testcloud() -> None:
    """ Import testcloud module only when needed """
    global testcloud
    global libvirt
    global Workarounds
    global DomainConfiguration
    global X86_64ArchitectureConfiguration
    global AArch64ArchitectureConfiguration
    global S390xArchitectureConfiguration
    global Ppc64leArchitectureConfiguration
    global SystemNetworkConfiguration
    global UserNetworkConfiguration
    global QCow2StorageDevice
    global RawStorageDevice
    global TPMConfiguration
    try:
        import libvirt
        import testcloud.image
        import testcloud.instance
        import testcloud.util
        from testcloud.domain_configuration import (
            AArch64ArchitectureConfiguration,
            DomainConfiguration,
            Ppc64leArchitectureConfiguration,
            QCow2StorageDevice,
            RawStorageDevice,
            S390xArchitectureConfiguration,
            SystemNetworkConfiguration,
            TPMConfiguration,
            UserNetworkConfiguration,
            X86_64ArchitectureConfiguration,
            )
        from testcloud.workarounds import Workarounds
    except ImportError as error:
        raise ProvisionError(
            "Install 'tmt+provision-virtual' to provision using this method.") from error

    # Version-aware TPM configuration is added in
    # https://pagure.io/testcloud/c/89f1c024ca829543de7f74f89329158c6dee3d83
    global TPM_CONFIG_ALLOWS_VERSIONS
    TPM_CONFIG_ALLOWS_VERSIONS = hasattr(TPMConfiguration(), 'version')


# Testcloud cache to our tmt's workdir root
TESTCLOUD_DATA = (
    Path(os.environ['TMT_WORKDIR_ROOT']) if os.getenv('TMT_WORKDIR_ROOT') else WORKDIR_ROOT
    ) / 'testcloud'
TESTCLOUD_IMAGES = TESTCLOUD_DATA / 'images'

TESTCLOUD_WORKAROUNDS: list[str] = []  # A list of commands to be executed during guest boot up

# Userdata for cloud-init
# TODO: Explore migration to jinja from string.Template
USER_DATA = """#cloud-config
chpasswd:
  list: |
    ${user_name}:${password}
  expire: false
users:
  - default
  - name: ${user_name}
ssh_authorized_keys:
  - ${public_key}
ssh_pwauth: true
disable_root: false
runcmd:
${runcommands}
"""

COREOS_DATA = """variant: fcos
version: 1.4.0
passwd:
  users:
    - name: ${user_name}
      ssh_authorized_keys:
        - ${public_key}
systemd:
  units:
    - name: ssh_root_login.service
      enabled: true
      contents: |
        [Unit]
        Before=sshd.service
        [Service]
        Type=oneshot
        ExecStart=/usr/bin/sed -i \
                  "s|^PermitRootLogin no$|PermitRootLogin yes|g" \
                  /etc/ssh/sshd_config
        [Install]
        WantedBy=multi-user.target
"""

# VM defaults
#: How many seconds to wait for a VM to start.
#: This is the default value tmt would use unless told otherwise.
DEFAULT_BOOT_TIMEOUT: int = 2 * 60

#: How many seconds to wait for a VM to start.
#: This is the effective value, combining the default and optional envvar,
#: ``TMT_BOOT_TIMEOUT``.
BOOT_TIMEOUT: int = configure_constant(DEFAULT_BOOT_TIMEOUT, 'TMT_BOOT_TIMEOUT')

#: How many seconds to wait for a connection to succeed after guest boot.
#: This is the default value tmt would use unless told otherwise.
DEFAULT_CONNECT_TIMEOUT = 2 * 60

#: How many seconds to wait for a connection to succeed after guest boot.
#: This is the effective value, combining the default and optional envvar,
#: ``TMT_CONNECT_TIMEOUT``.
CONNECT_TIMEOUT: int = configure_constant(DEFAULT_CONNECT_TIMEOUT, 'TMT_CONNECT_TIMEOUT')

#: How many times should the timeouts be multiplied in kvm-less cases.
#: These include emulating a different architecture than the host,
#: some nested virtualization cases, and hosts with degraded virt caps.
NON_KVM_TIMEOUT_COEF = 10      # times

# SSH key type, set None for ssh-keygen default one
SSH_KEYGEN_TYPE = "ecdsa"

DEFAULT_USER = 'root'
DEFAULT_CPU_COUNT = 2
DEFAULT_MEMORY: 'Size' = tmt.hardware.UNITS('2048 MB')
DEFAULT_DISK: 'Size' = tmt.hardware.UNITS('40 GB')
DEFAULT_IMAGE = 'fedora'
DEFAULT_CONNECTION = 'session'
DEFAULT_ARCH = platform.machine()

# Version-aware TPM configuration is added in
# https://pagure.io/testcloud/c/89f1c024ca829543de7f74f89329158c6dee3d83
#: If set, ``testcloud`` TPM configuration accepts TPM version as a parameter.
TPM_CONFIG_ALLOWS_VERSIONS: bool = False

#: List of operators supported for ``tpm.version`` HW requirement.
TPM_VERSION_ALLOWED_OPERATORS: tuple[tmt.hardware.Operator, ...] = (
    tmt.hardware.Operator.EQ,
    tmt.hardware.Operator.GTE,
    tmt.hardware.Operator.LTE)

#: TPM versions supported by the plugin. The key is :py:const:`TPM_CONFIG_ALLOWS_VERSIONS`.
TPM_VERSION_SUPPORTED_VERSIONS = {
    True: ['2.0', '2', '1.2'],
    # This is the default version used by testcloud before version became
    # an input parameter of TPM configuration.
    False: ['2.0', '2']
    }


def normalize_memory_size(
        key_address: str,
        value: Any,
        logger: tmt.log.Logger) -> Optional['Size']:
    """
    Normalize memory size.

    As of now, it's just a simple integer with implicit unit, ``MB``.
    """

    if value is None:
        return None

    if isinstance(value, pint.Quantity):
        return value

    if isinstance(value, str):
        try:
            magnitude = int(value)

        except ValueError:
            return tmt.hardware.UNITS(value)

        return tmt.hardware.UNITS(f'{magnitude} MB')

    if isinstance(value, int):
        return tmt.hardware.UNITS(f'{value} MB')

    raise tmt.utils.NormalizationError(key_address, value, 'an integer')


def normalize_disk_size(key_address: str, value: Any, logger: tmt.log.Logger) -> Optional['Size']:
    """
    Normalize disk size.

    As of now, it's just a simple integer with implicit unit, ``GB``.
    """

    if value is None:
        return None

    if isinstance(value, pint.Quantity):
        return value

    if isinstance(value, str):
        try:
            magnitude = int(value)

        except ValueError:
            return tmt.hardware.UNITS(value)

        return tmt.hardware.UNITS(f'{magnitude} GB')

    if isinstance(value, int):
        return tmt.hardware.UNITS(f'{value} GB')

    raise tmt.utils.NormalizationError(key_address, value, 'an integer')


def _report_hw_requirement_support(constraint: tmt.hardware.Constraint[Any]) -> bool:
    components = constraint.expand_name()

    if components.name == 'memory' \
        and constraint.operator in (tmt.hardware.Operator.EQ,
                                    tmt.hardware.Operator.GTE,
                                    tmt.hardware.Operator.LTE):
        return True

    if components.name == 'cpu' \
        and components.child_name == 'processors' \
        and constraint.operator in (tmt.hardware.Operator.EQ,
                                    tmt.hardware.Operator.LTE,
                                    tmt.hardware.Operator.GTE,
                                    tmt.hardware.Operator.NEQ,
                                    tmt.hardware.Operator.LT,
                                    tmt.hardware.Operator.GT):
        return True

    if components.name == 'disk' \
        and components.child_name == 'size' \
        and constraint.operator in (tmt.hardware.Operator.EQ,
                                    tmt.hardware.Operator.GTE,
                                    tmt.hardware.Operator.LTE):
        return True

    if components.name == 'tpm' \
            and components.child_name == 'version' \
            and constraint.value in TPM_VERSION_SUPPORTED_VERSIONS[TPM_CONFIG_ALLOWS_VERSIONS] \
            and constraint.operator in TPM_VERSION_ALLOWED_OPERATORS:
        return True

    return False


@dataclasses.dataclass
class TestcloudGuestData(tmt.steps.provision.GuestSshData):
    # Override parent class with our defaults
    user: str = field(
        default=DEFAULT_USER,
        option=('-u', '--user'),
        metavar='USERNAME',
        help='Username to use for all guest operations.')

    image: str = field(
        default=DEFAULT_IMAGE,
        option=('-i', '--image'),
        metavar='IMAGE',
        help="""
             Select image to be used. Provide a short name, full path to a local file
             or a complete url.
             """)
    memory: Optional['Size'] = field(
        default=cast(Optional['Size'], None),
        option=('-m', '--memory'),
        metavar='SIZE',
        help='Set available memory in MB, 2048 MB by default.',
        normalize=normalize_memory_size,
        serialize=lambda value: str(value) if value is not None else None,
        unserialize=lambda serialized: tmt.hardware.UNITS(serialized)
        if serialized is not None else None)
    disk: Optional['Size'] = field(
        default=cast(Optional['Size'], None),
        option=('-D', '--disk'),
        metavar='SIZE',
        help='Specify disk size in GB, 10 GB by default.',
        normalize=normalize_disk_size,
        serialize=lambda value: str(value) if value is not None else None,
        unserialize=lambda serialized: tmt.hardware.UNITS(serialized)
        if serialized is not None else None)
    connection: str = field(
        default=DEFAULT_CONNECTION,
        option=('-c', '--connection'),
        choices=['session', 'system'],
        help="What session type to use, 'session' by default.")
    arch: str = field(
        default=DEFAULT_ARCH,
        option=('-a', '--arch'),
        choices=['x86_64', 'aarch64', 's390x', 'ppc64le'],
        help="What architecture to virtualize, host arch by default.")

    list_local_images: bool = field(
        default=False,
        option='--list-local-images',
        is_flag=True,
        help="List locally available images.")

    image_url: Optional[str] = None
    instance_name: Optional[str] = None

    # TODO: custom handling for two fields - when the formatting moves into
    # field(), this should not be necessary.
    def show(
            self,
            *,
            keys: Optional[list[str]] = None,
            verbose: int = 0,
            logger: tmt.log.Logger) -> None:

        keys = keys or list(self.keys())
        super_keys = [key for key in keys if key not in ('memory', 'disk')]

        super().show(keys=super_keys, verbose=verbose, logger=logger)

        # TODO: find formatting that would show "MB" instead of "megabyte"
        # https://github.com/teemtee/tmt/issues/2410
        logger.info('memory', f'{(self.memory or DEFAULT_MEMORY).to("MB")}', 'green')
        logger.info('disk', f'{(self.disk or DEFAULT_DISK).to("GB")}', 'green')


@dataclasses.dataclass
class ProvisionTestcloudData(TestcloudGuestData, tmt.steps.provision.ProvisionStepData):
    pass


def _apply_hw_tpm(
        hardware: Optional[tmt.hardware.Hardware],
        domain: 'DomainConfiguration',
        logger: tmt.log.Logger) -> None:
    """ Apply ``tpm`` constraint to given VM domain """

    domain.tpm_configuration = None

    if not hardware or not hardware.constraint:
        logger.debug(
            'tpm.version',
            "not included because of no constraints",
            level=4)

        return

    variant = hardware.constraint.variant()

    tpm_constraints = [
        constraint
        for constraint in variant
        if isinstance(constraint, tmt.hardware.TextConstraint)
        and constraint.expand_name().name == 'tpm'
        and constraint.expand_name().child_name == 'version']

    if not tpm_constraints:
        logger.debug(
            'tpm.version',
            "not included because of no 'tpm.version' constraints",
            level=4)

        return

    for constraint in tpm_constraints:
        if constraint.operator not in TPM_VERSION_ALLOWED_OPERATORS:
            logger.warning(
                f"Cannot apply hardware requirement '{constraint}', operator not supported.")
            return

        if constraint.value not in TPM_VERSION_SUPPORTED_VERSIONS[TPM_CONFIG_ALLOWS_VERSIONS]:
            logger.warning(
                f"Cannot apply hardware requirement '{constraint}',"
                " TPM version not supported.")
            return

        logger.debug(
            'tpm.version',
            f"set to '{constraint.value}' because of '{constraint}'",
            level=4)

        if TPM_CONFIG_ALLOWS_VERSIONS:
            domain.tpm_configuration = TPMConfiguration(version=constraint.value)

        else:
            domain.tpm_configuration = TPMConfiguration()


def _apply_hw_disk_size(
        hardware: Optional[tmt.hardware.Hardware],
        domain: 'DomainConfiguration',
        logger: tmt.log.Logger) -> None:
    """ Apply ``disk`` constraint to given VM domain """

    final_size: Size = DEFAULT_DISK

    def _generate_disk_filepaths() -> Iterator[Path]:
        """ Generate paths to use for files representing VM storage """

        # Start with the path already decided by testcloud...
        yield Path(domain.local_disk)

        # ... and use it as a basis for remaining paths.
        for i in itertools.count(1, 1):
            yield Path(f'{domain.local_disk}.{i}')

    disk_filepath_generator = _generate_disk_filepaths()

    if not hardware or not hardware.constraint:
        logger.debug(
            'disk[0].size',
            f"set to '{final_size}' because of no constraints",
            level=4)

        domain.storage_devices = [
            QCow2StorageDevice(
                str(next(disk_filepath_generator)),
                int(final_size.to('GB').magnitude))
            ]

        return

    variant = hardware.constraint.variant()

    # Collect all `disk.size` constraints, ignore the rest.
    disk_size_constraints = [
        constraint
        for constraint in variant
        if isinstance(constraint, tmt.hardware.SizeConstraint)
        and constraint.expand_name().name == 'disk'
        and constraint.expand_name().child_name == 'size']

    if not disk_size_constraints:
        logger.debug(
            'disk[0].size',
            f"set to '{final_size}' because of no 'disk.size' constraints",
            level=4)

        domain.storage_devices = [
            QCow2StorageDevice(
                str(next(disk_filepath_generator)),
                int(final_size.to('GB').magnitude))
            ]

        return

    # Now sort them into groups by their `peer_index`, i.e. `disk[0]`,
    # `disk[1]` and so on.
    by_peer_index: dict[int, list[tmt.hardware.SizeConstraint]] = collections.defaultdict(list)

    for constraint in disk_size_constraints:
        if constraint.operator not in (
                tmt.hardware.Operator.EQ,
                tmt.hardware.Operator.GTE,
                tmt.hardware.Operator.LTE):
            raise ProvisionError(
                f"Cannot apply hardware requirement '{constraint}', operator not supported.")

        components = constraint.expand_name()

        assert components.peer_index is not None  # narrow type

        by_peer_index[components.peer_index].append(constraint)

    # Process each disk and its constraints, construct the
    # corresponding storage device, and the last constraint wins
    # & sets its size.
    for peer_index in sorted(by_peer_index.keys()):
        final_size = DEFAULT_DISK

        for constraint in by_peer_index[peer_index]:
            logger.debug(
                f'disk[{peer_index}].size',
                f"set to '{constraint.value}' because of '{constraint}'",
                level=4)

            final_size = constraint.value

        domain.storage_devices.append(
            QCow2StorageDevice(
                str(next(disk_filepath_generator)),
                int(final_size.to('GB').magnitude))
            )


def _apply_hw_cpu_processors(
        hardware: Optional[tmt.hardware.Hardware],
        domain: 'DomainConfiguration',
        logger: tmt.log.Logger) -> None:
    """ Apply ``cpu.processors`` constraint to given VM domain """

    domain.cpu_count = DEFAULT_CPU_COUNT

    if not hardware or not hardware.constraint:
        logger.debug(
            'cpu.processors',
            "not included because of no constraints",
            level=4)

        return

    variant = hardware.constraint.variant()

    cpu_processors_constraints = [
        constraint
        for constraint in variant
        if isinstance(constraint, tmt.hardware.NumberConstraint)
        and constraint.expand_name().name == 'cpu'
        and constraint.expand_name().child_name == 'processors']

    if not cpu_processors_constraints:
        logger.debug(
            'cpu.processors',
            "not included because of no 'cpu.processors' constraints",
            level=4)

        return

    for constraint in cpu_processors_constraints:
        if constraint.operator in (
                tmt.hardware.Operator.EQ,
                tmt.hardware.Operator.LTE,
                tmt.hardware.Operator.GTE):
            logger.debug(
                'cpu.processors',
                f"set to '{constraint.value}' because of '{constraint}'",
                level=4)

            domain.cpu_count = constraint.value

        elif constraint.operator is tmt.hardware.Operator.NEQ \
                and domain.cpu_count != constraint.value:
            logger.debug(
                'cpu.processors',
                f"kept at '{constraint.value}' because of '{constraint}'",
                level=4)

        elif constraint.operator is tmt.hardware.Operator.LT:
            logger.debug(
                'cpu.processors',
                f"set to '{constraint.value - 1}' because of '{constraint}'",
                level=4)

            domain.cpu_count = constraint.value - 1

        elif constraint.operator is tmt.hardware.Operator.GT:
            logger.debug(
                'cpu.processors',
                f"set to '{constraint.value + 1}' because of '{constraint}'",
                level=4)

            domain.cpu_count = constraint.value + 1

        else:
            raise ProvisionError(
                f"Cannot apply hardware requirement '{constraint}', operator not supported.")


class GuestTestcloud(tmt.GuestSsh):
    """
    Testcloud Instance

    The following keys are expected in the 'data' dictionary::

        image ...... qcov image name or url
        user ....... user name to log in
        memory ..... memory size for vm
        disk ....... disk size for vm
        connection . either session (default) or system, to be passed to qemu
        arch ....... architecture for the VM, host arch is the default
    """

    _data_class = TestcloudGuestData

    image: str
    image_url: Optional[str]
    instance_name: Optional[str]
    memory: Optional['Size']
    disk: Optional['Size']
    connection: str
    arch: str

    # Not to be saved, recreated from image_url/instance_name/... every
    # time guest is instantiated.
    # FIXME: ignore[name-defined]: https://github.com/teemtee/tmt/issues/1616
    _image: Optional['testcloud.image.Image'] = None  # type: ignore[name-defined]
    _instance: Optional['testcloud.instance.Instance'] = None  # type: ignore[name-defined]
    _domain: Optional[  # type: ignore[name-defined]
        'testcloud.domain_configuration.DomainConfiguration'] = None

    #: The lock protects calls into the testcloud library. We suspect it might
    #: be unprepared for multi-threaded use. After the dust settles, we may
    #: remove the lock.
    _testcloud_lock = threading.Lock()

    @property
    def is_ready(self) -> bool:
        if self._instance is None:
            return False

        assert testcloud is not None
        assert libvirt is not None
        try:
            state = testcloud.instance._find_domain(
                self._instance.name, self._instance.connection)
            # Note the type of variable 'state' is 'Any'. Hence, we don't use:
            #     return state == 'running'
            # to avoid error from type checking.
            return bool(state == "running")
        except libvirt.libvirtError:
            return False

    @functools.cached_property
    def is_kvm(self) -> bool:
        # Is the combination of host-requested architecture kvm capable?
        return bool(self.arch == platform.machine() and os.path.exists("/dev/kvm"))

    @functools.cached_property
    def is_legacy_os(self) -> bool:
        assert testcloud is not None  # narrow post-import type
        assert self._image is not None  # narrow type

        # Is this el <= 7?
        return cast(bool, testcloud.util.needs_legacy_net(self._image.name))

    @functools.cached_property
    def is_coreos(self) -> bool:
        # Is this a CoreOS?
        return bool(re.search('coreos|rhcos', self.image.lower()))

    def _get_url(self, url: str, message: str) -> requests.Response:
        """ Get url, retry when fails, return response """

        def try_get_url() -> requests.Response:
            try:
                with retry_session() as session:
                    response = session.get(url)

                if response.ok:
                    return response

            except requests.RequestException:
                pass
            finally:
                raise tmt.utils.WaitingIncompleteError

        try:
            return tmt.utils.wait(
                self, try_get_url, datetime.timedelta(
                    seconds=CONNECT_TIMEOUT), tick=1)

        except tmt.utils.WaitingTimedOutError:
            raise ProvisionError(
                f'Failed to {message} in {CONNECT_TIMEOUT}s.')

    def _guess_image_url(self, name: str) -> str:
        """ Guess image url for given name """

        # Try to check if given url is a local file
        name_as_path = Path(name)
        if name_as_path.is_absolute() and name_as_path.is_file():
            return f'file://{name}'

        url: Optional[str] = None
        assert testcloud is not None

        with GuestTestcloud._testcloud_lock:
            try:
                url = testcloud.util.get_image_url(name.lower().strip(), self.arch)
            except Exception as error:
                raise ProvisionError("Could not get image url.") from error

        if not url:
            raise ProvisionError(f"Could not map '{name}' to compose.")
        return url

    def wake(self) -> None:
        """ Wake up the guest """
        self.debug(
            f"Waking up testcloud instance '{self.instance_name}'.",
            level=2, shift=0)
        self.prepare_config()
        assert testcloud is not None
        self._image = testcloud.image.Image(self.image_url)
        if self.instance_name is None:
            raise ProvisionError(f"The instance name '{self.instance_name}' is invalid.")

        self._domain = DomainConfiguration(self.instance_name)
        self._apply_hw_arch(self._domain, self.is_kvm, self.is_legacy_os)

        self._instance = testcloud.instance.Instance(
            domain_configuration=self._domain,
            image=self._image, desired_arch=self.arch,
            connection=f"qemu:///{self.connection}")

    def prepare_ssh_key(self, key_type: Optional[str] = None) -> None:
        """ Prepare ssh key for authentication """
        assert self.workdir is not None

        # Use existing key
        if self.key:
            self.debug("Extract public key from the provided private one.")
            command = Command("ssh-keygen", "-f", self.key[0], "-y")
            public_key = self._run_guest_command(command, silent=True).stdout
        # Generate new ssh key pair
        else:
            self.debug('Generating an ssh key.')
            key_name = f"id_{key_type if key_type is not None else 'rsa'}"
            self.key = [self.workdir / key_name]
            command = Command("ssh-keygen", "-f", self.key[0], "-N", "")
            if key_type is not None:
                command += Command("-t", key_type)
            self._run_guest_command(command, silent=True)
            self.verbose('key', self.key[0], 'green')
            with open(self.workdir / f'{key_name}.pub') as pubkey_file:
                public_key = pubkey_file.read()

        # Place public key content into the machine configuration
        self.config.USER_DATA = Template(USER_DATA).safe_substitute(
            user_name=self.user, public_key=public_key)
        self.config.COREOS_DATA = Template(COREOS_DATA).safe_substitute(
            user_name=self.user, public_key=public_key)

    def prepare_config(self) -> None:
        """ Prepare common configuration """
        import_testcloud()

        # Get configuration
        assert testcloud is not None
        self.config = testcloud.config.get_config()

        self.debug(f"testcloud version: {testcloud.__version__}")

        # Make sure download progress is disabled unless in debug mode,
        # so it does not spoil our logging
        self.config.DOWNLOAD_PROGRESS = self.debug_level > 2
        self.config.DOWNLOAD_PROGRESS_VERBOSE = False

        # Configure to tmt's storage directories
        self.config.DATA_DIR = TESTCLOUD_DATA
        self.config.STORE_DIR = TESTCLOUD_IMAGES

    def _combine_hw_memory(self) -> None:
        """ Combine ``hardware`` with ``--memory`` option """

        if not self.hardware:
            self.hardware = tmt.hardware.Hardware.from_spec({})

        if self.memory is None:
            return

        memory_constraint = tmt.hardware.SizeConstraint.from_specification(
            'memory', str(self.memory))

        self.hardware.and_(memory_constraint)

    def _combine_hw_disk_size(self) -> None:
        """ Combine ``hardware`` with ``--disk`` option """

        if not self.hardware:
            self.hardware = tmt.hardware.Hardware.from_spec({})

        if self.disk is None:
            return

        disk_size_constraint = tmt.hardware.SizeConstraint.from_specification(
            'disk[0].size',
            str(self.disk))

        self.hardware.and_(disk_size_constraint)

    def _apply_hw_memory(self, domain: 'DomainConfiguration') -> None:
        """ Apply ``memory`` constraint to given VM domain """

        if not self.hardware or not self.hardware.constraint:
            self.debug(
                'memory',
                f"set to '{DEFAULT_MEMORY}' because of no constraints",
                level=4)

            domain.memory_size = int(DEFAULT_MEMORY.to('kB').magnitude)

            return

        variant = self.hardware.constraint.variant()

        memory_constraints = [
            constraint
            for constraint in variant
            if isinstance(constraint, tmt.hardware.SizeConstraint)
            and constraint.expand_name().name == 'memory']

        if not memory_constraints:
            self.debug(
                'memory',
                f"set to '{DEFAULT_MEMORY}' because of no 'memory' constraints",
                level=4)

            domain.memory_size = int(DEFAULT_MEMORY.to('kB').magnitude)

            return

        for constraint in memory_constraints:
            if constraint.operator not in (
                    tmt.hardware.Operator.EQ,
                    tmt.hardware.Operator.GTE,
                    tmt.hardware.Operator.LTE):
                raise ProvisionError(
                    f"Cannot apply hardware requirement '{constraint}', operator not supported.")

            self.debug(
                'memory',
                f"set to '{constraint.value}' because of '{constraint}'",
                level=4)

            domain.memory_size = int(constraint.value.to('kB').magnitude)

    def _apply_hw_arch(self, domain: 'DomainConfiguration', kvm: bool, legacy_os: bool) -> None:
        if self.arch == "x86_64":
            domain.system_architecture = X86_64ArchitectureConfiguration(
                kvm=kvm,
                uefi=False,  # Configurable
                model="q35" if not legacy_os else "pc")
        elif self.arch == "aarch64":
            domain.system_architecture = AArch64ArchitectureConfiguration(
                kvm=kvm,
                uefi=True,  # Always enabled
                model="virt")
        elif self.arch == "ppc64le":
            domain.system_architecture = Ppc64leArchitectureConfiguration(
                kvm=kvm,
                uefi=False,  # Always disabled
                model="pseries")
        elif self.arch == "s390x":
            domain.system_architecture = S390xArchitectureConfiguration(
                kvm=kvm,
                uefi=False,  # Always disabled
                model="s390-ccw-virtio")
        else:
            raise tmt.utils.ProvisionError("Unknown architecture requested.")

    def start(self) -> None:
        """ Start provisioned guest """
        if self.is_dry_run:
            return
        # Make sure required directories exist
        os.makedirs(TESTCLOUD_DATA, exist_ok=True)
        os.makedirs(TESTCLOUD_IMAGES, exist_ok=True)

        # Prepare config
        self.prepare_config()

        # Kick off image URL with the given image
        self.image_url = self.image

        # If image does not start with http/https/file, consider it a
        # mapping value and try to guess the URL
        if not re.match(r'^(?:https?|file)://.*', self.image_url):
            self.image_url = self._guess_image_url(self.image_url)
            self.debug(f"Guessed image url: '{self.image_url}'", level=3)

        # Initialize and prepare testcloud image
        assert testcloud is not None
        self._image = testcloud.image.Image(self.image_url)
        self.verbose('qcow', self._image.name, 'green')
        if not Path(self._image.local_path).exists():
            self.info('progress', 'downloading...', 'cyan')
        try:
            self._image.prepare()
        except FileNotFoundError as error:
            raise ProvisionError(
                f"Image '{self._image.local_path}' not found.") from error
        except (testcloud.exceptions.TestcloudPermissionsError,
                PermissionError) as error:
            raise ProvisionError(
                f"Failed to prepare the image. Check the '{TESTCLOUD_IMAGES}' "
                f"directory permissions.") from error
        except KeyError as error:
            raise ProvisionError(
                f"Failed to prepare image '{self.image_url}'.") from error

        # Prepare hostname (get rid of possible unwanted characters)
        hostname = re.sub(r"[^a-zA-Z0-9\-]+", "-", self.name.lower()).strip("-")

        # Create instance
        self.instance_name = self._tmt_name()

        # Prepare DomainConfiguration object before Instance object
        self._domain = DomainConfiguration(self.instance_name)

        # Prepare Workarounds object
        self._workarounds = Workarounds(defaults=True)
        for cmd in TESTCLOUD_WORKAROUNDS:
            self._workarounds.add(cmd)

        # Process hardware and find a suitable HW properties
        self._domain.cpu_count = DEFAULT_CPU_COUNT

        self._combine_hw_memory()
        self._combine_hw_disk_size()

        if self.hardware:
            self.verbose(
                'effective hardware',
                self.hardware.to_spec(),
                color='green')

            for line in self.hardware.format_variants():
                self._logger.debug('effective hardware', line, level=4)

        self._apply_hw_memory(self._domain)
        _apply_hw_cpu_processors(self.hardware, self._domain, self._logger)
        _apply_hw_disk_size(self.hardware, self._domain, self._logger)
        _apply_hw_tpm(self.hardware, self._domain, self._logger)

        self.debug('final domain memory', str(self._domain.memory_size))
        self.debug('final domain root disk size', str(self._domain.storage_devices[0].size))

        for i, device in enumerate(self._domain.storage_devices):
            self.debug(f'final domain disk #{i} size', str(device.size))

        # Is this a CoreOS?
        self._domain.coreos = self.is_coreos

        self._apply_hw_arch(self._domain, self.is_kvm, self.is_legacy_os)

        mac_address = testcloud.util.generate_mac_address()
        if f"qemu:///{self.connection}" == "qemu:///system":
            self._domain.network_configuration = SystemNetworkConfiguration(
                mac_address=mac_address)
        elif f"qemu:///{self.connection}" == "qemu:///session":
            device_type = "virtio-net-pci" if not self.is_legacy_os else "e1000"
            with GuestTestcloud._testcloud_lock:
                port = testcloud.util.spawn_instance_port_file(self.instance_name)
            self._domain.network_configuration = UserNetworkConfiguration(
                mac_address=mac_address,
                port=port,
                device_type=device_type)
        else:
            raise tmt.utils.ProvisionError("Only system, or session connection is supported.")

        if not self._domain.coreos:
            seed_disk = RawStorageDevice(self._domain.seed_path)
            self._domain.storage_devices.append(seed_disk)

        self._instance = testcloud.instance.Instance(
            hostname=hostname,
            image=self._image,
            connection=f"qemu:///{self.connection}",
            domain_configuration=self._domain,
            workarounds=self._workarounds)

        self.verbose('name', self.instance_name, 'green')

        # Decide if we want to multiply timeouts when emulating an architecture
        time_coeff = NON_KVM_TIMEOUT_COEF if not self.is_kvm else 1

        # Prepare ssh key
        # TODO: Maybe... some better way to do this?
        if self._domain.coreos:
            self._instance.coreos = True
            # prepare_ssh_key() writes key directly to COREOS_DATA
            self._instance.ssh_path = []
        self.prepare_ssh_key(SSH_KEYGEN_TYPE)

        # Boot the virtual machine
        self.info('progress', 'booting...', 'cyan')
        assert libvirt is not None

        try:
            self._instance.prepare()
            self._instance.spawn_vm()
            self._instance.start(BOOT_TIMEOUT * time_coeff)
        except (testcloud.exceptions.TestcloudInstanceError,
                libvirt.libvirtError) as error:
            raise ProvisionError(
                f'Failed to boot testcloud instance ({error}).')
        self.primary_address = self.topology_address = self._instance.get_ip()
        self.port = int(self._instance.get_instance_port())
        self.verbose('primary address', self.primary_address, 'green')
        self.verbose('topology address', self.topology_address, 'green')
        self.verbose('port', self.port, 'green')
        self._instance.create_ip_file(self.primary_address)

        # Wait a bit until the box is up
        if not self.reconnect(
                timeout=CONNECT_TIMEOUT *
                time_coeff,
                tick=1):
            raise ProvisionError(
                f"Failed to connect in {CONNECT_TIMEOUT * time_coeff}s.")

    def stop(self) -> None:
        """ Stop provisioned guest """
        super().stop()
        # Stop only if the instance successfully booted
        if self._instance and self.primary_address:
            self.debug(f"Stopping testcloud instance '{self.instance_name}'.")
            assert testcloud is not None
            try:
                self._instance.stop()
            except testcloud.exceptions.TestcloudInstanceError as error:
                raise tmt.utils.ProvisionError(
                    f"Failed to stop testcloud instance: {error}")

            self.info('guest', 'stopped', 'green')

    def remove(self) -> None:
        """ Remove the guest (disk cleanup) """
        if self._instance:
            self.debug(f"Removing testcloud instance '{self.instance_name}'.")
            try:
                self._instance.remove(autostop=True)
            except FileNotFoundError as error:
                raise tmt.utils.ProvisionError(
                    f"Failed to remove testcloud instance: {error}")

            self.info('guest', 'removed', 'green')

    def reboot(self,
               hard: bool = False,
               command: Optional[Union[Command, ShellScript]] = None,
               timeout: Optional[int] = None,
               tick: float = tmt.utils.DEFAULT_WAIT_TICK,
               tick_increase: float = tmt.utils.DEFAULT_WAIT_TICK_INCREASE) -> bool:
        """ Reboot the guest, return True if successful """
        # Use custom reboot command if provided
        if command:
            return super().reboot(hard=hard, command=command)
        if not self._instance:
            raise tmt.utils.ProvisionError("No instance initialized.")
        self._instance.reboot(soft=not hard)
        return self.reconnect(timeout=timeout)


@tmt.steps.provides_method('virtual.testcloud')
class ProvisionTestcloud(tmt.steps.provision.ProvisionPlugin[ProvisionTestcloudData]):
    """
    Local virtual machine using ``testcloud`` library.

    Minimal config which uses the latest Fedora image:

    .. code-block:: yaml

        provision:
            how: virtual

    Here's a full config example:

    .. code-block:: yaml

        provision:
            how: virtual
            image: fedora
            user: root
            memory: 2048

    As the image use ``fedora`` for the latest released Fedora compose,
    ``fedora-rawhide`` for the latest Rawhide compose, short aliases such as
    ``fedora-32``, ``f-32`` or ``f32`` for specific release or a full url to
    the qcow2 image for example from https://kojipkgs.fedoraproject.org/compose/.

    Short names are also provided for ``centos``, ``centos-stream``, ``alma``,
    ``rocky``, ``oracle``, ``debian`` and ``ubuntu`` (e.g. ``centos-8`` or ``c8``).

    .. note::

        The non-rpm distros are not fully supported yet in tmt as
        the package installation is performed solely using ``dnf``/``yum``
        and ``rpm``.
        But you should be able the login to the provisioned guest and start
        experimenting. Full support is coming in the future :)

    Supported Fedora CoreOS images are:

    * ``fedora-coreos``
    * ``fedora-coreos-stable``
    * ``fedora-coreos-testing``
    * ``fedora-coreos-next``

    Use the full path for images stored on local disk, for example:

    .. code-block:: shell

        /var/tmp/images/Fedora-Cloud-Base-31-1.9.x86_64.qcow2

    In addition to the qcow2 format, Vagrant boxes can be used as well,
    testcloud will take care of unpacking the image for you.
    """

    _data_class = ProvisionTestcloudData
    _guest_class = GuestTestcloud

    _thread_safe = True

    # Guest instance
    _guest = None

    def go(self, *, logger: Optional[tmt.log.Logger] = None) -> None:
        """ Provision the testcloud instance """
        super().go(logger=logger)

        if self.data.list_local_images:
            self._print_local_images()
            # Clean up the run workdir and exit
            if self.step.plan.my_run:
                self.step.plan.my_run._workdir_cleanup()
            raise SystemExit(0)

        # Give info about provided data
        data = TestcloudGuestData.from_plugin(self)

        # Once plan schema is enforced this won't be necessary
        # click enforces int for cmdline and schema validation
        # will make sure 'int' gets from plan data.
        # Another key is 'port' however that is not exposed to the cli
        for int_key in ["port"]:
            value = getattr(data, int_key)
            if value is not None:
                try:
                    setattr(data, int_key, int(value))
                except ValueError as exc:
                    raise tmt.utils.NormalizationError(
                        f'{self.name}:{int_key}', value, 'an integer') from exc

        data.show(verbose=self.verbosity_level, logger=self._logger)

        if data.hardware and data.hardware.constraint:
            data.hardware.report_support(check=_report_hw_requirement_support, logger=self._logger)

            for line in data.hardware.format_variants():
                self._logger.debug('hardware', line, level=4)

            if data.memory is not None and data.hardware.constraint.uses_constraint(
                    'memory', self._logger):
                self._logger.warning(
                    "Hardware requirement 'memory' is specified in 'hardware' key,"
                    " it will be overruled by 'memory' key.")

            if data.disk is not None and data.hardware.constraint.uses_constraint(
                    'disk.size', self._logger):
                self._logger.warning(
                    "Hardware requirement 'disk.size' is specified in 'hardware' key,"
                    " it will be overruled by 'disk' key.")

        # Create a new GuestTestcloud instance and start it
        self._guest = GuestTestcloud(
            logger=self._logger,
            data=data,
            name=self.name,
            parent=self.step)
        self._guest.start()
        self._guest.setup()

    def guest(self) -> Optional[tmt.Guest]:
        """ Return the provisioned guest """
        return self._guest

    def _print_local_images(self) -> None:
        """ Print images which are already cached """
        self.info("Locally available images")
        for filename in sorted(TESTCLOUD_IMAGES.glob('*.qcow2')):
            self.info(filename.name, shift=1, color='yellow')
            click.echo(f"{TESTCLOUD_IMAGES / filename}")

    @classmethod
    def clean_images(cls, clean: 'tmt.base.Clean', dry: bool) -> bool:
        """ Remove the testcloud images """
        clean.info('testcloud', shift=1, color='green')
        if not TESTCLOUD_IMAGES.exists():
            clean.warn(
                f"Directory '{TESTCLOUD_IMAGES}' does not exist.", shift=2)
            return True
        successful = True
        for image in TESTCLOUD_IMAGES.iterdir():
            if dry:
                clean.verbose(f"Would remove '{image}'.", shift=2)
            else:
                clean.verbose(f"Removing '{image}'.", shift=2)
                try:
                    image.unlink()
                except OSError:
                    clean.fail(f"Failed to remove '{image}'.", shift=2)
                    successful = False
        return successful
