from tmt.steps.execute.shell import ExecutorShell

""" Beakerlib Executor Provider Class """


class ExecutorBeakerlib(ExecutorShell):
    """ Run tests using how: beakerlib """

    def __init__(self, execute_step):
        super(ExecutorBeakerlib, self).__init__(execute_step)

    def go(self, tests):
        """ Run tests """
        super(ExecutorBeakerlib, self).go(tests)

    # API
    def requires(self):
        """ Returns packages required to run tests"""
        super(ExecutorBeakerlib, self).requires()
        packages = (
            'beakerlib',
        )
        return packages

    def results(self):
        """ Returns results from executed tests """
        super(ExecutorBeakerlib, self).results()
