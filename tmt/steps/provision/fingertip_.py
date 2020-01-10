""" fingertip provisioning step: https://github.com/t184256/fingertip """

# import fingertip  -  avoid importing until one attempts to use it

import atexit
import os

from tmt.steps.provision.base import ProvisionBase
from tmt.utils import GeneralError, SpecificationError


# TODO: persist a running machine for run resumptions with run -i

class ProvisionFingertip(ProvisionBase):
    def __init__(self, data, step, instance_name=None):
        import fingertip as _  # fail if fingertip is not installed
        super().__init__(data, step, instance_name=instance_name)

        self._prepare_map = {
            'ansible': self._prepare_ansible,
            'shell': self._prepare_shell,
        }

        # TODO: options, e.g., RAM size

    def load(self):
        """ Load ProvisionFingertip step """
        super().load()
        raise SpecificationError('NYI: ProvisionFingertip.load')

    def save(self):
        """ Save ProvisionFingertip step """
        super().save()
        raise SpecificationError('NYI: ProvisionFingertip.save')

    def go(self):
        """ Build, cache and spin up a VM """
        import fingertip
        # TODO: make configurable
        m = (fingertip.build('os.fedora')
             .apply('ansible', 'package', name='rsync', state='present')
             .apply('ansible', 'package', name='beakerlib', state='present')
             .apply('unseal')
             .apply('.hooks.disable_proxy')
             .transient())
        m.__enter__()
        self.cb = atexit.register(lambda: m.__exit__(None, None, None))
        self.m = m

    def execute(self, *args):
        """ executes one command in a guest """
        self.debug('execute', args)
        r = self.m(self.join(args), check=False, dedent=False)
        self.debug('got', r.retcode, r.out)
        return r.retcode

    def show(self):
        """ Show some info about the running instance """
        raise SpecificationError('NYI: ProvisionFingertip.show')

    def sync_workdir_to_guest(self):
        # TODO: use ansible instead?
        self.debug('sync_workdir_to_guest')
        opts = '-e "' + ' '.join(['ssh', '-p', f'{self.m.ssh.port}',
                                  '-i', self.m.ssh.key_file,
                                  '-o', 'StrictHostKeyChecking=no',
                                  '-o', 'UserKnownHostsFile=/dev/null',
                                  '-o', 'GSSAPIAuthentication=no',
                                  '-o', 'GSSAPIKeyExchange=no']) + '"'
        assert '/var/tmp/tmt' in self.step.plan.workdir
        self.m(f'mkdir -p {self.step.plan.workdir}')
        self.run(f'rsync -ar --del {opts} {self.step.plan.workdir}/ '
                 f'root@localhost:{self.step.plan.workdir}')

    def sync_workdir_from_guest(self):
        # TODO: use ansible instead?
        self.debug('sync_workdir_from_guest')
        opts = '-e "' + ' '.join(['ssh', '-p', f'{self.m.ssh.port}',
                                  '-i', self.m.ssh.key_file,
                                  '-o', 'StrictHostKeyChecking=no',
                                  '-o', 'UserKnownHostsFile=/dev/null',
                                  '-o', 'GSSAPIAuthentication=no',
                                  '-o', 'GSSAPIKeyExchange=no']) + '"'
        assert '/var/tmp/tmt' in self.step.plan.workdir
        os.makedirs(self.step.plan.workdir, exist_ok=True)
        self.run(f'rsync -ar --del {opts} '
                 f'root@localhost:{self.step.plan.workdir}/ '
                 f'{self.step.plan.workdir}')

    def _prepare_shell(self, what):
        r = self.m(what, check=False, dedent=False)
        if r.retcode:
            raise GeneralError(f'shell prepare failed with {r.retcode}')

    def _prepare_ansible(self, what):
        import fingertip.plugins.ansible
        playbook = os.path.join(self.step.plan.run.tree.root, what)
        fingertip.plugins.ansible.playbook(self.m, playbook)

    def prepare(self, how, what):
        """ Run prepare phase """
        try:
            self._prepare_map[how](what)
        except AttributeError:
            raise SpecificationError(f"Prepare method '{how}' "
                                     "is not supported.")

    def destroy(self):
        """ destroy the machine """
        self.m.__exit__(None, None, None)
        atexit.unregister(self.cb)
        super().destroy()
