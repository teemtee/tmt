import click
import fmf

import tmt


class PrepareShell(tmt.steps.prepare.PreparePlugin):
    """
    Prepare guest using shell scripts

    Example config:

    prepare:
        how: shell
        script:
        - sudo dnf install -y 'dnf-command(copr)'
        - sudo dnf copr enable -y psss/tmt
        - sudo dnf install -y tmt

    Use 'order' attribute to select in which order preparation should
    happen if there are multiple configs. Default order is '50'.
    Default order of required packages installation is '70'.
    """

    # Supported methods
    _methods = [tmt.steps.Method(name='shell', doc=__doc__, order=50)]

    @classmethod
    def options(cls, how=None):
        """ Prepare command line options """
        return [
            click.option(
                '-s', '--script', metavar='SCRIPT',
                help='Shell script to be executed.')
            ] + super().options(how)

    def default(self, option, default=None):
        """ Return default data for given option """
        if option == 'script':
            return []
        return default

    def show(self):
        """ Show provided scripts """
        super().show(['script'])

    def wake(self, data=None):
        """ Override options and wake up the guest """
        super().wake(['script'])

        # Convert to list if single script provided
        tmt.utils.listify(self.data, keys=['script'])

    def go(self, guest):
        """ Prepare the guests """
        super().go()

        # Give a short summary
        scripts = self.get('script')
        overview = fmf.utils.listed(scripts, 'script')
        self.info('overview', f'{overview} found', 'green')

        # Execute each script on the guest
        for script in scripts:
            self.verbose('script', script, 'green')
            guest.execute(script, cwd=self.step.plan.worktree)
