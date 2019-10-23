# coding: utf-8

""" Provision Step Vagrnat Class """

from click import echo

from tmt.steps.provision.base import ProvisionBase

import tmt
import childprocess
import os
from urllib.parse import urlparse

class ProvisionVagrant(ProvisionBase):
    """ Use Vagrant to Provision an environment for testing """
    executable = 'vagrant'
    config_prefix = '  config.'
    sync_type = 'rsync'

    def __init__(self, data, plan):
        """ Initialize the Vagrant provision step """
        super(Provision, self).__init__(data, plan)
        if not 'how' in self.data:
            self.data['how'] = ''

        self.data['box'] = 'box_' + self.data['instance_name']

        try:
            urlparse(image)
            image_is_uri = True
        except:
            image_is_uri = False

        if not 'image' in self.data:
            self.data['box'] = 'fedora/f30-cloud-base'
            self.data['image'] = ''

        elif image_is_uri:
            if len(re.search("\.box$", image)):
                # an actual box file
                self.data['box'] = 'box_' + self.instance_name

            elif len(re.search("\.qcow2$", image)):
                # do some qcow2 magic
                self.data['box'] = '...'
                raise('NYI')

            else:
                raise('Image format not known.')

        else:
            self.data['box'] = image
            self.data['image'] = ''

        #self.instancename = ''.join(random.choices(string.ascii_letters, k=16))
        #self.provisiondir = self.workdir + '/' + self.instance_name

        # instance_dir?
        self.vagrantfile = os.patch.join(self.workdir, 'Vagrantfile')

    def save(self):
        echo ('NYI: saving localhost')

    def show(self):
        """ Show execute details """
        super(ProvisionVagrant, self).show(keys=['how', 'box', 'image'])

    def go(self)
        """ Execute actual provisioning """
        echo ('provisioning localhost')
        self.create(self)
        # self.plan.run.workdir
        # [ . . . ]
        # Dry-run?
        self.run_vagrant(self, 'up')

    def execute(self, command)
        """ Execute remote command """
        self.run_vagrant(self, ['ssh', '-c', command])

    def sync(self)
        """ sync on demand """
        # needs reload for sync configuration change
        # TODO: test
        self.run_vagrant 'rsync'

    def sync_back(self)
        """ sync_back """
        # IDK: investigate
        # 'vm.synced_folder ".", "/vagrant"'
        pass

    def destroy(self)
        """ sync on demand """
        self.run_vagrant(self, ['destroy', '-f'])
        # box remove
        self.run_vagrant(self, ['box', 'remove', '-f'])

    def run_prepare(self)
        """ add single 'preparator' and run it """
        self.add_config(self, 'vm.provision "' + self.plan.run.workdir + '", "' + self.plan.run.workdir + '", type: "rsync", rsync__exclude: ".git/"')

    def create(self)
        """ Create default Vagrantfile with our modifications """
        self.run_vagrant(self, ['init', '-fm', self.box])
        self.add_config(self, 'vm.synced_folder "' + self.plan.run.workdir + '", "' + self.plan.run.workdir + '", type: "rsync", rsync__exclude: ".git/"')
        self.add_config(self, 'vm.synced_folder "' + self.plan.run.workdir + '", "' + self.plan.run.workdir + '", type: "rsync", rsync__exclude: ".git/"')
        # [. . . ]

    def validate(self)
        """ Validate Vagrantfile format """
        self.run_vagrant(self, 'validate')

    def run_vagrant(self, args)
        """ Show execute details """
        if type(args) is not list:
            args = [args]
        # Dry-run?
        # Verbose?
        subprocess.call([executable] + args, timeout = self.timeout, cwd = self.workdir) #instance_dir?
        #exit code?

    def add_config(self, config)
        """ Add config entry into Vagrantfile """
        vagrantdata = open(vagrantfile).read().splitlines()

        # Lookup last 'end' so we know position to insert into
        i = 0
        for line in vagrantdata:
            i -= 1
            if len(re.search("end", v)
                break

        vagrantdata = vagrantdata[:i] + [config_prefix + config] + vagrantdata[i:]

        with open(vagrantfile, 'w') as f:
            f.write(vagrantdata)

        self.validate(self)
