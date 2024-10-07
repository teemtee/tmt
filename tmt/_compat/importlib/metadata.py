from __future__ import annotations

import sys

if sys.version_info < (3, 10):
    from importlib_metadata import entry_points  # pyright: ignore[reportUnknownVariableType]
else:
    from importlib.metadata import entry_points

__all__ = [
    "entry_points",
    ]
