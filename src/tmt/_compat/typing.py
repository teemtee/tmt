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

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override

__all__ = [
    "Concatenate",
    "ParamSpec",
    "Self",
    "TypeAlias",
    "TypeGuard",
    "override",
]
