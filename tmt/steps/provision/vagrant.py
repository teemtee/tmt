# coding: utf-8

""" Provision Step Vagrnat Class """

from click import echo

from tmt.steps.provision.base import ProvisionBase

import tmt
import childprocess
import os
from urllib.parse import urlparse

# DATA[*]:
#   HOW = libvirt|virtual|docker|container|vagrant|...
#         provider, in Vagrant's terminilogy
#
#   IMAGE = URI|NAME
#         NAME is for Vagrant or other HOW, passed directly
#         URI can be path to BOX, QCOW2 or Vagrantfile f.e.
#
#   BOX = Set a BOX name directly (in case of URI for IMAGE)
#
class ProvisionVagrant(ProvisionBase):
    """ Use Vagrant to Provision an environment for testing """
    executable = 'vagrant'
    config_prefix = '  config.'
    sync_type = 'rsync'
    default_image = 'fedora/f30-cloud-base'
    default_container = 'fedora:30'

    def __init__(self, data, plan):
        """ Initialize the Vagrant provision step """
        super(Provision, self).__init__(data, plan)
        self.vagrantfile = os.patch.join(self.provision_dir, 'Vagrantfile')

        # Are we resuming?
        if os.path.exists(self.vagrantfile) and os.path.isfile(self.vagrantfile):
            self.validate()
            return self

        # Check for Vagrant
        self.run_vagrant('version')

        # Let's check what's actually needed
        self.how()

        # Create a Vagrantfile
        self.create()

        # Add default entries to Vagrantfile
        self.add_defaults()

        # Let's check what's actually needed
        self.add_knowhow()


    def load(self):
        """ Load ProvisionVagrant step """
        #TODO: ensure this loads self.data[*]
        # instancename and regenerates provision_dir and vagrantfile
        super(Provision, self).load(self)

    def save(self):
        """ Save ProvisionVagrant step """
        #TODO: ensure this saves self.data[*]
        # instancename
        super(Provision, self).save(self)

#    def wake(self):
#        """ Prepare the Vagrantfile """
#        super(Provision, self).wake(self)
#        # capabilities? providers?

    def show(self):
        """ Show execute details """
        super(ProvisionVagrant, self).show(keys=['how', 'box', 'image'])

    def how(self):
        """ Decide what to do when HOW is ...
            does not add anything into Vagrantfile yet
        """

        set_default('how', 'virtual')
        set_default('image', default_image)

        image = self.data['image']

        try:
            urlparse(image)
            self.image_is_uri = True
        except:
            self.image_is_uri = False

        if self.image_is_uri:
            set_default('how', 'box_' + self.instance_name)

            if len(re.search("\.box$", image)):
                # an actual box file, Great!
                pass

            elif len(re.search("\.qcow2$", image)):
                # do some qcow2 magic
                self.data['box'] = '...'
                raise SpecificationError("NYI: QCOW2 image")

            else:
                raise SpecificationError(f"Image format not recognized: {image}")

        else:
            set_default('box', image)


    def create(self):
        """ Create default Vagrantfile with our modifications """
        self.run_vagrant_success(['init', '-fm', self.box])

    def add_defaults(self):
        """ Adds default config entries
            1) Disable default sync
            2) To sync plan workdir
        """
        dir = self.plan.workdir
        self.add_synced_folder('vm.synced_folder', ".", "/vagrant", 'disabled: true')
        self.add_synced_folder('vm.synced_folder', dir, dir)
        # [. . . ]

    def go(self):
        """ Execute actual provisioning """
        echo ('provisioning localhost')
        # self.run_vagrant_success('up')

    def execute(self, command):
        """ Execute remote command """
        return self.run_vagrant_success(['ssh', '-c', command])

    def status(self, command):
        """ Get vagrant's status """
        return self.run_vagrant_success('status')

    def sync_workdir_to_guest(self):
        """ sync on demand """
        # needs reload for sync configuration change
        # TODO: test
        self.run_vagrant_success('rsync')

    def sync_workdir_from_guest(self):
        """ sync_back """
        # IDK: investigate
        # 'vm.synced_folder ".", "/vagrant"'
        pass

    def destroy(self):
        """ remove instance """
        self.run_vagrant_success(['destroy', '-f'])

    def cleanup(self):
        """ remove box and base box """
        self.run_vagrant_success(['box', 'remove', '-f'])
        # libvirt?

    def run_prepare(self, name, path):
        """ add single 'preparator' and run it """
        self.add_config('vm.provision', '')

    def validate(self):
        """ Validate Vagrantfile format """
        self.run_vagrant_success('validate')

    def run_vagrant_success(self, *args):
        self.run_vagrant(*args)

    def run_vagrant(self, *args):
        """ Run a Vagrant command

              args = 'command args'

            or

              args = ['comand', 'args']

            return subprocess.CompletedProcess
        """
        command = self.prepend(args, executable)

        # TODO: dry-run / verbose
        command = self.prepend(command, 'echo')

        return echo(command)

        return subprocess.run(
            command,
            timeout = self.timeout,
            cwd = self.provision_dir,
            capture_output=True)

    def add_synced_folder(self, sync_from, sync_to, *args):
        self.add_config('vm.synced_folder',
            self.quote(sync_from),
            self.quote(sync_to),
            f'type: {quote(self.sync_type)}', *args)

    def add_config(self, *config):
        """ Add config entry into Vagrantfile
            right before last 'end'

              config = "string"

            or:

              config = ['one', 'two', 'three']
                => "one two, three"

        """
        if len(config) == 1:
            config = config[0]
        elif len(config) == 0:
            raise RuntimeError("")
        else:
            config = f'{config[0]} ' + ', '.join(config[1:])

        vagrantdata = open(vagrantfile).read().splitlines()

        # Lookup last 'end' in Vagrantfile
        i = 0
        for line in reversed(vagrantdata):
            i -= 1
            if (line.find('end') != -1):
                break

        vagrantdata = vagrantdata[:i] \
            + [config_prefix + config + '\n'] \
            + vagrantdata[i:]

        print(vagrantdata)
        return vagrantdata

        with open(vagrantfile, 'w') as f:
            f.writelines(vagrantdata)

        self.validate(self)


    def set_default(self, where, default):
        if not (where in self.data and self.data[where]):
            self.data[where] = default

    def prepend(self, thing, string):
        if type(thing) is list:
            return thing.insert(0, string)
        else:
            return string + thing

    def append(self, thing, string):
        if type(thing) is list:
            return thing.append(string)
        else:
            return thing + string

    def quote(self, string):
        return thing + string


    def how_vm(self):
        self.virtual(self)

    def how_libvirt(self):
        pass

    def how_openstack(self):
        pass

    def how_docker(self):
        self.container(self)

    def how_podman(self):
        self.container(self)

    def how_container(self):
        # TODO
        pass

    def how_virtual(self):
        # TODO:
        pass

