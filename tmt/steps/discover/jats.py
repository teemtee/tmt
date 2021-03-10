import os
import fmf
import tmt
import click
import shutil
import tmt.steps.discover
import yaml

from tmt import utils


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
        if self.get('local_dir'):
            # generate tests from local_dir
            directory = self.step.plan.run.tree.root
            test_path = '/tests/tests/jats'

            def _search_dir(test_dir, res):
                # check for actual test
                if os.path.isfile(os.path.join(test_dir, 'test')):
                    data = {}
                    test_suite, test_name = test_dir.split("/src/")
                    test_suite = test_suite.rsplit(os.path.sep)[-1].strip('jats-')
                    test_name = test_name.lstrip(os.path.sep)
                    # the test is there, no more subdir searching
                    # if main.fmf with test params is present - add it to the test description
                    main_fmf = os.path.join(test_dir, 'main.fmf')
                    jats_testdata = {}
                    if os.path.isfile(main_fmf):
                        with open(main_fmf) as f:
                            jats_testdata = yaml.load(f, Loader=yaml.FullLoader)
                    # generate data for the tmt test
                    data['duration'] = jats_testdata.get('duration', jats_testdata.get('timeout', '15m'))
                    data['summary'] = "Run jats-{} {} tests".format(test_suite, test_name)
                    data['test'] = 'bash ./test.sh'
                    data['path'] = test_path
                    data['framework'] = 'shell'
                    data['environment'] = {'TESTSUITE': test_suite, 'TESTNAME': test_name}
                    data['tier'] = test_name.split(os.path.sep)[0]
                    data['name'] = '/integration/{}/{}'.format(test_suite, test_name)
                    res.append(data)
                else:
                    dirs = [os.path.join(test_dir, f) for f in os.listdir(test_dir)
                            if os.path.isdir(os.path.join(test_dir, f)) and not f.startswith('.') and
                            not f.startswith('_')]
                    for a_dir in dirs:
                        _search_dir(a_dir, res)
                return res

            tests_data = _search_dir(os.path.join(self.get('local_dir'), 'src'), [])
            # apply filters
            # XXX FIXME figure out how to respect options specified via cli
            filters = utils.listify(self.get('filter', []))
            tests_data = [t for t in tests_data
                          if all([fmf.utils.filter(a_filter, t, regexp=True) for a_filter in filters])]
            # create tmt workdir
            if tests_data:
                test_path = os.path.join(self.workdir, test_path.lstrip('/'))
                os.makedirs(test_path)
            # copy test.sh script
            test_sh = os.path.join(directory, 'tests/jats', 'test.sh')
            shutil.copyfile(test_sh, os.path.join(test_path, 'test.sh'))
            # create tmt Test objects
            self._tests = [tmt.Test(data=test, name=test.pop('name')) for test in tests_data]
        else:
            # use hardcoded test cases and hope nothing new has been added
            directory = self.step.plan.run.tree.root
            tree = tmt.Tree(path=directory, context=self.step.plan._fmf_context())

            # Show filters and test names if provided
            filters = utils.listify(self.get('filter', []))
            names = utils.listify(self.get('test', []))
            self._tests = tree.tests(filters=filters, names=names)
            # Copy directory tree (if defined) to the workdir
            testdir = os.path.join(self.workdir, 'tests')
            shutil.copytree(directory, testdir, symlinks=True)

    def tests(self):
        return self._tests
