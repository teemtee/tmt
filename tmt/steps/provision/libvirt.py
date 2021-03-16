import re
from pathlib import Path
from time import sleep
from typing import Tuple

import click

import tmt

VM_CLONE_OUT_RE = re.compile(".+'(.+)' created successfully")
VM_IP_RE = re.compile(".+ipv4\\s+(.+)\\/\\d+")
VM_WAITING_COUNTER_MAX_NET = 30


class ProvisionLibvirt(tmt.steps.provision.ProvisionPlugin):
    """Libvirt provision plugin.

    Prerequisite to have the vm already prepared via libvirt.
    Plugin clones the existing VM and do the rest steps.

    Example config:
    ```yaml
    provision:
        how: libvirt
        origin_vm_name: c2r_centos7_template
        develop: true
    ```

    Needed packages:
      virt-install \
      virt-manager \
      virt-viewer \
      virt-viewer \
      qemu-kvm \
      libvirt-devel \
      libvirt-daemon-config-network \
      libvirt-daemon-kvm \
      libguestfs-tools
    """

    # Guest instance
    _guest = None

    # Supported keys
    _keys = ["origin_vm_name", "develop"]

    # Supported methods
    _methods = [tmt.steps.Method(name="libvirt", doc=__doc__, order=50)]

    @classmethod
    def options(cls, how=None):
        """Prepare command line options for connect"""
        return [
            click.option(
                "-o",
                "--origin_vm_name",
                help="The name of the vm to clone",
                ),
            click.option(
                "--develop",
                metavar="DEVELOP",
                help="Do not remove the vm",
                ),
            ] + super().options(how)

    def wake(self, options=None, data=None):
        """Override options and wake up the guest"""
        if data:
            self._guest = GuestLibvirt(
                data,
                name=self.name,
                parent=self.step,
                new_keys=tuple(self._keys),
                )
            self._guest.prepare_vm(self.get("origin_vm_name"))

    def go(self):
        """Provision the VM."""
        super().go()
        # Prepare data for the guest instance
        data = dict()
        for key in self._keys:
            data[key] = self.get(key)
        self._guest = GuestLibvirt(
            data,
            name=self.name,
            parent=self.step,
            new_keys=tuple(self._keys),
            )
        self._guest.prepare_vm(self.get("origin_vm_name"))

    def guest(self):
        """Return the provisioned guest"""
        return self._guest

    def show(self):
        """Show provision details"""
        super().show(self._keys)


class GuestLibvirt(tmt.Guest):
    def __init__(self, data, name=None, parent=None,
                 new_keys: Tuple[str, ...] = ()):
        super().__init__(data=data, name=name, parent=parent, new_keys=new_keys)
        self.user = "root"

    def prepare_vm(self, origin_vm_name):
        stdout, _ = self.run(
            f"virt-clone --original {origin_vm_name} --auto-clone --check all=off",
            message="Cloning VM...",
            )
        try:
            self.vm_name = VM_CLONE_OUT_RE.findall(stdout)[0]
        except IndexError:
            raise NotImplementedError(
                f"Can't extract cloned vm name from:\n{stdout}")
        self.run(f"virsh start {self.vm_name}", message="Starting VM...")

        self.guest, counter = None, 0
        while not self.guest and counter <= VM_WAITING_COUNTER_MAX_NET:
            try:
                self.guest = VM_IP_RE.findall(
                    self.run(f"virsh domifaddr --domain {self.vm_name}")[0]
                    )[0]
            except IndexError:
                counter += 1
                self.info(
                    f"Trial {counter} of {VM_WAITING_COUNTER_MAX_NET}: VM is not yet available."
                    f" Sleeping...")
                sleep(3)

    def stop(self):
        super().stop()
        if self.develop:
            self.info("In the develop mode. Skipping stopping the vm.")
            return
        self.info("Stopping the vm...")
        _, err = self.run(f"virsh shutdown --domain {self.vm_name}")
        if err:
            self.warn(f"Stopping failed.\nDetails: {err}")

    def remove(self):
        super().remove()
        if self.develop:
            self.info(
                f"In the develop mode. Skipping removing the vm {self.vm_name}. "
                f"\nUse:\nssh -o StrictHostKeyChecking=no "
                f"root@{self.guest}\nto connect the machine."
                f"\nUse:\nrsync -avPutz -e 'ssh -o StrictHostKeyChecking=no' . "
                f"{self.user}@{self.guest}:"
                f"{str(Path(self.parent.plan.workdir) / 'discover/default/tests/')}\n"
                f"to rsync your cwd to the guest.")
            return
        self.info("Removing the vm...")
        _, err = self.run(f"virsh undefine --domain {self.vm_name}")
        if err:
            self.warn(f"Removing failed.\nDetails: {err}")
