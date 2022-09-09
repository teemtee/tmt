from typing import Any, Optional

import click

import tmt
import tmt.steps.prepare
import tmt.utils
from tmt.steps.provision import Guest


class PrepareRepository(tmt.steps.prepare.PreparePlugin):
    """
    Prepare custom repository
    Example config:
    prepare:
        how: repository
        name: Local repository
        baseurl: file:///repository
        gpgcheck: 0
        gpgkey: file:///gpgkey
        skip-if-unavailable: 1
        order: 1
        priority: 99
    """

    # Supported methods
    _methods = [tmt.steps.Method(name='repository', doc=__doc__, order=50)]

    # Supported keys
    _keys = ["name", "baseurl", "gpgcheck", "gpgkey", "skip-if-unavailable", "order", "priority"]

    @classmethod
    def options(cls, how: Optional[str] = None) -> Any:
        """ Prepare command line options """
        return [
            click.option(
                '-n', '--name', metavar='NAME',
                help='Set name of repository.'),
            click.option(
                '-u', '--baseurl', metavar='BASEURL',
                help='Set baseurl of the repository.'),
            click.option(
                '-g', '--gpgcheck', metavar='GPGCHECK',
                help='Set gpgcheck of the repository.'),
            click.option(
                '-k', '--gpgkey', metavar='GPGKEY',
                help='Set gpgcheck of the repository.'),
            click.option(
                '-s', '--skip-if-unavailable', metavar='SKIP_IF_UNAVAILABLE',
                help='Set skip-if-unavailable of the repository.'),
            click.option(
                '-o', '--order', metavar='ORDER',
                help='Set order of the repository.'),
            click.option(
                '-p', '--priority', metavar='PRIORITY',
                help='Set priority of the repository.')
            ] + super().options(how)

    def default(self, option: str, default: Optional[Any] = None) -> Any:
        """ Return default data for given option """
        if option == 'name':
            return "Repository"
        if option == 'baseurl':
            return "file:///repository"
        if option == 'gpgcheck':
            return 0
        if option == 'gpgkey':
            return "file:///gpgkey"
        if option == 'skip-if-unavailable':
            return 1
        if option == 'order':
            return 1
        if option == 'priority':
            return 99
        return default

    def wake(self) -> None:
        """ Wake up the plugin, process data, apply options """
        super().wake()

        # Convert to list if necessary
        """
        tmt.utils.listify(
            self.data, split=True,
            keys=['name', 'baseurl', 'order', 'priority'])
        """

    def go(self, guest: Guest) -> None:
        """ Prepare the guests """
        super().go(guest)

        self.info("Add repository into '/etc/yum.repos.d'.")
        repo_path = "/etc/yum.repos.d/demo.repo"
        guest.execute(f"touch {repo_path}")
        guest.execute(f'echo "[demo]" >> {repo_path}')
        for key in self._keys:
            guest.execute(f'echo "{key}={self.get(key)}" >> {repo_path}')
