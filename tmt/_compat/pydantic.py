# mypy: disable-error-code="assignment"
from __future__ import annotations

import pydantic

if pydantic.__version__.startswith('1.'):
    from pydantic import (
        BaseModel,
        Extra,
        HttpUrl,
        ValidationError,
        )
else:
    from pydantic.v1 import (
        BaseModel,
        Extra,
        HttpUrl,
        ValidationError,
        )

__all__ = [
    "BaseModel",
    "Extra",
    "HttpUrl",
    "ValidationError",
    ]
