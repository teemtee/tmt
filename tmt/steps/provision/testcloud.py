# coding: utf-8

import dataclasses
import datetime
import os
import platform
import re
import time
import types
from typing import TYPE_CHECKING, Any, List, Optional, Union

import click
import requests

import tmt
import tmt.steps
import tmt.steps.provision
import tmt.utils
from tmt.utils import (
    WORKDIR_ROOT,
    Command,
    Path,
    ProvisionError,
    ShellScript,
    field,
    retry_session,
    )

if TYPE_CHECKING:
    import tmt.base


libvirt: Optional[types.ModuleType] = None
testcloud: Optional[types.ModuleType] = None

# To silence mypy
DomainConfiguration: Any
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
    except ImportError as error:
        raise ProvisionError(
            "Install 'tmt+provision-virtual' to provision using this method.") from error


# Testcloud cache to our tmt's workdir root
TESTCLOUD_DATA = (
    Path(os.environ['TMT_WORKDIR_ROOT']) if os.getenv('TMT_WORKDIR_ROOT') else WORKDIR_ROOT
    ) / 'testcloud'
TESTCLOUD_IMAGES = TESTCLOUD_DATA / 'images'

# Userdata for cloud-init
USER_DATA = """#cloud-config
chpasswd:
  list: |
    {user_name}:%s
  expire: false
users:
  - default
  - name: {user_name}
ssh_authorized_keys:
  - {public_key}
ssh_pwauth: true
disable_root: false
runcmd:
  - sed -i -e '/^.*PermitRootLogin/s/^.*$/PermitRootLogin yes/'
    -e '/^.*UseDNS/s/^.*$/UseDNS no/'
    -e '/^.*GSSAPIAuthentication/s/^.*$/GSSAPIAuthentication no/'
    /etc/ssh/sshd_config
  - systemctl reload sshd
  - [sh, -c, 'if [ ! -f /etc/systemd/network/20-tc-usernet.network ] &&
  systemctl status systemd-networkd | grep -q "enabled;\\svendor\\spreset:\\senabled";
  then mkdir -p /etc/systemd/network/ &&
  echo "[Match]" >> /etc/systemd/network/20-tc-usernet.network &&
  echo "Name=en*" >> /etc/systemd/network/20-tc-usernet.network &&
  echo "[Network]" >> /etc/systemd/network/20-tc-usernet.network &&
  echo "DHCP=yes" >> /etc/systemd/network/20-tc-usernet.network; fi']
  - [sh, -c, 'if systemctl status systemd-networkd |
  grep -q "enabled;\\svendor\\spreset:\\senabled"; then
  systemctl restart systemd-networkd; fi']
  - [sh, -c, 'if cat /etc/os-release |
  grep -q platform:el8; then systemctl restart sshd; fi']
  - [sh, -c, 'dhclient || :']
"""

COREOS_DATA = """variant: fcos
version: 1.4.0
passwd:
  users:
    - name: {user_name}
      ssh_authorized_keys:
        - {public_key}
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
DEFAULT_BOOT_TIMEOUT = 120     # seconds
DEFAULT_CONNECT_TIMEOUT = 60   # seconds
NON_KVM_ADDITIONAL_WAIT = 20   # seconds
NON_KVM_TIMEOUT_COEF = 10      # times

# SSH key type, set None for ssh-keygen default one
SSH_KEYGEN_TYPE = "ecdsa"

DEFAULT_USER = 'root'
DEFAULT_MEMORY = 2048          # MB
DEFAULT_DISK = 40              # GB (maximum size allowed)
DEFAULT_IMAGE = 'fedora'
DEFAULT_CONNECTION = 'session'
DEFAULT_ARCH = platform.machine()


@dataclasses.dataclass
class TestcloudGuestData(tmt.steps.provision.GuestSshData):
    # Override parent class with our defaults
    user: Optional[str] = field(
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
    memory: int = field(
        default=DEFAULT_MEMORY,
        option=('-m', '--memory'),
        metavar='SIZE',
        help='Set available memory in MB, 2048 MB by default.',
        normalize=tmt.utils.normalize_storage_size)
    disk: int = field(
        default=DEFAULT_DISK,
        option=('-D', '--disk'),
        metavar='SIZE',
        help='Specify disk size in GB, 10 GB by default.',
        normalize=tmt.utils.normalize_storage_size)
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
            keys: Optional[List[str]] = None,
            verbose: int = 0,
            logger: tmt.log.Logger) -> None:

        keys = keys or list(self.keys())
        super_keys = [key for key in keys if key not in ('memory', 'disk')]

        super().show(keys=super_keys, verbose=verbose, logger=logger)

        logger.info('memory', f"{self.memory} MB", 'green')
        logger.info('disk', f"{self.disk} GB", 'green')


@dataclasses.dataclass
class ProvisionTestcloudData(TestcloudGuestData, tmt.steps.provision.ProvisionStepData):
    pass


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
    memory: int
    disk: str
    connection: str
    arch: str

    # Not to be saved, recreated from image_url/instance_name/... every
    # time guest is instantiated.
    # FIXME: ignore[name-defined]: https://github.com/teemtee/tmt/issues/1616
    _image: Optional['testcloud.image.Image'] = None  # type: ignore[name-defined]
    _instance: Optional['testcloud.instance.Instance'] = None  # type: ignore[name-defined]
    _domain: Optional[  # type: ignore[name-defined]
        'testcloud.domain_configuration.DomainConfiguration'] = None

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
                    seconds=DEFAULT_CONNECT_TIMEOUT), tick=1)

        except tmt.utils.WaitingTimedOutError:
            raise ProvisionError(
                f'Failed to {message} in {DEFAULT_CONNECT_TIMEOUT}s.')

    def _guess_image_url(self, name: str) -> str:
        """ Guess image url for given name """

        # Try to check if given url is a local file
        name_as_path = Path(name)
        if name_as_path.is_absolute() and name_as_path.is_file():
            return f'file://{name}'

        url: Optional[str] = None
        assert testcloud is not None

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
        self._instance = testcloud.instance.Instance(
            self.instance_name, image=self._image,
            connection=f"qemu:///{self.connection}", desired_arch=self.arch)

    def prepare_ssh_key(self, key_type: Optional[str] = None) -> None:
        """ Prepare ssh key for authentication """
        assert self.workdir is not None

        # Use existing key
        if self.key:
            self.debug("Extract public key from the provided private one.")
            command = Command("ssh-keygen", "-f", str(self.key[0]), "-y")
            public_key = self._run_guest_command(command, silent=True).stdout
        # Generate new ssh key pair
        else:
            self.debug('Generating an ssh key.')
            key_name = f"id_{key_type if key_type is not None else 'rsa'}"
            self.key = [self.workdir / key_name]
            command = Command("ssh-keygen", "-f", str(self.key[0]), "-N", "")
            if key_type is not None:
                command += Command("-t", key_type)
            self._run_guest_command(command, silent=True)
            self.verbose('key', self.key[0], 'green')
            with open(self.workdir / f'{key_name}.pub') as pubkey_file:
                public_key = pubkey_file.read()

        # Place public key content into the machine configuration
        self.config.USER_DATA = USER_DATA.format(
            user_name=self.user, public_key=public_key)
        self.config.COREOS_DATA = COREOS_DATA.format(
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
        self._domain.memory_size = self.memory * 1024
        self._domain.cpu_count = 2  # Make configurable

        # Is the combination of host-requested architecture kvm capable?
        kvm = bool(self.arch == platform.machine() and os.path.exists("/dev/kvm"))

        # Is this el <= 7?
        legacy_os = testcloud.util.needs_legacy_net(self._image.name)

        # Is this a CoreOS?
        self._domain.coreos = bool(re.search('coreos|rhcos', self.image.lower()))

        if self.arch == "x86_64":
            self._domain.system_architecture = X86_64ArchitectureConfiguration(
                kvm=kvm,
                uefi=False,  # Configurable
                model="q35" if not legacy_os else "pc")
        elif self.arch == "aarch64":
            self._domain.system_architecture = AArch64ArchitectureConfiguration(
                kvm=kvm,
                uefi=True,  # Always enabled
                model="virt")
        elif self.arch == "ppc64le":
            self._domain.system_architecture = Ppc64leArchitectureConfiguration(
                kvm=kvm,
                uefi=False,  # Always disabled
                model="pseries")
        elif self.arch == "s390x":
            self._domain.system_architecture = S390xArchitectureConfiguration(
                kvm=kvm,
                uefi=False,  # Always disabled
                model="s390-ccw-virtio")
        else:
            raise tmt.utils.ProvisionError("Unknown architecture requested.")

        mac_address = testcloud.util.generate_mac_address()
        if f"qemu:///{self.connection}" == "qemu:///system":
            self._domain.network_configuration = SystemNetworkConfiguration(
                mac_address=mac_address)
        elif f"qemu:///{self.connection}" == "qemu:///session":
            device_type = "virtio-net-pci" if not legacy_os else "e1000"
            self._domain.network_configuration = UserNetworkConfiguration(
                mac_address=mac_address,
                port=testcloud.util.spawn_instance_port_file(self.instance_name),
                device_type=device_type)
        else:
            raise tmt.utils.ProvisionError("Only system, or session connection is supported.")

        image = QCow2StorageDevice(self._domain.local_disk, self.disk)
        self._domain.storage_devices.append(image)

        if not self._domain.coreos:
            seed_disk = RawStorageDevice(self._domain.seed_path)
            self._domain.storage_devices.append(seed_disk)

        self._instance = testcloud.instance.Instance(
            hostname=hostname,
            image=self._image,
            connection=f"qemu:///{self.connection}",
            domain_configuration=self._domain)
        self.verbose('name', self.instance_name, 'green')

        # Decide if we want to multiply timeouts when emulating an architecture
        time_coeff = NON_KVM_TIMEOUT_COEF if not kvm else 1

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
            self._instance.start(DEFAULT_BOOT_TIMEOUT * time_coeff)
        except (testcloud.exceptions.TestcloudInstanceError,
                libvirt.libvirtError) as error:
            raise ProvisionError(
                f'Failed to boot testcloud instance ({error}).')
        self.guest = self._instance.get_ip()
        self.port = int(self._instance.get_instance_port())
        self.verbose('ip', self.guest, 'green')
        self.verbose('port', self.port, 'green')
        self._instance.create_ip_file(self.guest)

        # Wait a bit until the box is up
        if not self.reconnect(
                timeout=DEFAULT_CONNECT_TIMEOUT *
                time_coeff,
                tick=1):
            raise ProvisionError(
                f"Failed to connect in {DEFAULT_CONNECT_TIMEOUT * time_coeff}s.")

        if not self._instance.kvm:
            self.debug(
                f"Waiting {NON_KVM_ADDITIONAL_WAIT} seconds "
                f"for non-kvm instance...")
            time.sleep(NON_KVM_ADDITIONAL_WAIT)

    def stop(self) -> None:
        """ Stop provisioned guest """
        super().stop()
        # Stop only if the instance successfully booted
        if self._instance and self.guest:
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
class ProvisionTestcloud(tmt.steps.provision.ProvisionPlugin):
    """
    Local virtual machine using testcloud

    Minimal config which uses the latest fedora image:

        provision:
            how: virtual

    Here's a full config example:

        provision:
            how: virtual
            image: fedora
            user: root
            memory: 2048

    As the image use 'fedora' for the latest released Fedora compose,
    'fedora-rawhide' for the latest Rawhide compose, short aliases such as
    'fedora-32', 'f-32' or 'f32' for specific release or a full url to
    the qcow2 image for example from:

        https://kojipkgs.fedoraproject.org/compose/

    Short names are also provided for 'centos', 'centos-stream', 'alma',
    'rocky', 'oracle', 'debian' and 'ubuntu' (e.g. 'centos-8' or 'c8').

    Note that the non-rpm distros are not fully supported yet in tmt as
    the package installation is performed solely using dnf/yum and rpm.
    But you should be able the login to the provisioned guest and start
    experimenting. Full support is coming in the future :)

    Supported Fedora CoreOS images are:

        fedora-coreos
        fedora-coreos-stable
        fedora-coreos-testing
        fedora-coreos-next

    Use the full path for images stored on local disk, for example:

        /var/tmp/images/Fedora-Cloud-Base-31-1.9.x86_64.qcow2

    In addition to the qcow2 format, vagrant boxes can be used as well,
    testcloud will take care of unpacking the image for you.
    """

    _data_class = ProvisionTestcloudData
    _guest_class = GuestTestcloud

    # Guest instance
    _guest = None

    def go(self) -> None:
        """ Provision the testcloud instance """
        super().go()

        if self.get('list-local-images'):
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
        for int_key in ["memory", "disk", "port"]:
            value = getattr(data, int_key)
            if value is not None:
                try:
                    setattr(data, int_key, int(value))
                except ValueError as exc:
                    raise tmt.utils.NormalizationError(
                        f'{self.name}:{int_key}', value, 'an integer') from exc

        data.show(verbose=self.verbosity_level, logger=self._logger)

        if data.hardware and data.hardware.constraint:
            self.warn("The 'virtual' provision plugin does not support hardware requirements.")

        # Create a new GuestTestcloud instance and start it
        self._guest = GuestTestcloud(
            logger=self._logger,
            data=data,
            name=self.name,
            parent=self.step)
        self._guest.start()

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
