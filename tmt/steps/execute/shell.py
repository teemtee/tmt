from tmt.steps.execute.base import ExecutorBase

""" Shell Executor Provider Class """


class ExecutorShell(ExecutorBase):
    """ Run tests using how: shell """

    def __init__(self, execute_step):
        super(ExecutorShell, self).__init__(execute_step)

    def go(self, tests):
        """ Run tests """
        super(ExecutorShell, self).go(tests)

    # API
    def requires(self):
        """ Returns packages required to run tests"""
        super(ExecutorShell, self).requires()
        return ()

    def results(self):
        """ Returns results from executed tests """
        super(ExecutorShell, self).results()
