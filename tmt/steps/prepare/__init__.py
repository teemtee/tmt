# coding: utf-8

""" Prepare Step Class """

import tmt
import os
import shutil
import subprocess

from tmt.utils import ConvertError, StructuredFieldError, SpecificationError, GeneralError

from click import echo

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
            self.set_default(i, 'how', 'shell')
            self.set_default(i, 'playbooks', [])
            self.set_default(i, 'path', self.data[i]['playbooks'])
            self.set_default(i, 'script', self.data[i]['path'])

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
                self.plan.provision.prepare(how, script)
            else:
                self.debug('Note', f"No path/script defined for prepare({how})", 'yellow')

        # TODO: find a better way
        for package in self.plan.execute.requires():
            self.plan.provision.execute('dnf', 'install', '-y', package)

    def set_default(self, i, where, default):
        if not (where in self.data[i] and self.data[i][where]):
            self.data[i][where] = default
