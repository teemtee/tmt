# coding: utf-8

""" Provision Step Vagrnat Class """

from click import echo

from tmt.steps.provision.base import ProvisionBase

import tmt
import subprocess
import os
import re

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
    config_prefix = '  config.vm.'
    sync_type = 'rsync'
    default_image = 'fedora/f30-cloud-base'
    default_container = 'fedora:30'
    image_uri = None

    def __init__(self, data, step):
        """ Initialize the Vagrant provision step """
        super(ProvisionVagrant, self).__init__(data, step)
        self.vagrantfile = os.path.join(self.provision_dir, 'Vagrantfile')

        self.debugon = True

        # Are we resuming?
        if os.path.exists(self.vagrantfile) and os.path.isfile(self.vagrantfile):
            self.validate()
            return self

        # Check for working Vagrant
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
        super(ProvisionVagrant, self).load(self)

    def save(self):
        """ Save ProvisionVagrant step """
        #TODO: ensure this saves self.data[*]
        # instancename
        super(ProvisionVagrant, self).save(self)

#    def wake(self):
#        """ Prepare the Vagrantfile """
#        super(ProvisionVagrant, self).wake(self)
#        # capabilities? providers?

    def show(self):
        """ Show execute details """
        super(ProvisionVagrant, self).show(keys=['how', 'box', 'image'])

    def how(self):
        """ Decide what to do when HOW is ...
            does not add anything into Vagrantfile yet
        """

        self.set_default('how', 'virtual')
        self.set_default('image', self.default_image)

        image = self.data['image']

        try:
            i = urlparse(image)
            if not i.schema:
                raise (i)
            self.image_uri = i
        except:
            pass

        self.debug('image_uri', self.image_uri)


        if self.image_uri:
            self.set_default('box', 'box_' + self.instance_name)

            if re.search("\.box$", image) is None:
                # an actual box file, Great!
                pass

            elif re.search("\.qcow2$", image) is None:
                # do some qcow2 magic
                self.data['box'] = '...'
                raise SpecificationError("NYI: QCOW2 image")

            else:
                raise SpecificationError(f"Image format not recognized: {image}")

        else:
            self.set_default('box', image)

        for x in ('how','box','image'):
            self.debug(x, self.data[x])


    def create(self):
        """ Create default Vagrantfile with our modifications """
        self.run_vagrant_success('init', '-fm', self.data['box'])

    def add_defaults(self):
        """ Adds default config entries
            1) Disable default sync
            2) To sync plan workdir
        """
        dir = self.step.workdir
        self.add_synced_folder('synced_folder', ".", "/vagrant", 'disabled: true')
        self.add_synced_folder('synced_folder', dir, dir)
        # [. . . ]

    def go(self):
        """ Execute actual provisioning """
        echo ('provisioning vagrant')
        # self.run_vagrant_success('up')

    def execute(self, command):
        """ Execute remote command """
        return self.run_vagrant_success('ssh', '-c', command)

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
        # 'synced_folder ".", "/vagrant"'
        pass

    def destroy(self):
        """ remove instance """
        self.run_vagrant_success('destroy', '-f')

    def cleanup(self):
        """ remove box and base box """
        self.run_vagrant_success('box', 'remove', '-f')
        # libvirt?

    def run_prepare(self, name, path):
        """ add single 'preparator' and run it """
        self.add_config('provision', name, )

    def validate(self):
        """ Validate Vagrantfile format """
        self.run_vagrant_success('validate')

    def run_vagrant_success(self, *args):
        cps = self.run_vagrant(*args)
        if cps.exitcode != 0:
            raise RuntimeError(f'Failed to run vagrant:\n  command: {cps}')

    def run_vagrant(self, *args):
        """ Run a Vagrant command

              args = 'command args'

            or

              args = ['comand', 'args']

            return subprocess.CompletedProcess
        """
        if len(args) == 1:
            args = args[0]
        elif len(args) == 0:
            raise RuntimeError("vagrant has to run with args")

        command = self.prepend(args, self.executable)

        # TODO: dry-run / verbose
        command = self.prepend(command, 'echo')

        return echo(command)

        return subprocess.run(
            command,
            timeout = self.timeout,
            cwd = self.provision_dir,
            capture_output=True)

    def add_synced_folder(self, sync_from, sync_to, *args):
        self.add_config('synced_folder',
            sync_from,
            self.quote(sync_to),
            f'type: {self.quote(self.sync_type)}', *args)

    def add_config(self, *config):
        """ Add config entry into Vagrantfile
            right before last 'end'

              config = "string"

            or:

              config = ['one', 'two', 'three']
                => one "two", three

        """
        if len(config) == 1:
            config = config[0]
        elif len(config) == 0:
            raise RuntimeError("config has no definition")
        else:
            config = f'{config[0]} ' + self.quote(config[1]) + ', '.join(config[2:])

        vagrantdata = open(self.vagrantfile).read().splitlines()

        # Lookup last 'end' in Vagrantfile
        i = 0
        for line in reversed(vagrantdata):
            i -= 1
            if (line.find('end') != -1):
                break

        vagrantdata = vagrantdata[:i] \
            + [config_prefix + config + '\n'] \
            + vagrantdata[i:]

        debug('>>>' + vagrantdata)
        return vagrantdata

        with open(self.vagrantfile, 'w') as f:
            f.writelines(vagrantdata)

        self.validate(self)


    def set_default(self, where, default):
        if not (where in self.data and self.data[where]):
            self.data[where] = default

    def prepend(self, thing, string):
        if type(thing) is list:
            return thing.insert(0, string)
        elif type(thing) is tuple:
            return (string ,) + thing
        else:
            return string + ' ' + thing

    def append(self, thing, string):
        if type(thing) is list:
            return thing.append(string)
        elif type(thing) is tuple:
            return thing + (string ,)
        else:
            return thing + ' ' + string

    def quote(self, string):
        return f'"{string}"'

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

    def debug(self, k, v):
        if self.debugon:
            echo(f"{k} = {v}")
