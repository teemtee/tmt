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
    default_container = 'fedora/f30'

    def __init__(self, data, plan):
        """ Initialize the Vagrant provision step """
        super(Provision, self).__init__(data, plan)

        #TODO: investigate whether this call is needed
        self.wake(self)

    def load(self):
        """ Load ProvisionVagrant step """
        super(Provision, self).load(self)

    def save(self):
        """ Save ProvisionVagrant step """
        #TODO: ensure this saves self.data[*]
        super(Provision, self).save(self)

    def show(self):
        """ Show execute details """
        super(ProvisionVagrant, self).show(keys=['how', 'box', 'image'])

    def wake(self):
        """ Some minimal inicialization """
        super(Provision, self).wake(self)
        # capabilities? providers?
        self.vagrantfile = os.patch.join(self.provision_dir, 'Vagrantfile')

    def knowhow(self):
        """ Decide what to do when HOW is ... """

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


    def go(self)
        """ Execute actual provisioning """
        echo ('provisioning localhost')
        self.knowhow()
        self.create(self)
        # self.plan.workdir
        # [ . . . ]
        # Dry-run?
        self.run_vagrant('up')

    def execute(self, command)
        """ Execute remote command """
        self.run_vagrant(['ssh', '-c', command])

    def sync(self)
        """ sync on demand """
        # needs reload for sync configuration change
        # TODO: test
        self.run_vagrant('rsync')

    def sync_back(self)
        """ sync_back """
        # IDK: investigate
        # 'vm.synced_folder ".", "/vagrant"'
        pass

    def destroy(self)
        """ remove instance """
        self.run_vagrant(['destroy', '-f'])

    def cleanup(self)
        """ remove box and base box """
        self.run_vagrant(['box', 'remove', '-f'])
        # libvirt?

    def run_prepare(self, name, path)
        """ add single 'preparator' and run it """
        self.add_config(['vm.provision', .....])

    def create(self)
        """ Create default Vagrantfile with our modifications """
        self.run_vagrant(['init', '-fm', self.box])
        dir = f'"{self.plan.workdir}"'
        self.add_config(['vm.synced_folder', dir, dir, 'type: "' + self.sync_type + '"'])
        # [. . . ]

    def validate(self)
        """ Validate Vagrantfile format """
        self.run_vagrant('validate')

    def run_vagrant(self, args)
        """ Run a Vagrant command

              args = 'command args'

            or

              args = ['comand', 'args']

        """
        command = self.append(executable, args)

        # TODO: dry-run / verbose
        command = self.prepend('echo', command)

        subprocess.call(command, timeout = self.timeout, cwd = self.provision_dir) #instance_dir?
        #subprocess.check_output
        #exit code?

    def add_config(self, config)
        """ Add config entry into Vagrantfile
            right before last 'end'

              config = "string"

            or list:

              config = ['one', 'two', 'three']
                => "one two, three"

        """
        if type(config) is list:
            config = f'{config[0]} ' + ', '.join(config[1:])

        vagrantdata = open(vagrantfile).read().splitlines()

        # Lookup last 'end' in Vagrantfile
        i = 0
        for line in reversed(vagrantdata):
            i -= 1
            if (line.find('end') != -1)
                break

        vagrantdata = vagrantdata[:i] \
            + [config_prefix + config + '\n'] \
            + vagrantdata[i:]

        with open(vagrantfile, 'w') as f:
            f.writelines(vagrantdata)

        self.validate(self)


    def set_default(self, where, default) #, additional = None, setthis = None)
        if not (where in self.data and self.data[where]):
            self.data[where] = default
            #if not (additional is None or setthis is None):

    def prepend(self, thing, string)
        if type(thing) is list:
            return thing.insert(0, string)
        else:
            return string + thing

    def append(self)
        if type(thing) is list:
            return thing.append(string)
        else:
            return thing + string


    def how_vm(self)
        self.virtual(self)

    def how_libvirt(self)
        pass

    def how_openstack(self)
        pass

    def how_docker(self)
        self.container(self)

    def how_podman(self)
        self.container(self)

    def how_container(self)
        # TODO

    def how_virtual(self)
        # TODO:

