from unittest.mock import MagicMock

from tmt.base import DependencySimple
from tmt.steps.prepare.install import InstallBase


def test_debuginfo(root_logger):
    """ Check debuginfo package parsing """

    parent = MagicMock()
    guest = MagicMock()

    install = InstallBase(
        parent=parent,
        dependencies=[
            # Regular packages
            DependencySimple("wget"),
            DependencySimple("debuginfo-something"),
            DependencySimple("elfutils-debuginfod"),
            # Debuginfo packages
            DependencySimple("grep-debuginfo"),
            DependencySimple("elfutils-debuginfod-debuginfo"),
            ],
        directories=[],
        exclude=[],
        logger=root_logger,
        guest=guest)

    assert install.packages == [
        "wget",
        "debuginfo-something",
        "elfutils-debuginfod",
        ]
    assert install.debuginfo_packages == [
        "grep",
        "elfutils-debuginfod",
        ]
