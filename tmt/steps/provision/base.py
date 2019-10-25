import os
import random
import string


class ProvisionBase(object):
    def __init__(self, data, step, instance_name=None):
        self.data = data
        self.step = step
        self.instance_name = instance_name or ''.join(random.choices(string.ascii_letters, k=16))
        self.provision_dir = os.path.join(step.workdir, self.instance_name)

    def execute(self, command):
        """ executes one command in a guest """
        pass

    def sync_workdir_to_guest(self):
        """ sync self.plan.workdir from host to guests """
        pass

    def sync_workdir_from_guest(self):
        """ sync self.plan.workdir from guest to host """
        pass

    def copy_from_guest(self):
        """ copy on guest to workdir and sync_workdir_from_guest

            arg: "/var/log/journal.log"
               => f"{provision_dir}/copy/var/log/journal.log

        """
        pass

    def go(self):
        """ do the actual provisioning """
        pass

    def load(self):
        """ load state from workdir """
        pass

    def save(self):
        """ save state to workdir """
        pass

    def destroy(self):
        """ destroy the machine """
        pass

