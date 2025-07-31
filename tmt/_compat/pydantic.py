# mypy: disable-error-code="assignment"
from __future__ import annotations

import importlib.metadata

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    ValidationError,
)

PYDANTIC_VERSION = importlib.metadata.version('pydantic')

PYDANTIC_V1 = PYDANTIC_VERSION.startswith("1.")

__all__ = [
    "PYDANTIC_V1",
    "BaseModel",
    "ConfigDict",
    "Field",
    "HttpUrl",
    "ValidationError",
]
