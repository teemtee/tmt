from __future__ import annotations

import sys

if sys.version_info >= (3, 12):
    from importlib.resources import files
else:
    from importlib_resources import files

__all__ = [
    "files",
]
