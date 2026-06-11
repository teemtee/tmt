import shutil
import tempfile
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from tmt.base.core import DependencySimple
from tmt.steps.prepare.install import PrepareInstall
from tmt.utils import Path

if TYPE_CHECKING:
    from tests import RunTmt

DISABLED_CHECK_DATA = Path(__file__).resolve().parent / 'disabled_check_data'


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


def test_disabled_check_skips_essential_requires(run_tmt: 'RunTmt'):
    """
    Disabled check must not contribute its essential requirements
    to the prepare step's package list.
    """

    tmp = tempfile.mkdtemp()
    result = run_tmt(
        '--feeling-safe', '--root', str(DISABLED_CHECK_DATA),
        'run', '-i', tmp, '-vvv',
        'plan', '--name', '/disabled-only',
    )
    shutil.rmtree(tmp)

    assert result.exit_code == 0
    assert '/usr/bin/dmesg' not in result.output
