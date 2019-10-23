# coding: utf-8

""" Base Executor Provider Class """


class ExecutorBase(object):
    """ This is base executor class """

    def __init__(self, data, plan):
        self.data = data
        self.plan = plan

    def go(self, tests):
        pass