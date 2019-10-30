from tmt.steps.execute.shell import ExecutorShell

""" Beakerlib Executor Provider Class """


class ExecutorBeakerlib(ExecutorShell):
    """ Run tests using how: beakerlib """

    def __init__(self,  data, step=None, name=None):
        super(ExecutorBeakerlib, self).__init__(data, step, name)

    def go(self):
        """ Run tests """
        super(ExecutorBeakerlib, self).go()

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
