# coding: utf-8

""" Prepare Step Class """

import tmt
import os
import shutil
import subprocess

from click import echo

from tmt.utils import GeneralError, ConvertError, SpecificationError

class Prepare(tmt.steps.Step):
    name = 'prepare'

    ## Default API ##
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
        # TODO: not sure why
        self.super.go()

        packages = []
        for step in self.plan.steps():
            if getattr(step, 'requires', False):
                packages += step.requires()

        if packages:
            self.install(packages)

        for data in self.data:
            self.run_how(data['how'], data['script'])


    ## Knowhow ##
    def run_how(self, how, what):
        """ Run specific HOW """
        self.info('Prepare', f"{how} = '{what}", 'yellow')
        getattr(self,
            f"how_{how}",
            lambda: 'generic',
            )(how, what)

    def how_generic(self, how, what):
        if not what:
            self.debug('Note', f"No data provided for prepare({how})", 'yellow')
            return

        # Process multiple inputs
        if type(what) is list:
            return [self.how_generic(how, w) for w in what]

        # Try guesssing the path
        whatpath = os.path.join(self.plan.run.tree.root, what)

        self.debug('Looking for prepare script in', whatpath)
        if os.path.exists(whatpath) and os.path.isfile(whatpath):
            what = whatpath
        else:
            whatpath = os.path.join(self.plan.workdir,
                'discover',
                self.data['name'],
                'tests',
                what)

            self.debug('Looking for prepare script', whatpath)
            if os.path.exists(whatpath) and os.path.isfile(whatpath):
                what = whatpath

        try:
            self.plan.provision.prepare(how, packages)
        except AttributeError as error:
            raise SpecificationError('NYI: cannot currently run this preparator.')


    def how_install(self, how, what):
        """ Install packages from some source """
        what_uri = self.get_uri(what)
        if what_uri:
            if not re.search(r"^koji\.", what_uri.netloc) is None:
                return self.how_koji(how, what, what_uri)

            if not re.search(r"^brew\.", what_uri.netloc) is None:
                return self.how_brew(how, what, what_uri)

        self.install(what)

    def how_koji(self, how, what, what_uri=''):
        if not what_uri:
            what_uri = self.get_uri(what)

        if what_uri:
            query = get_query(what_uri)

            if not 'buildID' in query:
                raise SpecificationError(f"No buildID found in: {what}")

            build = query['buildID']

        else:
            self.info(f"Could not parse URI, assuming buildID was given.")
            build = what

        self.install('koji')
        return self.prepare('shell', f'`pwd`; set -xe; koji download-task -a noarch -a x86_64 {build} && ls *')

    def how_brew(self, how, what):
        raise SpecificationError(f"NYI: Cannot currenlty install brew builds.")


    ## Additional API ##
    def install(self, packages):
        if type(packages) is list:
            packages = ' '.join(packages)

        failed = False
        logf = os.path.join(self.workdir, 'prepare.log')
        try:
            self.plan.provision.prepare('shell', f"set -o pipefail; dnf install -y {packages} 2>&1 | tee -a '{logf}'")

        except GeneralError:
            failed = True

        self.plan.provision.sync_workdir_from_guest()

        output = open(logf).read()

        if failed:
            raise GeneralError(f'Install failed:\n{output}')

        self.debug(logf, output, 'yellow')


    ## END of API ##


    ## Helpers ##
    def get_query(self, what_uri):
        return dict(que.split("=") for que in what_uri.query.split("&"))

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
        if name in self.data[i]:
            self.set_default(i, where, self.data[i][name])

    def get_uri(self, what):
        if self.is_uri(what):
            what_uri = urlparse(what)
            for pr in ('netloc', 'path', 'query'):
                self.debug(f'URI {pr}', getattr(what_uri, pr))
            return what_uri
        else:
            return ''
