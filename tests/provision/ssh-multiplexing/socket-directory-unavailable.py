"""Exercise the CLI when private SSH socket directories cannot be created."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from tmt.__main__ import run_cli

with patch(
    'tmt.guest.tempfile',
    SimpleNamespace(
        TemporaryDirectory=MagicMock(side_effect=PermissionError('Socket directory unavailable'))
    ),
):
    raise SystemExit(run_cli())
