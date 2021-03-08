import os
import fmf
import tmt
import click
import shutil
import tmt.steps.discover

class DiscoverJats(tmt.steps.discover.DiscoverPlugin):
    """
    Use provided list of shell script tests

    List of test cases to be executed can be defined manually directly
    in the plan as a list of dictionaries containing test name, actual
    test script and optionally a path to the test. Example config:

    discover:
        how: jats
        tests:
        - name: /help/main
          test: tmt --help
        - name: /help/test
          test: tmt test --help
        - name: /help/smoke
          test: ./smoke.sh
          path: /tests/shell
    """

    # Supported methods
    _methods = [tmt.steps.Method(name='jats', doc=__doc__, order=60)]

    def show(self):
        """ Show config details """
        super().show([])
        tests = self.get('tests')
        if tests:
            test_names = [test['name'] for test in tests]
            click.echo(tmt.utils.format('tests', test_names))

    def wake(self):
        # Check provided tests, default to an empty list
        if 'tests' not in self.data:
            self.data['tests'] = []
        self._tests = []

    def go(self):
        """ Discover available tests """
        super(DiscoverJats, self).go()
        directory = self.step.plan.run.tree.root
        tree = tmt.Tree(path=directory, context=self.step.plan._fmf_context())

        # Show filters and test names if provided
        filters = self.get('filter', [])
        names = self.get('test', [])
        # XXX FIXME tmt run -a provision  -h connect -g 10.0.78.255 plans --name "integration-leapp-repository"
        # results in filter being passed as a string instead of a list. So workarounding not to return [] from
        # tree.tests()
        if isinstance(filters, str):
            filters = [filters]
        self._tests = tree.tests(filters=filters, names=names)
        # Copy directory tree (if defined) to the workdir
        testdir = os.path.join(self.workdir, 'tests')
        shutil.copytree(directory, testdir, symlinks=True)

    def tests(self):
        return self._tests
