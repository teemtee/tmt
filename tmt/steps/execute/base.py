# coding: utf-8

""" Base Executor Provider Class """

from tmt.steps import Plugin


class ExecutorBase(Plugin):
    """ This is base executor class """

    def __init__(self,  data, step=None, name=None):
        super(ExecutorBase, self).__init__(data, step, name)

    def go(self, realpath, script, duration):
        """ Run tests """
        super(ExecutorBase, self).go()
        cmd = f'timeout {duration} {script}'
        self._run(cmd, cwd=realpath, shell=True)

    def _run(self, *args, **kwargs):
        return self.step.run(*args, **kwargs)

    # API
    def requires(self):
        """ Returns packages required to run tests"""
        pass

    def results(self):
        """ Returns results from executed tests """
        pass
