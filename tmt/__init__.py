""" Test Management Tool """

# starting with setuptools_scm 7.0 it's possible to import __version__ directly
# to support setuptools_scm 6.0 (in EL9), we can only import version
from tmt._version import version as __version__  # noqa: F401

__all__ = [
    'Tree',
    'Test',
    'Plan',
    'Story',
    'Run',
    'Guest',
    'GuestSsh',
    'Result',
    'Status',
    'Clean',
    'Logger']

from tmt.base import Clean, Plan, Run, Status, Story, Test, Tree
from tmt.log import Logger
from tmt.result import Result
from tmt.steps.provision import Guest, GuestSsh
