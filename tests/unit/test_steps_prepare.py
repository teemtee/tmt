from unittest.mock import MagicMock, patch

import tmt
from tmt.log import Logger
from tmt.steps.prepare.install import InstallBase


def prepare_command(self):
    """ Fake prepare_command() for InstallBase """
    return ("command", "options")


def get(what, default=None):
    """ Fake get() for parent PrepareInstall """

    if what == "directory":
        return []

    if what == "missing":
        return "skip"

    if what == "package":
        return [
            # Regular packages
            "wget",
            "debuginfo-something",
            "elfutils-debuginfod",
            # Debuginfo packages
            "grep-debuginfo",
            "elfutils-debuginfod-debuginfo",
            ]

    return None


@patch.object(tmt.steps.prepare.install.InstallBase, 'prepare_command', prepare_command)
def test_debuginfo():
    """ Check debuginfo package parsing """

    logger = Logger.create()
    parent = MagicMock()
    parent.get = get
    guest = MagicMock()

    install = InstallBase(parent=parent, logger=logger, guest=guest)

    assert install.repository_packages == [
        "wget",
        "debuginfo-something",
        "elfutils-debuginfod",
        ]
    assert install.debuginfo_packages == [
        "grep",
        "elfutils-debuginfod",
        ]
