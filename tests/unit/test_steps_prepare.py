from unittest.mock import MagicMock

from tmt.base.core import DependencySimple
from tmt.steps.prepare.install import PrepareInstall


def test_debuginfo(root_logger):
    """
    Check debuginfo package parsing
    """

    plugin = MagicMock(spec=PrepareInstall)

    PrepareInstall._prepare_installables(
        plugin,
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
        logger=root_logger,
    )

    assert plugin.packages == [
        "wget",
        "debuginfo-something",
        "elfutils-debuginfod",
    ]
    assert plugin.debuginfo_packages == [
        "grep",
        "elfutils-debuginfod",
    ]
