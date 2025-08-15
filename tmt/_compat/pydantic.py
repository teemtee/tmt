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

        def model_dump(self, **kwargs: Any) -> dict[str, Any]:
            return self.dict(**kwargs)

        @property
        def model_fields_set(self) -> set[str]:
            return set(self.__dict__.keys())

        # The names of the model_fields and __fields__ value types are different,
        # but it shouldn't matter for our implementation so far
        @property
        def model_fields(self) -> dict[str, Any]:  # type: ignore[override]
            return self.__fields__

    def model_rebuild(model: type[BaseModel], localns: dict[str, Any]) -> None:
        """
        Try to rebuild the pydantic-core schema for the model.

        This may be necessary when one of the annotations is a
        ``ForwardRef`` which could not be resolved during the initial
        attempt to build the schema, and automatic rebuilding fails.
        """

        model.update_forward_refs(**localns)

else:
    from pydantic import BaseModel

    def model_rebuild(model: type[BaseModel], localns: dict[str, Any]) -> None:
        """
        Try to rebuild the pydantic-core schema for the model.

        This may be necessary when one of the annotations is a
        ``ForwardRef`` which could not be resolved during the initial
        attempt to build the schema, and automatic rebuilding fails.
        """

        model.model_rebuild(_types_namespace=localns)


__all__ = [
    "PYDANTIC_V1",
    "BaseModel",
    "ConfigDict",
    "Field",
    "HttpUrl",
    "ValidationError",
    "model_rebuild",
]
