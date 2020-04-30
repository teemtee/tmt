import os
import click
import tmt

# The default playbook used to run the tests
DEFAULT_PLAYBOOK = 'tests/tests.yml'

# Ansible inventory file required to run the tests
ANSIBLE_INVENTORY = """
[localhost]
sut  ansible_host={hostname} ansible_user=root ansible_remote_tmp={remote_tmp}
"""


class ExecutorSTI(tmt.steps.execute.ExecutePlugin):
    """ Run tests using ansible according to Standard Test Interface spec """
    _doc = """
    Execute STI tests

    An inventory file is prepared according to the STI specification
    and ansible-playbook is used to run the given playbook.
    """

    # Supported methods
    _methods = [
        tmt.steps.Method(
            name='sti', doc=_doc, order=50),
        ]

    @classmethod
    def options(cls, how=None):
        """ Prepare command line options for given method """
        options = []
        if how == 'sti':
            options.append(click.option(
                '-p', '--playbook', metavar='PLAYBOOK',
                help=f"""
                    Ansible playbook to be run as a test.
                    By default '{DEFAULT_PLAYBOOK}'
                """))
        return options + super().options(how)

    def show(self):
        """ Show discover details """
        super().show(['playbook'])

    def default(self, option, default=None):
        """ Return the default value for the given option """
        defaults = {
            'playbook': DEFAULT_PLAYBOOK
        }
        playbook = defaults.get(option, default)

        if not os.path.exists(playbook):
            raise tmt.utils.GeneralError(f"Playbook '{playbook}' not found.")

        return playbook

    def _inventory(self, guest):
        """ Provides Ansible inventory compared to STI """
        hostname = guest.guest or guest.container

        inventory_file = os.path.join(
            self.step.workdir, f'inventory-{hostname}')
        # Note that we have to force remote_tmp because in rootless container
        # it would default to '/root/.ansible/tmp' which is
        # not accessible by ordinary users
        inventory_content = ANSIBLE_INVENTORY.format(
            hostname=hostname,
            remote_tmp=os.path.expanduser('~/.ansible/tmp')
        )

        with open(inventory_file, 'w') as inventory:
            inventory.write(inventory_content)

        return inventory_file

    def wake(self):
        """ Wake up the plugin (override data with command line) """

        value = self.opt('playbook')
        if value:
            self.data['playbook'] = value

    def go(self):
        """ Execute available tests """
        super().go()

        # Nothing to do in dry mode
        if self.opt('dry'):
            self._results = []
            return

        for guest in self.step.plan.provision.guests():
            guest.ansible(
                self.opt('playbook'),
                inventory=self._inventory(guest),
                options=f'-e artifacts={self.step.workdir}'
            )

    def results(self):
        """ Returns results from executed tests """
        return []

    def requires(self):
        """ No packages are required """
        return []
