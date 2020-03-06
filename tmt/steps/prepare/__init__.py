# coding: utf-8

""" Prepare Step Class """

import tmt
import os
import shutil
import subprocess
import re

from click import echo
from urllib.parse import urlparse

from tmt.utils import GeneralError, SpecificationError

class Prepare(tmt.steps.Step):
    name = 'prepare'
    eol = '\n'

    valid_inputs = { 'shell': ['script'],
                     'install': ['package', 'packages', 'url'],
                     'ansible': ['playbook', 'playbooks']
                   }

    ## Default API ##
    def __init__(self, data, plan):
        """ Initialize the Prepare step """
        self.super = super(Prepare, self)
        self.super.__init__(data, plan)

    def wake(self):
        """ Wake up the step (process workdir and command line) """
        self.super.wake()

        for i in range(len(self.data)):
            self.opts(i, 'how', 'input', 'copr')
            how = self.data[i]['how']

            # Aliases for 'input'; or the WHAT is to be applied
            for key in self.valid_inputs:
                for alt in self.valid_inputs[key]:
                    value = self.alias(i, 'input', alt)

                    if value and key != how:
                        raise SpecificationError(f"You cannot specify {alt} for {how}.")

    def show(self):
        """ Show discover details """
        self.super.show(keys = ['how', 'input', 'copr'])

    def go(self):
        """ Prepare the test step """
        # TODO: not sure why
        self.super.go()

        for dat in self.data:
            self.run_how(dat)

        packages = []
        for step in self.plan.steps():
            if hasattr(step, 'requires'):
                packages += step.requires()

        if packages:
            self.debug(f'Installing steps requires', ', '.join(packages))
            self.install(packages)


    ## Knowhow ##
    def run_how(self, dat):
        """ Run specific HOW """
        input = dat['input']
        if not input:
            self.debug('note', f"No data provided for prepare.", 'yellow')
            return
        self.debug('input', input, 'yellow')

        if 'copr' in dat:
            self.copr(dat['copr'])

        how = dat['how']
        getattr(self, f"how_{how}", self.how_generic)(how, input)

    def how_generic(self, how, what):
        """ Handle a generic 'Prepare',
            which is relayed to provider's prepare().
        """
        # Process multiple inputs
        if type(what) is list:
            return [self.how_generic(how, w) for w in what]

        # Try guesssing the path (1)
        whatpath = os.path.join(self.plan.run.tree.root, what)
        self.debug('Looking for prepare script in', self.plan.run.tree.root)

        if os.path.exists(whatpath) and os.path.isfile(whatpath):
            what = whatpath

        else:
            # Try guesssing the path (2)
            base = os.path.join(self.plan.workdir,
                'discover',
                self.data[0]['name'],
                'tests')
            whatpath = os.path.join(base, what)
            self.debug('Looking for prepare script in', base)

            if os.path.exists(whatpath) and os.path.isfile(whatpath):
                what = whatpath

            elif how == 'shell':
                return self.command(what)

        try:
            self.plan.provision.prepare(how, what)
        except AttributeError as error:
            raise SpecificationError('NYI: cannot currently run this preparator.')

    def how_install(self, how, what):
        """ Install packages
            handles various URIs or packages themselves
        """
        if not type(what) is list:
            return self.install(what)

        rest = []
        for wha in what:
            if self.is_uri(wha):
                domain = self.get_uri(wha).netloc
                if not re.search(r"^koji\.", domain) is None:
                    self.how_koji('koji', how, what)
                    continue
                if not re.search(r"^brew\.", domain) is None:
                    self.how_koji('brew', how, what)
                    continue

            rest += wha
        self.install(rest)

    def how_koji(self, com, how, what):
        """ Download and install packages from koji URI """
        what_uri = self.get_uri(what)

        if what_uri:
            query = self.get_query(what_uri)

            if not 'buildID' in query:
                raise SpecificationError(f"No buildID found in: {what}")

            build = query['buildID']

        else:
            self.debug(f"Could not parse URI, assuming buildID was given.")
            build = what

        self.install(com)

        install_dir = os.path.join(self.workdir, 'install')
        self.command(f"{self.cmd_mkcd(install_dir)}; {com} download-build -a noarch -a x86_64 {build}; dnf install --skip-broken -y *.rpm; rm *.rpm")


    ## Additional API ##
    def copr(self, copr):
        """ Enable copr repository """
        self.debug(f'Enabling copr repository', copr)
        # Shouldn't be needed
        # self.install('dnf-command(copr)')
        return self.command(f"sudo dnf copr list --enabled | grep -qE '(^|\/){copr}$' || sudo dnf copr -y enable {copr}")

    def install(self, packages):
        """ Install specified package(s)
        """
        if type(packages) is list:
            packages = [
                self.quote(package) for package in packages
            ]
            packages = ' '.join(packages)
        else:
            packages = self.quote(packages)

        return self.command(f"rpm -V {packages} || sudo dnf install -y {packages}")

    def command(self, command, logfile=True):
        failed = False
        logf = os.path.join(self.workdir, 'prepare.log')

        comf = os.path.join(self.workdir, 'command.sh')
        comd = [
              'set -x',
              command,
              'exit $?',
              ''
            ]
        with open(comf, 'w', newline=self.eol) as f:
            f.write(self.eol.join(comd))
        os.chmod(comf, 0o700)

        if type(logfile) is str and logfile:
            logf = logfile

        self.plan.provision.sync_workdir_to_guest()
        try:
            if logfile:
                self.plan.provision.prepare('shell',
                    f"set -o pipefail; bash '{comf}' 2>&1 | tee -a '{logf}'")
            else:
                self.plan.provision.prepare('shell', comf)
        except GeneralError:
            failed = True

        self.plan.provision.sync_workdir_from_guest()

        if failed:
            if logfile:
                output = '\nlog:\n' + open(logf).read()
            else:
                output = command
            raise GeneralError(f'Command failed: ' + output)


    ## END of API ##


    ## Helpers ##
    def set_default(self, i, where, default):
        """ Set `self.data[i]` entry if not set already or if empty.
            It needs an index specified as self.data is a list.
            Returns the value if set, '' otherwise.
        """
        if where in self.data[i] and self.data[i][where]:
            return ''
        else:
            self.data[i][where] = default
            return default

    def opts(self, i, *keys):
        """ Load opts into data[i][]
            It needs an index specified as self.data is a list.
            By the same key.
        """
        for key in keys:
            val = self.opt(key)
            if val:
                self.data[i][key] = val

    def alias(self, i, where, name):
        """ Maps additional data and opt entry onto a different one.
            It needs an index specified as self.data is a list.
            Actually Runs set_default based on entry in opt() and data[].
            Returns the selected value or ''
        """
        val = self.set_default(i, where, self.opt(name))

        if not val and name in self.data[i]:
            val = self.set_default(i, where, self.data[i][name])

        return val

    def get_uri(self, what):
        """ Return parsed URI if parsable,
            Otherwise returns ''.
            See is_uri().
        """
        if self.is_uri(what):
            what_uri = urlparse(what)
            for pr in ('netloc', 'path', 'query'):
                self.debug(f'URI {pr}', getattr(what_uri, pr))
            return what_uri
        else:
            return ''

    def is_uri(self, uri):
        """ Check if string is an URI-parsable
            actually returns its 'scheme'
        """
        return getattr(urlparse(uri),
            'scheme',
            None)

    def get_query(self, what_uri):
        """ Returns dict from parsed URI's query.
            See get_uri().
        """
        return dict(que.split("=") for que in what_uri.query.split("&"))

    def cmd_mkcd(self, target_dir):
        """ return string containing shell
            commands to create dir and copy a target in there
        """
        target_dir = self.quote(target_dir)
        return f'mkdir -p {target_dir}; cd {target_dir}'

    def quote(self, string):
        """ returns string decorated with squot """
        return f"'{string}'"
