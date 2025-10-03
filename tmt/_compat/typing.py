from __future__ import annotations

import sys

if sys.version_info >= (3, 10):
    from typing import Concatenate, ParamSpec, TypeAlias, TypeGuard
else:
    from typing_extensions import Concatenate, ParamSpec, TypeAlias, TypeGuard

if sys.version_info >= (3, 11):
    from typing import Self
else:
    from typing_extensions import Self

__all__ = [
    "Concatenate",
    "ParamSpec",
    "Self",
    "TypeAlias",
    "TypeGuard",
]
