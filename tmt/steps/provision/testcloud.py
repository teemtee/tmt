import collections
import functools
import itertools
import os
import platform
import re
import shutil
import tempfile
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
import tmt.utils.wait
from tmt.container import container, field
from tmt.utils import (
    Command,
    Path,
    ProvisionError,
    ShellScript,
    configure_constant,
    retry_session,
)
from tmt.utils.wait import Deadline, Waiting

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


def import_testcloud(logger: tmt.log.Logger) -> None:
    """
    Import testcloud module only when needed
    """

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
        from tmt.utils.hints import print_hints

        print_hints('provision/virtual.testcloud', logger=logger)

        raise ProvisionError('Could not import testcloud package.') from error

    # Version-aware TPM configuration is added in
    # https://pagure.io/testcloud/c/89f1c024ca829543de7f74f89329158c6dee3d83
    global TPM_CONFIG_ALLOWS_VERSIONS
    TPM_CONFIG_ALLOWS_VERSIONS = hasattr(TPMConfiguration(), 'version')


TESTCLOUD_WORKAROUNDS: list[str] = []  # A list of commands to be executed during guest boot up

# Target filename to store the console log
CONSOLE_LOG_FILE = "console.txt"

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
storage:
  files:
    - path: /etc/ssh/sshd_config.d/20-enable-root-login.conf
      mode: 0644
      contents:
        inline: |
          # CoreOS disables root SSH login by default.
          # Enable it.
          # This file must sort before 40-rhcos-defaults.conf.
          PermitRootLogin yes
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
NON_KVM_TIMEOUT_COEF = 10  # times

# SSH key type, set None for ssh-keygen default one
SSH_KEYGEN_TYPE = "ecdsa"

DEFAULT_USER = 'root'
DEFAULT_CPU_COUNT = 2
DEFAULT_MEMORY: 'Size' = tmt.hardware.UNITS('2048 MB')
DEFAULT_DISK: 'Size' = tmt.hardware.UNITS('40 GB')
DEFAULT_IMAGE = 'fedora'
DEFAULT_CONNECTION = 'session'
DEFAULT_ARCH = platform.machine()
#: Default number of attempts to stop a VM.
#:
#: .. note::
#:
#:    The value :py:mod:`testcloud` starts with is ``3``, and we already
#:    observed some VMs with bootc involved to not shut down in time.
#:    Therefore starting with increased default on our side.
DEFAULT_STOP_RETRIES = 10
#: Default time, in seconds, to wait between attempts to stop a VM.
DEFAULT_STOP_RETRY_DELAY = 1

# Version-aware TPM configuration is added in
# https://pagure.io/testcloud/c/89f1c024ca829543de7f74f89329158c6dee3d83
#: If set, ``testcloud`` TPM configuration accepts TPM version as a parameter.
TPM_CONFIG_ALLOWS_VERSIONS: bool = False

#: List of operators supported for ``tpm.version`` HW requirement.
TPM_VERSION_ALLOWED_OPERATORS: tuple[tmt.hardware.Operator, ...] = (
    tmt.hardware.Operator.EQ,
    tmt.hardware.Operator.GTE,
    tmt.hardware.Operator.LTE,
)

#: TPM versions supported by the plugin. The key is :py:const:`TPM_CONFIG_ALLOWS_VERSIONS`.
TPM_VERSION_SUPPORTED_VERSIONS = {
    True: ['2.0', '2', '1.2'],
    # This is the default version used by testcloud before version became
    # an input parameter of TPM configuration.
    False: ['2.0', '2'],
}


def normalize_memory_size(
    key_address: str,
    value: Any,
    logger: tmt.log.Logger,
) -> Optional['Size']:
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


def _report_hw_requirement_support(constraint: tmt.hardware.Constraint) -> bool:
    components = constraint.expand_name()

    if components.name == 'memory' and constraint.operator in (
        tmt.hardware.Operator.EQ,
        tmt.hardware.Operator.GTE,
        tmt.hardware.Operator.LTE,
    ):
        return True

    if (
        components.name == 'cpu'
        and components.child_name == 'processors'
        and constraint.operator
        in (
            tmt.hardware.Operator.EQ,
            tmt.hardware.Operator.LTE,
            tmt.hardware.Operator.GTE,
            tmt.hardware.Operator.NEQ,
            tmt.hardware.Operator.LT,
            tmt.hardware.Operator.GT,
        )
    ):
        return True

    if (
        components.name == 'disk'
        and components.child_name == 'size'
        and constraint.operator
        in (tmt.hardware.Operator.EQ, tmt.hardware.Operator.GTE, tmt.hardware.Operator.LTE)
    ):
        return True

    if (
        components.name == 'tpm'
        and components.child_name == 'version'
        and constraint.value in TPM_VERSION_SUPPORTED_VERSIONS[TPM_CONFIG_ALLOWS_VERSIONS]
        and constraint.operator in TPM_VERSION_ALLOWED_OPERATORS
    ):
        return True

    return False


@container
class TestcloudGuestData(tmt.steps.provision.GuestSshData):
    # Override parent class with our defaults
    user: str = field(
        default=DEFAULT_USER,
        option=('-u', '--user'),
        metavar='USERNAME',
        help='Username to use for all guest operations.',
    )

    image: str = field(
        default=DEFAULT_IMAGE,
        option=('-i', '--image'),
        metavar='IMAGE',
        help="""
             Select image to be used. Provide a short name, full path to a local file
             or a complete url.
             """,
    )
    memory: Optional['Size'] = field(
        default=cast(Optional['Size'], None),
        option=('-m', '--memory'),
        metavar='SIZE',
        help='Set available memory in MB, 2048 MB by default.',
        normalize=normalize_memory_size,
        serialize=lambda value: str(value) if value is not None else None,
        unserialize=lambda serialized: tmt.hardware.UNITS(serialized)
        if serialized is not None
        else None,
    )
    disk: Optional['Size'] = field(
        default=cast(Optional['Size'], None),
        option=('-D', '--disk'),
        metavar='SIZE',
        help='Specify disk size in GB, 10 GB by default.',
        normalize=normalize_disk_size,
        serialize=lambda value: str(value) if value is not None else None,
        unserialize=lambda serialized: tmt.hardware.UNITS(serialized)
        if serialized is not None
        else None,
    )
    connection: str = field(
        default=DEFAULT_CONNECTION,
        option=('-c', '--connection'),
        choices=['session', 'system'],
        help="What session type to use, 'session' by default.",
    )
    arch: str = field(
        default=DEFAULT_ARCH,
        option=('-a', '--arch'),
        choices=['x86_64', 'aarch64', 's390x', 'ppc64le'],
        help="What architecture to virtualize, host arch by default.",
    )

    list_local_images: bool = field(
        default=False,
        option='--list-local-images',
        is_flag=True,
        help="List locally available images.",
    )

    image_url: Optional[str] = field(
        default=None,
        internal=True,
    )
    instance_name: Optional[str] = field(
        default=None,
        internal=True,
    )

    stop_retries: int = field(
        default=DEFAULT_STOP_RETRIES,
        metavar='N',
        option='--stop-retries',
        help="""
             Number of attempts to stop a VM.
             """,
    )

    stop_retry_delay: int = field(
        default=DEFAULT_STOP_RETRY_DELAY,
        metavar='SECONDS',
        option='--stop-retry-delay',
        help="""
             Time to wait between attempts to stop a VM.
             """,
    )

    # TODO: custom handling for two fields - when the formatting moves into
    # field(), this should not be necessary.
    def show(
        self,
        *,
        keys: Optional[list[str]] = None,
        verbose: int = 0,
        logger: tmt.log.Logger,
    ) -> None:
        keys = keys or list(self.keys())
        super_keys = [key for key in keys if key not in ('memory', 'disk')]

        super().show(keys=super_keys, verbose=verbose, logger=logger)

        # TODO: find formatting that would show "MB" instead of "megabyte"
        # https://github.com/teemtee/tmt/issues/2410
        logger.info('memory', f'{(self.memory or DEFAULT_MEMORY).to("MB")}', 'green')
        logger.info('disk', f'{(self.disk or DEFAULT_DISK).to("GB")}', 'green')


@container
class ProvisionTestcloudData(TestcloudGuestData, tmt.steps.provision.ProvisionStepData):
    pass


def _apply_hw_tpm(
    hardware: Optional[tmt.hardware.Hardware],
    domain: 'DomainConfiguration',
    logger: tmt.log.Logger,
) -> None:
    """
    Apply ``tpm`` constraint to given VM domain
    """

    domain.tpm_configuration = None

    if not hardware or not hardware.constraint:
        logger.debug('tpm.version', "not included because of no constraints", level=4)

        return

    variant = hardware.constraint.variant()

    tpm_constraints = [
        constraint
        for constraint in variant
        if isinstance(constraint, tmt.hardware.TextConstraint)
        and constraint.expand_name().name == 'tpm'
        and constraint.expand_name().child_name == 'version'
    ]

    if not tpm_constraints:
        logger.debug(
            'tpm.version', "not included because of no 'tpm.version' constraints", level=4
        )

        return

    for constraint in tpm_constraints:
        if constraint.operator not in TPM_VERSION_ALLOWED_OPERATORS:
            logger.warning(
                f"Cannot apply hardware requirement '{constraint}', operator not supported."
            )
            return

        if constraint.value not in TPM_VERSION_SUPPORTED_VERSIONS[TPM_CONFIG_ALLOWS_VERSIONS]:
            logger.warning(
                f"Cannot apply hardware requirement '{constraint}', TPM version not supported."
            )
            return

        logger.debug(
            'tpm.version', f"set to '{constraint.value}' because of '{constraint}'", level=4
        )

        if TPM_CONFIG_ALLOWS_VERSIONS:
            domain.tpm_configuration = TPMConfiguration(version=constraint.value)

        else:
            domain.tpm_configuration = TPMConfiguration()


def _apply_hw_disk_size(
    hardware: Optional[tmt.hardware.Hardware],
    domain: 'DomainConfiguration',
    logger: tmt.log.Logger,
) -> None:
    """
    Apply ``disk`` constraint to given VM domain
    """

    final_size: Size = DEFAULT_DISK

    def _generate_disk_filepaths() -> Iterator[Path]:
        """
        Generate paths to use for files representing VM storage
        """

        # Start with the path already decided by testcloud...
        yield Path(domain.local_disk)

        # ... and use it as a basis for remaining paths.
        for i in itertools.count(1, 1):
            yield Path(f'{domain.local_disk}.{i}')

    disk_filepath_generator = _generate_disk_filepaths()

    if not hardware or not hardware.constraint:
        logger.debug('disk[0].size', f"set to '{final_size}' because of no constraints", level=4)

        domain.storage_devices = [
            QCow2StorageDevice(
                str(next(disk_filepath_generator)), int(final_size.to('GB').magnitude)
            )
        ]

        return

    variant = hardware.constraint.variant()

    # Collect all `disk.size` constraints, ignore the rest.
    disk_size_constraints = [
        constraint
        for constraint in variant
        if isinstance(constraint, tmt.hardware.SizeConstraint)
        and constraint.expand_name().name == 'disk'
        and constraint.expand_name().child_name == 'size'
    ]

    if not disk_size_constraints:
        logger.debug(
            'disk[0].size', f"set to '{final_size}' because of no 'disk.size' constraints", level=4
        )

        domain.storage_devices = [
            QCow2StorageDevice(
                str(next(disk_filepath_generator)), int(final_size.to('GB').magnitude)
            )
        ]

        return

    # Now sort them into groups by their `peer_index`, i.e. `disk[0]`,
    # `disk[1]` and so on.
    by_peer_index: dict[int, list[tmt.hardware.SizeConstraint]] = collections.defaultdict(list)

    for constraint in disk_size_constraints:
        if constraint.operator not in (
            tmt.hardware.Operator.EQ,
            tmt.hardware.Operator.GTE,
            tmt.hardware.Operator.LTE,
        ):
            raise ProvisionError(
                f"Cannot apply hardware requirement '{constraint}', operator not supported."
            )

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
                level=4,
            )

            final_size = constraint.value

        domain.storage_devices.append(
            QCow2StorageDevice(
                str(next(disk_filepath_generator)), int(final_size.to('GB').magnitude)
            )
        )


def _apply_hw_cpu_processors(
    hardware: Optional[tmt.hardware.Hardware],
    domain: 'DomainConfiguration',
    logger: tmt.log.Logger,
) -> None:
    """
    Apply ``cpu.processors`` constraint to given VM domain
    """

    domain.cpu_count = DEFAULT_CPU_COUNT

    if not hardware or not hardware.constraint:
        logger.debug('cpu.processors', "not included because of no constraints", level=4)

        return

    variant = hardware.constraint.variant()

    cpu_processors_constraints = [
        constraint
        for constraint in variant
        if isinstance(constraint, tmt.hardware.IntegerConstraint)
        and constraint.expand_name().name == 'cpu'
        and constraint.expand_name().child_name == 'processors'
    ]

    if not cpu_processors_constraints:
        logger.debug(
            'cpu.processors', "not included because of no 'cpu.processors' constraints", level=4
        )

        return

    for constraint in cpu_processors_constraints:
        if constraint.operator in (
            tmt.hardware.Operator.EQ,
            tmt.hardware.Operator.LTE,
            tmt.hardware.Operator.GTE,
        ):
            logger.debug(
                'cpu.processors', f"set to '{constraint.value}' because of '{constraint}'", level=4
            )

            domain.cpu_count = constraint.value

        elif (
            constraint.operator is tmt.hardware.Operator.NEQ
            and domain.cpu_count != constraint.value
        ):
            logger.debug(
                'cpu.processors',
                f"kept at '{constraint.value}' because of '{constraint}'",
                level=4,
            )

        elif constraint.operator is tmt.hardware.Operator.LT:
            logger.debug(
                'cpu.processors',
                f"set to '{constraint.value - 1}' because of '{constraint}'",
                level=4,
            )

            domain.cpu_count = constraint.value - 1

        elif constraint.operator is tmt.hardware.Operator.GT:
            logger.debug(
                'cpu.processors',
                f"set to '{constraint.value + 1}' because of '{constraint}'",
                level=4,
            )

            domain.cpu_count = constraint.value + 1

        else:
            raise ProvisionError(
                f"Cannot apply hardware requirement '{constraint}', operator not supported."
            )


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

    stop_retries: int
    stop_retry_delay: int

    # Not to be saved, recreated from image_url/instance_name/... every
    # time guest is instantiated.
    # FIXME: ignore[name-defined]: https://github.com/teemtee/tmt/issues/1616
    _image: Optional['testcloud.image.Image'] = None  # type: ignore[name-defined]
    _instance: Optional['testcloud.instance.Instance'] = None  # type: ignore[name-defined]
    _domain: Optional[  # type: ignore[name-defined]
        'testcloud.domain_configuration.DomainConfiguration'
    ] = None

    #: The lock protects calls into the testcloud library. We suspect it might
    #: be unprepared for multi-threaded use. After the dust settles, we may
    #: remove the lock.
    _testcloud_lock = threading.Lock()

    @functools.cached_property
    def testcloud_data_dirpath(self) -> Path:
        return self.workdir_root / 'testcloud'

    @functools.cached_property
    def testcloud_image_dirpath(self) -> Path:
        return self.testcloud_data_dirpath / 'images'

    @property
    def is_ready(self) -> bool:
        if self._instance is None:
            return False

        assert testcloud is not None
        assert libvirt is not None
        try:
            state = testcloud.instance._find_domain(self._instance.name, self._instance.connection)
            # Note the type of variable 'state' is 'Any'. Hence, we don't use:
            #     return state == 'running'
            # to avoid error from type checking.
            return bool(state == "running")
        except libvirt.libvirtError:
            return False

    @functools.cached_property
    def is_kvm(self) -> bool:
        # Is the combination of host-requested architecture kvm capable?
        return bool(self.arch == platform.machine() and Path('/dev/kvm').exists())

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
        """
        Get url, retry when fails, return response
        """

        def try_get_url() -> requests.Response:
            try:
                with retry_session() as session:
                    response = session.get(url)

                if response.ok:
                    return response

            except requests.RequestException:
                pass
            finally:
                raise tmt.utils.wait.WaitingIncompleteError

        try:
            return Waiting(Deadline.from_seconds(CONNECT_TIMEOUT), tick=1).wait(
                try_get_url, self._logger
            )

        except tmt.utils.wait.WaitingTimedOutError:
            raise ProvisionError(f'Failed to {message} in {CONNECT_TIMEOUT}s.')

    def _guess_image_url(self, name: str) -> str:
        """
        Guess image url for given name
        """

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
        """
        Wake up the guest
        """

        self.debug(f"Waking up testcloud instance '{self.instance_name}'.", level=2, shift=0)
        self.prepare_config()
        assert testcloud is not None
        self._image = testcloud.image.Image(self.image_url)
        if self.instance_name is None:
            raise ProvisionError(f"The instance name '{self.instance_name}' is invalid.")

        self._domain = DomainConfiguration(self.instance_name)
        self._apply_hw_arch(self._domain, self.is_kvm, self.is_legacy_os)

        # Is this a CoreOS?
        self._domain.coreos = self.is_coreos

        self._instance = testcloud.instance.Instance(
            domain_configuration=self._domain,
            image=self._image,
            desired_arch=self.arch,
            connection=f"qemu:///{self.connection}",
        )

    def prepare_ssh_key(self, key_type: Optional[str] = None) -> str:
        """
        Prepare ssh key for authentication
        """

        assert self.workdir is not None

        # Use existing key
        if self.key:
            self.debug("Extract public key from the provided private one.")
            command = Command("ssh-keygen", "-f", self.key[0], "-y")
            public_key = self._run_guest_command(command, silent=True).stdout
            assert public_key is not None
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
            public_key = (self.workdir / f'{key_name}.pub').read_text()

        return public_key

    def prepare_config(self) -> None:
        """
        Prepare common configuration
        """

        import_testcloud(self._logger)

        # Get configuration
        assert testcloud is not None
        self.config = testcloud.config.get_config()

        self.debug(f"testcloud version: {testcloud.__version__}")

        # Make sure download progress is disabled unless in debug mode,
        # so it does not spoil our logging
        self.config.DOWNLOAD_PROGRESS = self.debug_level > 2
        self.config.DOWNLOAD_PROGRESS_VERBOSE = False

        # We can't assign a not-exists path to STORE_DIR,
        # so we should make sure required directories exist
        os.makedirs(self.testcloud_data_dirpath, exist_ok=True)
        os.makedirs(self.testcloud_image_dirpath, exist_ok=True)

        # Configure to tmt's storage directories
        self.config.DATA_DIR = self.testcloud_data_dirpath
        self.config.STORE_DIR = self.testcloud_image_dirpath

        self.config.STOP_RETRIES = self.stop_retries
        self.config.STOP_RETRY_WAIT = self.stop_retry_delay

    def _combine_hw_memory(self) -> None:
        """
        Combine ``hardware`` with ``--memory`` option
        """

        if not self.hardware:
            self.hardware = tmt.hardware.Hardware.from_spec({})

        if self.memory is None:
            return

        memory_constraint = tmt.hardware.SizeConstraint.from_specification(
            'memory', str(self.memory)
        )

        self.hardware.and_(memory_constraint)

    def _combine_hw_disk_size(self) -> None:
        """
        Combine ``hardware`` with ``--disk`` option
        """

        if not self.hardware:
            self.hardware = tmt.hardware.Hardware.from_spec({})

        if self.disk is None:
            return

        disk_size_constraint = tmt.hardware.SizeConstraint.from_specification(
            'disk[0].size', str(self.disk)
        )

        self.hardware.and_(disk_size_constraint)

    def _apply_hw_memory(self, domain: 'DomainConfiguration') -> None:
        """
        Apply ``memory`` constraint to given VM domain
        """

        if not self.hardware or not self.hardware.constraint:
            self.debug('memory', f"set to '{DEFAULT_MEMORY}' because of no constraints", level=4)

            domain.memory_size = int(DEFAULT_MEMORY.to('kB').magnitude)

            return

        variant = self.hardware.constraint.variant()

        memory_constraints = [
            constraint
            for constraint in variant
            if isinstance(constraint, tmt.hardware.SizeConstraint)
            and constraint.expand_name().name == 'memory'
        ]

        if not memory_constraints:
            self.debug(
                'memory', f"set to '{DEFAULT_MEMORY}' because of no 'memory' constraints", level=4
            )

            domain.memory_size = int(DEFAULT_MEMORY.to('kB').magnitude)

            return

        for constraint in memory_constraints:
            if constraint.operator not in (
                tmt.hardware.Operator.EQ,
                tmt.hardware.Operator.GTE,
                tmt.hardware.Operator.LTE,
            ):
                raise ProvisionError(
                    f"Cannot apply hardware requirement '{constraint}', operator not supported."
                )

            self.debug('memory', f"set to '{constraint.value}' because of '{constraint}'", level=4)

            domain.memory_size = int(constraint.value.to('kB').magnitude)

    def _apply_hw_arch(self, domain: 'DomainConfiguration', kvm: bool, legacy_os: bool) -> None:
        if self.arch == "x86_64":
            domain.system_architecture = X86_64ArchitectureConfiguration(
                kvm=kvm,
                uefi=False,  # Configurable
                model="q35" if not legacy_os else "pc",
            )
        elif self.arch == "aarch64":
            domain.system_architecture = AArch64ArchitectureConfiguration(
                kvm=kvm,
                uefi=True,  # Always enabled
                model="virt",
            )
        elif self.arch == "ppc64le":
            domain.system_architecture = Ppc64leArchitectureConfiguration(
                kvm=kvm,
                uefi=False,  # Always disabled
                model="pseries",
            )
        elif self.arch == "s390x":
            domain.system_architecture = S390xArchitectureConfiguration(
                kvm=kvm,
                uefi=False,  # Always disabled
                model="s390-ccw-virtio",
            )
        else:
            raise tmt.utils.ProvisionError("Unknown architecture requested.")

    def start(self) -> None:
        """
        Start provisioned guest
        """

        if self.is_dry_run:
            return

        # Prepare the console log
        assert self.logdir is not None  # Narrow type
        console_log = ConsoleLog(
            name=CONSOLE_LOG_FILE,
            testcloud_symlink_path=self.logdir / CONSOLE_LOG_FILE,
            guest=self,
        )
        console_log.prepare(logger=self._logger)
        self.guest_logs.append(console_log)

        # Prepare config
        self.prepare_config()
        self.config.CONSOLE_LOG_DIR = console_log.exchange_directory

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
            raise ProvisionError(f"Image '{self._image.local_path}' not found.") from error
        except (testcloud.exceptions.TestcloudPermissionsError, PermissionError) as error:
            raise ProvisionError(
                f"Failed to prepare the image. Check the '{self.testcloud_image_dirpath}' "
                f"directory permissions."
            ) from error
        except KeyError as error:
            raise ProvisionError(f"Failed to prepare image '{self.image_url}'.") from error

        # Prepare hostname (get rid of possible unwanted characters)
        hostname = re.sub(r"[^a-zA-Z0-9\-]+", "-", self.name.lower()).strip("-")

        # Create instance
        self.instance_name = self._tmt_name()

        # Prepare DomainConfiguration object before Instance object
        self._domain = DomainConfiguration(self.instance_name)
        self._domain.console_log_file = console_log.testcloud_symlink_path

        # Prepare Workarounds object
        self._workarounds = Workarounds(defaults=True)
        for cmd in TESTCLOUD_WORKAROUNDS:
            self._workarounds.add(cmd)

        # Process hardware and find a suitable HW properties
        self._domain.cpu_count = DEFAULT_CPU_COUNT

        self._combine_hw_memory()
        self._combine_hw_disk_size()

        if self.hardware:
            self.verbose('effective hardware', self.hardware.to_spec(), color='green')

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
                mac_address=mac_address
            )
        elif f"qemu:///{self.connection}" == "qemu:///session":
            device_type = "virtio-net-pci" if not self.is_legacy_os else "e1000"
            with GuestTestcloud._testcloud_lock:
                port = testcloud.util.spawn_instance_port_file(self.instance_name)
            self._domain.network_configuration = UserNetworkConfiguration(
                mac_address=mac_address, port=port, device_type=device_type
            )
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
            workarounds=self._workarounds,
        )

        self.verbose('name', self.instance_name, 'green')

        # Decide if we want to multiply timeouts when emulating an architecture
        time_coeff = NON_KVM_TIMEOUT_COEF if not self.is_kvm else 1

        # Prepare ssh key
        # TODO: Maybe... some better way to do this?
        public_key = self.prepare_ssh_key(SSH_KEYGEN_TYPE)
        if self._domain.coreos:
            self._instance.coreos = True
            # prepare_ssh_key() writes key directly to COREOS_DATA
            self._instance.ssh_path = []
            data_tpl = Template(COREOS_DATA).safe_substitute(
                user_name=self.user, public_key=public_key
            )
        else:
            data_tpl = Template(USER_DATA).safe_substitute(
                user_name=self.user, public_key=public_key
            )

        # Boot the virtual machine
        self.info('progress', 'booting...', 'cyan')
        self.verbose("console", console_log.testcloud_symlink_path, level=2, color="cyan")
        assert libvirt is not None

        try:
            self._instance.prepare(data_tpl=data_tpl)
            self._instance.spawn_vm()
            self._instance.start(BOOT_TIMEOUT * time_coeff)
        except (testcloud.exceptions.TestcloudInstanceError, libvirt.libvirtError) as error:
            raise ProvisionError(f'Failed to boot testcloud instance ({error}).')
        self.primary_address = self.topology_address = self._instance.get_ip()
        self.port = int(self._instance.get_instance_port())
        self.verbose('primary address', self.primary_address, 'green')
        self.verbose('topology address', self.topology_address, 'green')
        self.verbose('port', self.port, 'green')
        self._instance.create_ip_file(self.primary_address)

        # Wait a bit until the box is up
        if not self.reconnect(
            Waiting(Deadline.from_seconds(CONNECT_TIMEOUT * time_coeff), tick=1)
        ):
            raise ProvisionError(f"Failed to connect in {CONNECT_TIMEOUT * time_coeff}s.")

    def stop(self) -> None:
        """
        Stop provisioned guest
        """

        super().stop()
        # Stop only if the instance successfully booted
        if self._instance and self.primary_address:
            self.debug(f"Stopping testcloud instance '{self.instance_name}'.")
            assert testcloud is not None
            try:
                self._instance.stop()
            except testcloud.exceptions.TestcloudInstanceError as error:
                raise tmt.utils.ProvisionError(f"Failed to stop testcloud instance: {error}")

            self.info('guest', 'stopped', 'green')

    def remove(self) -> None:
        """
        Remove the guest (disk cleanup)
        """

        if self._instance:
            self.debug(f"Removing testcloud instance '{self.instance_name}'.")
            try:
                self._instance.remove(autostop=True)
            except FileNotFoundError as error:
                raise tmt.utils.ProvisionError(f"Failed to remove testcloud instance: {error}")

            self.info('guest', 'removed', 'green')

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

        :param hard: if set, force the reboot. This may result in a loss
            of data. The default of ``False`` will attempt a graceful
            reboot.
        :param command: a command to run on the guest to trigger the
            reboot. If ``hard`` is also set, ``command`` is ignored.
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
            if self._instance is None:
                raise tmt.utils.ProvisionError("No instance initialized.")

            self.debug("Hard reboot using the testcloud API.")

            # ignore[union-attr]: mypy still considers `self._instance` as possibly
            # being `None`, missing the explicit check above.
            return self.perform_reboot(
                lambda: self._instance.reboot(soft=False),  # type: ignore[union-attr]
                waiting,
                fetch_boot_time=False,
            )

        if command:
            return super().reboot(
                hard=False,
                command=command,
                waiting=waiting,
            )

        if self._instance is None:
            raise tmt.utils.ProvisionError("No instance initialized.")

        # ignore[union-attr]: mypy still considers `self._instance` as possibly
        # being `None`, missing the explicit check above.
        return self.perform_reboot(
            lambda: self._instance.reboot(soft=True),  # type: ignore[union-attr]
            waiting,
        )


@tmt.steps.provides_method(
    'virtual.testcloud',
    installation_hint="""
        Make sure ``testcloud`` and ``libvirt`` packages are installed and configured, they are
        required for VM-backed guests provided by ``provision/virtual.testcloud`` plugin.

        * Users who installed tmt from system repositories should install ``tmt+provision-virtual``
          package.
        * Users who installed tmt from PyPI should also install ``tmt+provision-virtual`` package,
          as it will install required system dependencies. After doing so, they should install
          ``tmt[provision-virtual]`` extra.
    """,
)
class ProvisionTestcloud(tmt.steps.provision.ProvisionPlugin[ProvisionTestcloudData]):
    """
    Local virtual machine using ``testcloud`` library.
    Testcloud takes care of downloading an image and
    making necessary changes to it for optimal experience
    (such as disabling ``UseDNS`` and ``GSSAPI`` for SSH).

    Minimal config which uses the latest Fedora image:

    .. code-block:: yaml

        provision:
            how: virtual

    Here's a full config example:

    .. code-block:: yaml

        # Provision a virtual machine from a specific QCOW2 file,
        # using specific memory and disk settings, using the fedora user,
        # and using sudo to run scripts.
        provision:
            how: virtual
            image: https://mirror.vpsnet.com/fedora/linux/releases/41/Cloud/x86_64/images/Fedora-Cloud-Base-Generic-41-1.4.x86_64.qcow2
            user: fedora
            become: true
            # in MB
            memory: 2048
            # in GB
            disk: 30

    Images
    ^^^^^^

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

    Reboot
    ^^^^^^

    To trigger hard reboot of a guest, plugin uses testcloud API. It is
    also used to trigger soft reboot unless a custom reboot command was
    specified via ``tmt-reboot -c ...``.

    Console
    ^^^^^^^

    The full console log is available, after the guest is booted, in the
    ``logs`` directory under the provision step workdir, for example:
    ``plan/provision/client/logs/console.txt``. Enable verbose mode
    using ``-vv`` to get the full path printed to the terminal for easy
    investigation.

    """

    _data_class = ProvisionTestcloudData
    _guest_class = GuestTestcloud

    _thread_safe = True

    # Guest instance
    _guest = None

    def go(self, *, logger: Optional[tmt.log.Logger] = None) -> None:
        """
        Provision the testcloud instance
        """

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
                        f'{self.name}:{int_key}', value, 'an integer'
                    ) from exc

        data.show(verbose=self.verbosity_level, logger=self._logger)

        if data.hardware and data.hardware.constraint:
            data.hardware.report_support(check=_report_hw_requirement_support, logger=self._logger)

            for line in data.hardware.format_variants():
                self._logger.debug('hardware', line, level=4)

            if data.memory is not None and data.hardware.constraint.uses_constraint(
                'memory', self._logger
            ):
                self._logger.warning(
                    "Hardware requirement 'memory' is specified in 'hardware' key,"
                    " it will be overruled by 'memory' key."
                )

            if data.disk is not None and data.hardware.constraint.uses_constraint(
                'disk.size', self._logger
            ):
                self._logger.warning(
                    "Hardware requirement 'disk.size' is specified in 'hardware' key,"
                    " it will be overruled by 'disk' key."
                )

        # Create a new GuestTestcloud instance and start it
        self._guest = GuestTestcloud(
            logger=self._logger,
            data=data,
            name=self.name,
            parent=self.step,
        )
        self._guest.start()
        self._guest.setup()

    def _print_local_images(self) -> None:
        """
        Print images which are already cached
        """

        store_dir = self.workdir_root / 'testcloud/images'
        self.info("Locally available images")
        for filename in sorted(store_dir.glob('*.qcow2')):
            self.info(filename.name, shift=1, color='yellow')
            click.echo(f"{store_dir / filename}")

    @classmethod
    def clean_images(cls, clean: 'tmt.base.Clean', dry: bool, workdir_root: Path) -> bool:
        """
        Remove the testcloud images
        """

        testcloud_images = workdir_root / 'testcloud/images'
        clean.info('testcloud', shift=1, color='green')
        if not testcloud_images.exists():
            clean.warn(f"Directory '{testcloud_images}' does not exist.", shift=2)
            return True
        successful = True
        for image in testcloud_images.iterdir():
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


@container
class ConsoleLog(tmt.steps.provision.GuestLog):
    # Path where testcloud will create the symlink to the console log
    testcloud_symlink_path: Path

    # Temporary directory for storing the console log content
    exchange_directory: Optional[Path] = None

    def prepare(self, logger: tmt.log.Logger) -> None:
        """
        Prepare temporary directory for the console log.

        Special directory is needed for console logs with the right
        selinux context so that virtlogd is able to write there.
        """

        self.exchange_directory = Path(tempfile.mkdtemp(prefix="testcloud-"))
        logger.debug(f"Created console log directory '{self.exchange_directory}'.", level=3)

        self.exchange_directory.chmod(0o755)
        self.guest._run_guest_command(
            Command("chcon", "--type", "virt_log_t", self.exchange_directory), silent=True
        )

    def cleanup(self, logger: tmt.log.Logger) -> None:
        """
        Remove the temporary directory.
        """

        if self.exchange_directory is None:
            return

        try:
            logger.debug(f"Remove console log directory '{self.exchange_directory}'.", level=3)
            shutil.rmtree(self.exchange_directory)
            self.exchange_directory = None

        except OSError as error:
            logger.warning(
                f"Failed to remove console log directory '{self.exchange_directory}': {error}"
            )

    def fetch(self, logger: tmt.log.Logger) -> Optional[str]:
        """
        Read the content of the symlink target prepared by testcloud.
        """

        text = None

        try:
            logger.debug(
                f"Read the console log content from '{self.testcloud_symlink_path}'.", level=3
            )
            text = self.testcloud_symlink_path.read_text(errors="ignore")

        except OSError as error:
            logger.warning(f"Failed to read the console log: {error}")

        self.testcloud_symlink_path.unlink()
        self.cleanup(logger)

        return text
