from tmt.steps.execute.shell import ExecutorShell

""" Beakerlib Executor Provider Class """


class ExecutorBeakerlib(ExecutorShell):
    """ Run tests using how: beakerlib """

    def __init__(self, data, plan):
        super(ExecutorBeakerlib, self).__init__(data, plan)

    def go(self, tests):
        super(ExecutorBeakerlib, self).go(tests)

