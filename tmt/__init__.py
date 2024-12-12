""" Test Management Tool """

import importlib.metadata
from os import getenv

__version__ = importlib.metadata.version(__name__)

__all__ = [
    'Clean',
    'Guest',
    'GuestSsh',
    'Logger',
    'Plan',
    'Result',
    'Run',
    'Status',
    'Story',
    'Test',
    'Tree',
    ]

from tmt.base import Clean, Plan, Run, Status, Story, Test, Tree
from tmt.log import Logger
from tmt.result import Result
from tmt.steps.provision import Guest, GuestSsh

# Import early to enable benchmarking if requested
if getenv("TMT_COPYTREE_METHOD"):
    from tmt.utils.copytree_benchmark import install_benchmarks
    install_benchmarks()
