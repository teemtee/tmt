# mypy: disable-error-code="assignment"
from __future__ import annotations

import importlib.metadata

from pydantic import (
    ConfigDict,
    Field,
    HttpUrl,
    ValidationError,
)

PYDANTIC_VERSION = importlib.metadata.version('pydantic')

PYDANTIC_V1 = PYDANTIC_VERSION.startswith("1.")

if PYDANTIC_V1:
    from typing import Any

    from pydantic import BaseModel as _BaseModel

    from tmt._compat.typing import Self

    class BaseModel(_BaseModel):
        @classmethod
        def model_validate(cls, obj: Any, **kwargs: Any) -> Self:
            if kwargs:
                raise NotImplementedError(
                    "Backport of model_validate to parse_obj does not include kwargs."
                )
            return cls.parse_obj(obj)

        @classmethod
        def model_validate_json(cls, json_data: str, **kwargs: Any) -> Self:  # type: ignore[override]
            if kwargs:
                raise NotImplementedError(
                    "Backport of model_validate_json to parse_raw does not include kwargs."
                )

            return cls.parse_raw(json_data, content_type="application/json")

        def model_dump(self, **kwargs: Any) -> dict[str, Any]:
            return self.dict(**kwargs)

        @property
        def model_fields_set(self) -> set[str]:
            return set(self.__dict__.keys())

        # The names of the model_fields and __fields__ value types are different,
        # but it shouldn't matter for our implementation so far
        @property
        def model_fields(self) -> dict[str, Any]:
            return self.__fields__

else:
    from pydantic import BaseModel

__all__ = [
    "PYDANTIC_V1",
    "BaseModel",
    "ConfigDict",
    "Field",
    "HttpUrl",
    "ValidationError",
]
