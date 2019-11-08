""" Proof-of-concept libvirt provisioning step """

import os
import subprocess

import libvirt
import paramiko
import time

from tmt.steps.provision.base import ProvisionBase


# Hacky, hacky constants

LIBVIRT_URI = 'qemu:///system'
NAME = 'tmt-libvirt-poc-f31'
MIRROR = 'https://download.fedoraproject.org/pub'
INSTALLATION_URL = f'{MIRROR}/fedora/linux/releases/31/Server/x86_64/os'
PASSWORD = 'tmt'

KICKSTART = '''
install
rootpw --plaintext tmt
auth --enableshadow --passalgo=sha512
keyboard --vckeymap=us --xlayouts='us'
lang en_US.UTF-8
timezone --isUtc UTC
network --device link --activate

# Wipe all disk
zerombr
bootloader
clearpart --all --initlabel
autopart --type=plain

url --mirrorlist=https://mirrors.fedoraproject.org/mirrorlist?repo=fedora-$releasever&arch=$basearch
repo --name=fedora
repo --name=updates

%packages
@^minimal-environment
qemu-guest-agent
%end

poweroff
'''


class ProvisionLibvirt(ProvisionBase):
    def __init__(self, data, step, instance_name=None):
        super().__init__(data, step, instance_name=instance_name)

    def _get_vm(self, name):
        try:
            print('get', name, '...')
            vm = self.libvirt_connection.lookupByName(name)
            print(vm)
            return vm
        except libvirt.libvirtError as e:
            print(e)
            pass

    def _install(self):
        KICKSTART_FILENAME = 'f31.ks'
        self.ks_path = os.path.join(self.provision_dir, KICKSTART_FILENAME)
        VIRT_INSTALL_CMD = ('virt-install', '--connect', LIBVIRT_URI,
                            '--name', NAME,
                            '--disk', 'size=20', '--memory=2048',
                            f'--location={INSTALLATION_URL}',
                            f'--initrd-inject={self.ks_path}',
                            '--extra-args', f'ks=file:/{KICKSTART_FILENAME}',
                            '--noautoconsole', '--noreboot')
        with open(self.ks_path, 'w') as f:
            f.write(KICKSTART)
        print('installing...')
        subprocess.run(VIRT_INSTALL_CMD, check=True)
        vm = self._get_vm(NAME)
        while vm.isActive():
            time.sleep(1)
        print('installation completed')

    def _clone_and_get_vm(self):
        subprocess.run(('virt-clone', '--connect', LIBVIRT_URI,
                        '--auto-clone', '-o', NAME, '-n', self.name),
                       check=True)
        return self.libvirt_connection.lookupByName(self.name)

    def _get_ip(self):
        ip = None
        while not ip:
            time.sleep(1)
            try:
                ifaces = self.vm.interfaceAddresses(
                    libvirt.VIR_DOMAIN_INTERFACE_ADDRESSES_SRC_AGENT
                )
                ip = ifaces['enp1s0']['addrs'][0]['addr']
            except libvirt.libvirtError as e:
                if 'Guest agent is not responding' not in e.args[0]:
                    raise e
            except (KeyError, TypeError):
                pass
        return ifaces['enp1s0']['addrs'][0]['addr']

    def execute(self, cmd):
        """ executes one command in a guest """
        print('connect')
        self.ssh_client = self.ssh_client or paramiko.SSHClient()
        self.ssh_client.connect(self.ip, username='root', password=PASSWORD)
        chan = self.ssh_client.get_transport().open_session()
        print('exec', cmd)
        chan.exec_command(cmd)
        ret = chan.recv_exit_status()
        assert ret == 0
        return ret

    def sync_workdir_to_guest(self):
        """ sync self.plan.workdir from host to guests """
        print('sync_workdir_to_guest')
        pass

    def sync_workdir_from_guest(self):
        """ sync self.plan.workdir from guest to host """
        print('sync_workdir_from_guest')
        pass

    def copy_from_guest(self, target):
        """ copy on guest to workdir and sync_workdir_from_guest

            arg: "/var/log/journal.log"
               => f"{provision_dir}/copy/var/log/journal.log

        """
        print('copy_from_guest', target)
        pass

    def go(self):
        """ do the actual provisioning """
        self.libvirt_connection = libvirt.open(LIBVIRT_URI)
        self.name = NAME + '-' + (self.instance_name or 'instance')
        if not self._get_vm(NAME):
            self._install()
        self.vm = self._get_vm(self.name) or self._clone_and_get_vm()
        if not self.vm.isActive():
            self.vm.create()
        self.ip = self._get_ip()
        self.ssh_client = None

    def load(self):
        """ load state from workdir """
        print('load')
        super().load()
        pass

    def save(self):
        """ save state to workdir """
        print('save')
        super().save()
        pass

    def destroy(self):
        """ destroy the machine """
        print('destroy')
        subprocess.run(('virsh', '--connect', LIBVIRT_URI,
                        'undefine', self.name, '--remove-all-storage'),
                       check=True)
        pass
