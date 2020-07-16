# coding: utf-8

""" Provision Step Vagrnat Class """

import tmt
import subprocess
import os
import re
import shutil
import click
#import pprint
from time import sleep

#from tmt.steps.provision.base import ProvisionBase
from tmt.utils import ConvertError, SpecificationError, GeneralError, quote

from urllib.parse import urlparse


class ProvisionVagrant(tmt.steps.provision.ProvisionPlugin):
    """
    Use Vagrant to Provision an environment for testing
    """

    # Guest instance
    _guest = None

    # Supported methods
    _methods = [
        tmt.steps.Method(name='virtual.vagrant', doc=__doc__, order=50),
        tmt.steps.Method(name='libvirt.vagrant', doc=__doc__, order=50),
        tmt.steps.Method(name='virtualbox.vagrant', doc=__doc__, order=50),
        tmt.steps.Method(name='container.vagrant', doc=__doc__, order=50),
        ]

    display = ['image', 'box', 'memory', 'user', 'password', 'key', 'guest',
        'vagrantfile', 'sync_type']

    @classmethod
    def options(cls, how=None):
        """ Prepare command line options for testcloud """
        return [
            click.option(
                '-i', '--image', metavar='IMAGE',
                help='Select image to use. Short name or complete url.'),
            click.option(
                '-m', '--memory', metavar='MEMORY',
                help='Set available memory in MB, 2048 MB by default.'),
            click.option(
                '-u', '--user', metavar='USER',
                help='Username to use for all guest operations.'),
            click.option(
                '-b', '--box', metavar='BOX',
                help='Explicit box name to use.'),
            click.option(
                '-p', '--password', metavar='PASSWORD',
                help='Password for login into the guest system.'),
            click.option(
                '-k', '--key', metavar='KEY',
                help='Private key for login into the guest system.'),
            click.option(
                '-g', '--guest', metavar='GUEST',
                help='Select remote host to connect to (hostname or ip).'),
            click.option(
                '-f', '--vagrantfile', metavar='VAGRANTFILE',
                help='Path to Vagrantfile, which will be copied.'),
            click.option(
                '-s', '--sync-type', metavar='SYNC_TYPE',
                help='Sync method Vagrant will use.'),
            ] + super().options(how)


    def default(self, option, default=None):
        """ Return default data for given option """
        defaults = {
            'user': 'root',
            'memory': 2048,
            'sync_type': 'rsync',
            'image': 'fedora/32-cloud-base'
            }
        if option in defaults:
            return defaults[option]
        return default

    def show(self):
        """ Show provision details """
        super().show(self.display)

    def wake(self, data=None):
        """ Override options and wake up the guest """
        super().wake(self.display)

        # Convert memory and disk to integers
        for key in ['memory']:
            if isinstance(self.get(key), str):
                self.data[key] = int(self.data[key])

        # Wake up testcloud instance
        if data:
            guest = GuestVagrant(data, name=self.name, parent=self.step)
            guest.wake()
            self._guest = guest

    def go(self):
        """ Provision the testcloud instance """
        super().go()

        # Give info about provided data
        data = dict()
        for key in self.display:
            data[key] = self.get(key)
            if key == 'memory':
                self.info(key, f"{self.get('memory')} MB", 'green')
            else:
                self.info(key, data[key], 'green')

        # Create a new GuestTestcloud instance and start it
        self._guest = GuestVagrant(data, name=self.name, parent=self.step)
        self._guest.start()

    def guest(self):
        """ Return the provisioned guest """
        return self._guest


class GuestVagrant(tmt.Guest):
    """ Architecture:

        DATA[]:
          HOW = libvirt|virtual|docker|container|vagrant|...
                provider, in Vagrant's terminilogy

          IMAGE = URI|NAME
                  NAME is for Vagrant or other HOW, passed directly
                  URI can be path to BOX, QCOW2 or Vagrantfile f.e.

          BOX = Set a BOX name directly (in case of URI for IMAGE)

    """
    # For convenicence
    executable = 'vagrant'
    config_prefix = '  config.'
    vf_name = 'Vagrantfile'
    eol = '\n'

    # This is for connect plugin. We should ship the image.
    dummy_image = 'tknerr/managed-server-dummy'
    container_image = 'registry.fedoraproject.org/fedora:latest'

    default_indent = 16
    timeout = 333

    # Any possible state Vagrant could be in (`vagrant status`)
    statuses = ('not reachable', 'running', 'not created', 'preparing', 'shutoff')

    # These will be saved for subsequent re-runs.
    _keys = ['image', 'box', 'memory', 'user', 'password', 'key', 'guest',
        'vagrantfile', 'instance_name', 'vf_data', 'sync_type', 'preparations']

    def load(self, data):
        """ load ProvisionVagrant step
            `data` is based on L2 config, defaults, and comamndline.

            Also define instance variables, as this is run on both
            first inicialization(start) and a subsequent one(wake).
        """
        super().load(data)
        # Handle custom Vagrantfiles.
        # Warning: this has higher priority than all our configs, apart from provision.
        self.custom_vagrantfile = self.vagrantfile

        # If it's defined already this is a second run
        self.instance_name = self.instance_name or self._random_name()
        self.preparations = self.preparations or 0

        # These are always derived from instance name, but defined here
        # for code deduplication.
        self.provision_dir = os.path.join(self.parent.plan.workdir, self.instance_name)
        self.vagrantfile = os.path.join(self.provision_dir, self.vf_name)

    def save(self):
        """ save ProvisionVagrant step
            We're using `_keys` to save what's needed in for re-runs.
        """
        data = super().save()
        return data

    def wake(self):
        """ wake up the guest
            Ensures the config is valid and the instance is running.
        """
        self.debug(f"Waking up Vagrant instance '{self.instance_name}'.")
        self.prepare_config()
        # The machine is supposed to be running already
        self.ensure_running()

    def start(self):
        """ execute actual provisioning
            Start the provision, after providing the config with needed
            entries.
        """
        self.info(f'Provisioning {self.executable}')

        self.vf_data = ''

        os.mkdir(self.provision_dir)
        self.prepare_config()
        self.debug(f'{self.vf_name}', self.vf_read())

        out, err = self.run_vagrant('up')
        self.ensure_running()

    def ensure_running(self):
        status = self.status()
        if status != 'running':
            raise GeneralError(
                f'Failed to provision (status: {status}), log:\n{out}\n{err}')

    def stop(self):
        """ stop provisioning """
        self.info(
            f'Stopping {self.executable}, {self.vf_name}')
        out, err = self.run_vagrant('halt')

        status = self.status()
        if status != 'shutoff':
            raise GeneralError(
                f'Failed to stop (status: {status}), log:\n{out}\n{err}')

    def execute(self, *args, **kwargs):
        """ Execute remote command
            We need to redefine this, as the behaviour is different,
            due to specifig changes in Vagrantfile (users can supply custom one).
            For arguments see base.py.
        """
        # Directory needs to be prepended first = higher 'priority'
        # Change to given directory on guest if cwd provided
        directory = kwargs.get('cwd', '')
        if directory:
            args = self.prepend(args, f"cd {quote(directory)} && ")

        # Prepare the export of environment variables
        environment = self._export_environment(kwargs.get('env', dict()))
        if environment:
            args = self.prepend(args, environment)
            self.debug('env', environment)

        return self.run_vagrant('ssh', '-c', self.join(args))

    def show(self):
        """ create and show the Vagrantfile """
        self.info(self.vf_name, self.vf_read())

    def push(self):
        """ sync on demand
            This has to be overriden, as vagrant allows for
            multiple types of sync (NFS f.e.).
        """
        return self.run_vagrant('rsync')

    def pull(self):
        """ sync from guest to host
            We're using custom plugin rsync-back.
            TODO: Verify it can handle any type of sync.
        """
        command = 'rsync-back'
        self.plugin_install(command)
        return self.run_vagrant(command)

    def remove(self):
        """ remove instance """
        for i in range(1, 5):
            if i > 1 and self.status() == 'not created':
                return
            try:
                return self.run_vagrant('destroy', '-f')
            except GeneralError:
                sleep(5)

    def ansible(self, playbook):
        """ Prepare guest using ansible playbook """
        self.prepare("ansible", playbook)

    def prepare(self, how, what):
        """ Add single 'preparation' and run it.
        """

        self.preparations += 1
        name = 'prepare_' + self.preparations
        cmd = 'provision'

        self.vf_backup("Prepare")

        # decide what to do
        if how == 'ansible':
            what = self._ansible_playbook_path(what)

            # Prepare verbose level based on the --debug option count
            verbose = self.opt('debug') * 'v' if self.opt('debug') else 'false'

            self.add_config_block(cmd,
                name,
                f'become = true',
                self.kve('become_user', self.user),
                self.kve('playbook', what),
                self.kve('verbose', verbose))
                # I'm not sure whether this is needed.
                # run: 'never'

        else:
            if self.is_uri(what):
                method = 'path'
            else:
                method = 'inline'

            self.add_config('vm',
                cmd,
                quote(name),
                self.kv('type', how),
                self.kv('privileged', 'true'),
                self.kv('run', 'never'),
                self.kv(method, what))

        try:
            self.validate()
        except GeneralError as error:
            self.vf_restore()
            raise GeneralError(
                f'Invalid input for vagrant prepare ({how}):\n{what}')

        out, err = self.run_vagrant(cmd, f'--{cmd}-with', name)
        self._ansible_summary(out)

    ## Additional API ##
    def create(self):
        """ Initialize Vagrantfile """
        self.run_vagrant('init', '-fm', self.box)
        self.debug('Initialized new Vagrantfile', self.vf_read())

    def clean(self):
        """ remove base box (image) """
        return self.run_vagrant('box', 'remove', '-f', self.box)
        # TODO: libvirt storage removal?

    def validate(self):
        """ Validate Vagrantfile format """
        return self.run_vagrant('validate')

    def reload(self):
        """ restart guest machine """
        return self.run_vagrant('reload')

    def status(self):
        """ check guest status """
        out, err = self.run_vagrant('status')

        for status in self.statuses:
            if not re.search(f" {status} ", out) is None:
                return status
        return 'unknown'

    def plugin_install(self, name):
        """ Install a vagrant plugin if it's not installed yet.
        """
        plugin = f'{self.executable}-{name}'
        command = ['plugin', 'install']
        try:
            # is it already present?
            run = f"{self.executable} {command[0]} list | grep '^{plugin} '"
            return self.run(f"bash -c \"{run}\"")
        except GeneralError:
            pass

        try:
            # try to install it
            return self.run_vagrant(command[0], command[1], plugin)
        except GeneralError as error:
            # Let's work-around the error handling limitation for now
            # by getting the output manually
            command = ' '.join([self.executable] + command + [plugin])

            out, err = self.run(f"bash -c \"{command}; :\"")

            if re.search(r"Conflicting dependency chains:", err) is None:
                raise error
            raise GeneralError('Dependency conflict detected:\n'
                'Please install vagrant plugins from one source only (hint: `dnf remove rubygem-fog-core`).')

    def prepare_config(self):
        """ Initialize ProvisionVagrant / run following:
            1] check input values and set defaults
            2] check that Vagrant works
            3] check for already-present or user-specified Vagrantfile
            4] create and populates Vagrantfile with
                - provider-specific entries
                - default config entries
        """
        # Let's check we know what's needed
        self.check_input()

        self.debug('provision dir', self.provision_dir)

         # Check for working Vagrant
        self.run_vagrant('version')

        # if custom vagrantfile was provided
        if not self.custom_vagrantfile is None \
            and self.custom_vagrantfile != self.vagrantfile \
            and os.path.exists(self.custom_vagrantfile):
            shutil.copy(self.custom_vagrantfile, self.vagrantfile)

        # Don't setup Vagrantfile in case we are resuming, or custom
        # Vagrantfile was specified,
        if os.path.exists(self.vagrantfile) and os.path.isfile(self.vagrantfile):
            self.validate()
            return

        # Let's add what's needed
        # Important: run this first to install provider
        self.add_how()

        # Add default entries to Vagrantfile
        self.add_defaults()

    def check_input(self):
        """ Initialize configuration(no defaults), based on data (how, image).
            does not create Vagrantfile or add anything into it.
        """
        self.debug('VagrantProvider', 'Checking initial status, setting defaults.')

        if self.is_uri(self.image):
            if re.search(r"\.box$", self.image) is None:
                # an actual box file, Great!
                pass

            elif re.search(r"\.qcow2$", self.image) is None:
                # do some qcow2 magic
                self.box = '...'
                raise SpecificationError("NYI: QCOW2 image")

            else:
                raise SpecificationError(f"Image format not recognized: {self.image}")

        else:
            if self.box is None:
                self.box  = self.image
                self.image = None


    ## Knowhow ##
    def add_how(self):
        """ Add provider (in Vagrant-speak) specifics """
        getattr(self,
            f"how_{self.parent.how}",
            self.how_generic,
            )()
        self.validate()

    def how_generic(self):
        self.debug("generating", "generic")
        self.create()
        self.add_provider(self.parent.how)

    def how_libvirt(self):
        """ libvirt provider specifics
            Try adding QEMU session entry.
        """
        name = 'libvirt'
        self.debug("generating", name)

        self.plugin_install(name)

        self.gen_virtual(name)

        self.vf_backup("QEMU user session")
        self.add_provider(name, 'qemu_use_session = true')

        try:
            self.validate()
        except GeneralError as error:
            self.vf_restore()
            # Not really an error
            self.debug(error)

    def how_connect(self):
        """ Defines a connection to guest
            using managed provider from managed-servers plugin.
            Recreates Vagrantfile with dummy box.
        """
        name = 'connect'
        self.debug("generating", name)

        if self.guest is None:
            raise SpecificationError('Guest is not specified.')
        self.debug("guest", self.guest)

        self.plugin_install(f"managed-servers")

        self.box = self.dummy_image
        self.create()

        self.add_provider('managed', self.kve('server', self.guest))

        # Let's use the config.ssh setup first; this is backup:
        # => override.ssh.username
        # => override.ssh.private_key_path = ".vagrant/machines/local_linux/virtualbox/private_key"

    def how_container(self):
        self.debug("generating", "container")
        raise SpecificationError('NYI: cannot currently run containers.')

    def how_openstack(self):
        self.debug("generating", "openstack")
        raise SpecificationError('NYI: cannot currently run on openstack.')

    # Aliases
    def how_docker(self):
        self.how_container()

    def how_podman(self):
        self.how_container()

    def how_virtual(self):
        self.how_libvirt()


    ## END of API ##
    def gen_virtual(self, provider = ''):
        """ Add config entry for VM
            (re)creates Vagrantfile with
             - box
             - box_url
             - memory and provider(if provider is set)
        """
        self.create()

        if self.image:
            self.add_config('vm', self.kve("box_url", image))

        if provider:
            self.add_provider(provider, self.kve('memory', self.memory))

    def add_defaults(self):
        """ Adds default /generic/ config entries into Vagrantfile:
             - disable default sync
             - add sync for plan.workdir
             - add ssh config opts if set
             - disable nfs check
            and validates Vagrantfile
        """
        self.add_synced_folder(".", "/vagrant", 'rsync', 'disabled: true')

        dir = self.parent.plan.workdir
        self.add_synced_folder(dir, dir, self.sync_type)

        # Credentials are used for `how: connect` as well as for VMs
        if self.user:
          self.add_config('ssh', self.kve('username', self.user))
        if self.password:
            self.add_config('ssh', self.kve('password', self.password))
        if self.key:
            self.add_config('ssh', self.kve('private_key_path', self.key))

        self.add_config('nfs', 'verify_installed = false')

        # Enabling this fails with `how: connect`
        #self.add_config('ssh', 'insert_key = false')
        self.validate()

    def run_vagrant(self, *args):
        """ Run vagrant command and raise an error if it fails
              args = 'command args'
            or
              args = ['comand', 'args']
        """
        if len(args) == 0:
            raise RuntimeError("vagrant has to run with args")

        cmd = self.prepend(args, self.executable)

        # TODO: timeout = self.timeout ?,
        return self.run(cmd, cwd=self.provision_dir, shell=False)

    def add_synced_folder(self, sfrom, sto, stype, *sargs):
        """ Add synced_folder entry into Vagrantfile """
        self.add_config('vm',
            'synced_folder',
            quote(sfrom),
            quote(sto),
            self.kv('type', stype),
            *sargs)

    def add_provider(self, provider, *config):
        """ Add provider entry into Vagrantfile """
        self.add_config_block('provider', provider, *config)

    def add_config_block(self, name, block, *config):
        """ Add a config block into Vagrantfile
        """
        config_str = ''
        for c in config:
            config_str += f'{block}.{c}; '

        self.add_config('vm', f"{name} '{block}' do |{block}| {config_str}end")

    def add_config(self, type, *config):
        """ Add config entry into Vagrantfile right before last 'end',
            and prepends it with `config_prefix`.

            Adding arbitrary config entry:
                config = "string"
            or, with conversion:
                config = ['one', 'two', 'three']
                => one "two", three
        """
        if len(config) == 1:
            config = config[0]
        elif len(config) == 0:
            raise RuntimeError("config has no definition")
        else:
            config = f'{config[0]} ' + ', '.join(config[1:])

        self.debug('Adding into Vagrantfile', f"{type}.{config}", 'green')

        vf_tmp = self.vf_read()

        # Lookup last 'end' in Vagrantfile
        i = 0
        for line in reversed(vf_tmp):
            i -= 1
            # TODO: avoid infinite loop in case of invalid Vagrantfile
            if (line.find('end') != -1):
                break

        vf_tmp = vf_tmp[:i] \
            + [self.config_prefix + f"{type}." + config] \
            + vf_tmp[i:]

        self.vf_write(vf_tmp)

    def vf_read(self):
        """ read Vagrantfile
            also splits lines
        """
        return open(self.vagrantfile).read().splitlines()

    def vf_write(self, vf_tmp):
        """ write into Vagrantfile
            str or list
        """
        if type(vf_tmp) is list:
            vf_tmp = self.eol.join(vf_tmp)

        with open(self.vagrantfile, 'w', newline=self.eol) as f:
            f.write(vf_tmp)

    def vf_backup(self, msg=''):
        """ backup Vagrantfile contents to vf_data """
        if msg:
            self.info("Trying to enable", msg)
        self.msg = msg
        self.vf_data = self.vf_read()

    def vf_restore(self):
        """ restore Vagrantfile contents from vf_data"""
        if self.msg:
            self.info('Reverting', self.msg, 'red')
            self.msg = ''
        self.vf_write(self.vf_data)


    ## Helpers ##
    def info(self, key = '', val = '', color = 'blue', level = 1):
        """ info out!
            see msgout()
        """
        self.msgout('info', key, val, color, level)

    def verbose(self, key = '', val = '', color = 'green', level = 1):
        """ info out!
            see msgout()
        """
        self.msgout('verbose', key, val, color, level)

    def debug(self, key = '', val = '', color='yellow', level = 1):
        """ debugging, yay!
            see msgout()
        """
        self.msgout('debug', key, val, color, level)

    def msgout(self, mtype, key = '', val = '', color = 'red', level = 1):
        """ args: key, value, indent, color
            all optional
        """
        if type(val) is list and len(val):
            ind_val = ''
            for v in val:
                if v:
                    ind_val += ' '*self.default_indent + self.hr(v) + self.eol

            val = ind_val
        else:
            val = self.hr(val)

        emsg = lambda: RuntimeError(f"Message type unknown: {mtype}")

        # Call super.debug or super.info
        if val:
            getattr(super(), mtype, emsg)(key, val, color=color)
        else:
            getattr(super(), mtype, emsg)(key, color=color)

    def hr(self, val):
        """ return human readable data
             - converts bytes, tuples and lists
             - separates entries with newlines
             - runs recursively
             - tries to add eol
        """
        if type(val) is tuple or type(val) is list:
            ret = ''
            for v in val:
                ret += self.hr(v)
            return ret

        if type(val) is bytes:
            val = str(val, "utf-8")

        elif type(val) is not str:
            val = str(val)

        try:
            val = rstrip(val)
            eol = self.eol
        except:
            eol = ''

        return f'{val}{eol}'

    def prepend(self, thing, string):
        """ modify object to prepend it with string
            based on the type of object
             - tuple, list, string
             - adds a space for string
        """
        if type(thing) is list:
            return thing.insert(0, string)
        elif type(thing) is tuple:
            return (string ,) + thing
        else:
            return string + ' ' + thing

    def is_uri(self, uri):
        """ Check if string is an URI-parsable
            actually returns its 'scheme'
        """
        return getattr(urlparse(uri),
            'scheme',
            None)

    def kv(self, key, val, sep=': '):
        """ returns key-value decrorated
             - use separator
             - quote val
        """
        return f'{key}{sep}{quote(val)}'

    def kve(self, key, val, sep=' = '):
        """ returns key equals value
            see kv()
        """
        return self.kv(key, val, sep)

    def join(self, *args):
        if len(args) == 0:
            return ""
        elif len(args) == 1:
            args = args[0]

        return ' '.join(args)
