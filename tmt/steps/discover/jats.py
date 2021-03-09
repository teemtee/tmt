import os
import fmf
import tmt
import click
import shutil
import tmt.steps.discover
import yaml

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
                    data['duration'] = jats_testdata.get('timeout', '15m')
                    data['summary'] = "Run jats-{} {} tests".format(test_suite, test_name)
                    data['test'] = './test.sh'
                    data['path'] = '/tests/tests/jats'
                    data['framework'] = 'shell'
                    data['environment'] = {'TESTSUITE': test_suite, 'TESTNAME': test_name}
                    data['tier'] = 'jats-{}'.format(test_suite)
                    data['name'] = '/integration/{}/{}'.format(test_suite, test_name)
                    res.append(data)
                else:
                    for root, dirs, files in os.walk(test_dir):
                        for a_dir in [d for d in dirs if not d.startswith('.') and not d.startswith('_')]:
                            _search_dir(os.path.join(root, a_dir), res)
                return res

            # XXX FIXME Add support for names and filters
            tests_data = _search_dir(os.path.join(self.get('local_dir'), 'src'), [])
            # write generated tmt test files to the workdir
            if tests_data:
                # create test dir
                test_path = os.path.join(self.workdir, tests_data[0]['path'].lstrip('/'))
                os.makedirs(test_path)
            for test in tests_data:
                with open(os.path.join(
                    test_path, "{}.fmf".format(test['name'].lstrip('/').replace('/', '-'))), 'w') as f:
                    f.write(yaml.dump(test))
            # copy test.sh script
            test_sh = os.path.join(self.step.plan.run.tree.root, 'tests/jats', 'test.sh')
            shutil.copyfile(test_sh, os.path.join(test_path, 'test.sh'))
            self._tests = [tmt.Test(data=test, name=test.pop('name')) for test in tests_data]
        else:
            # use hardcoded test cases and hope nothing new has been added
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
