# coding: utf-8

""" Base Executor Provider Class """


class ExecutorBase(object):
    """ This is base executor class """

    def __init__(self, execute_step):
        self.execute_step = execute_step

    def go(self, tests):
        """ Run tests """
        pass

    def _run(self, *args, **kwargs):
        return self.execute_step.run(*args, **kwargs)

    # API
    def requires(self):
        """ Returns packages required to run tests"""
        pass

    def results(self):
        """ Returns results from executed tests """
        pass
