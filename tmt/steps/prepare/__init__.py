# coding: utf-8

""" Prepare Step Class """

import tmt
import os
import shutil
import subprocess

from click import echo

from tmt.utils import GeneralError, ConvertError

class Prepare(tmt.steps.Step):
    name = 'prepare'

    def __init__(self, data, plan):
        """ Initialize the Prepare step """
        self.super = super(Prepare, self)
        self.super.__init__(data, plan)

    def wake(self):
        """ Wake up the step (process workdir and command line) """
        self.super.wake()

        for i in range(len(self.data)):
            self.opts(i, 'how', 'script')

            self.alias(i, 'script', 'playbooks')
            self.alias(i, 'script', 'playbook')
            self.alias(i, 'script', 'path')
            self.alias(i, 'script', 'inline')

            self.debug('how', self)

            for key, val in self.data[i].items():
                if not val is None:
                    self.info(f'{key}', val)

    def show(self):
        """ Show discover details """
        self.super.show(keys = ['how', 'script'])

    def go(self):
        """ Prepare the test step """
        self.super.go()

        for data in self.data:
            how = data['how']
            script = data['script']

            if script:
                self.verbose('    Prepare', f"{how} = '{script}", 'yellow')

                try:
                    self.plan.provision.prepare(how, script)
                except AttributeError as error:
                    raise SpecificationError('NYI: cannot currently run this preparator.')

            else:
                self.debug('Note', f"No path/script defined for prepare({how})", 'yellow')

        # TODO: find a better way
        packages = self.plan.execute.requires()
        if not packages:
            return

        failed = False
        logf = os.path.join(self.workdir, 'prepare.log')
        try:
            self.plan.provision.prepare('shell', f"dnf install -y {' '.join(packages)} 2>&1 | tee -a '{logf}'")
        except GeneralError:
            failed = True

        self.plan.provision.sync_workdir_from_guest()
        if failed:
            raise ConvertError(f'Prepare failed:\n{open(logf).read()}')

    def set_default(self, i, where, default):
        if not (where in self.data[i] and self.data[i][where]):
            self.data[i][where] = default

    def opts(self, i, *keys):
        for key in keys:
            val = self.opt(key)
            if val:
                self.data[i][key] = val

    def alias(self, i, where, name):
        self.set_default(i, where, self.opt(name))
        val = self.data[i].get(name)
        if not val is None:
            self.set_default(i, where, val)
