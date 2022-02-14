import tempfile

import click
import requests

import tmt
from tmt.utils import PrepareError, retry_session


class PrepareAnsible(tmt.steps.prepare.PreparePlugin):
    """
    Prepare guest using ansible

    Single playbook config:

        prepare:
            how: ansible
            playbook: ansible/packages.yml

    Multiple playbooks config:

        prepare:
            how: ansible
            playbook:
              - playbook/one.yml
              - playbook/two.yml
              - playbook/three.yml
            extra-args: '-vvv'

    Remote playbooks can be referenced as well as local ones, and both kinds be intermixed:

        prepare:
            how: ansible
            playbook:
              - playbook/one.yml
              - https://foo.bar/two.yml
              - playbook/three.yml
            extra-args: '-vvv'

    The playbook path should be relative to the metadata tree root.
    Use 'order' attribute to select in which order preparation should
    happen if there are multiple configs. Default order is '50'.
    Default order of required packages installation is '70'.
    """

    # Supported methods
    _methods = [tmt.steps.Method(name='ansible', doc=__doc__, order=50)]

    # Supported keys
    _keys = ["playbook", "extra-args"]

    def __init__(self, step, data):
        """ Store plugin name, data and parent step """
        super().__init__(step, data)
        # Rename plural playbooks to singular
        if 'playbooks' in self.data:
            self.data['playbook'] = self.data.pop('playbooks')

    @classmethod
    def options(cls, how=None):
        """ Prepare command line options """
        return [
            click.option(
                '-p', '--playbook', metavar='PLAYBOOK', multiple=True,
                help='Path or URL of an ansible playbook to run.'),
            click.option(
                '--extra-args', metavar='EXTRA-ARGS',
                help='Optional arguments for ansible-playbook.')
            ] + super().options(how)

    def default(self, option, default=None):
        """ Return default data for given option """
        if option == 'playbook':
            return []
        return default

    def wake(self, keys=None):
        """ Wake up the plugin, process data, apply options """
        super().wake(keys=keys)

        # Convert to list if necessary
        tmt.utils.listify(self.data, keys=['playbook'])

    def go(self, guest):
        """ Prepare the guests """
        super().go()

        # Apply each playbook on the guest
        for playbook in self.get('playbook'):
            self.info('playbook', playbook, 'green')

            lowercased_playbook = playbook.lower()
            playbook_path = playbook

            if lowercased_playbook.startswith(
                    'http://') or lowercased_playbook.startswith('https://'):
                try:
                    response = retry_session().get(playbook)

                    if not response.ok:
                        raise PrepareError(
                            f"failed to fetch remote playbook '{playbook}'")

                except requests.RequestException as exc:
                    raise PrepareError(
                        f"failed to fetch remote playbook '{playbook}'", original=exc)

                with tempfile.NamedTemporaryFile(mode='w+b', prefix='playbook-', suffix='.yml', dir=None, delete=False) as f:
                    f.write(response.content)
                    f.flush()

                    playbook_path = f.name

                self.info('playbook-path', playbook_path)

            guest.ansible(playbook_path, self.get('extra-args'))
