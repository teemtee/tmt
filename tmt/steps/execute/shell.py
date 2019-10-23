from tmt.steps.execute.base import ExecutorBase

""" Shell Executor Provider Class """


class ExecutorShell(ExecutorBase):
    """ Run tests using how: shell """

    def __init__(self, data, plan):
        super(ExecutorShell, self).__init__(data, plan)

    def go(self, tests):
        super(ExecutorShell, self).go(tests)

