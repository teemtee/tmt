# mypy: disable-error-code="assignment"
from __future__ import annotations

import pydantic

if pydantic.__version__.startswith('1.'):
    from pydantic import (
        BaseModel,
        Extra,
        Field,
        HttpUrl,
        ValidationError,
    )
else:
    from pydantic.v1 import (  # type: ignore[no-redef]
        BaseModel,
        Extra,
        Field,
        HttpUrl,
        ValidationError,
    )

__all__ = [
    "BaseModel",
    "Extra",
    "Field",
    "HttpUrl",
    "ValidationError",
]
