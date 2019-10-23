# coding: utf-8

""" Base Executor Provider Class """


class ExecutorBase(object):
    """ This is base executor class """

    def __init__(self, data, plan):
        self.data = data
        self.plan = plan

    def go(self, tests):
        """ Run tests """
        pass

    # API
    def requires(self):
        """ Returns packages required to run tests"""
        pass

    def results(self):
        """ Returns results from executed tests """
        pass
