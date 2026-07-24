import sys

if sys.version_info >= (3, 14):
    from annotationlib import Format, get_annotations
else:
    import enum
    from collections.abc import Mapping
    from typing import Any, Optional

    class Format(enum.IntEnum):
        VALUE = 1
        VALUE_WITH_FAKE_GLOBALS = 2
        FORWARDREF = 3
        STRING = 4

    def get_annotations(
        obj: Any,
        *,
        globals: Optional[dict[str, object]] = None,  # noqa: A002
        locals: Optional[Mapping[str, object]] = None,  # noqa: A002
        eval_str: bool = False,
        format: Format = Format.VALUE,
    ) -> dict[str, str]:
        if format != Format.STRING:
            raise NotImplementedError("Format other than Format.STRING is not backported.")
        if globals or locals or eval_str:
            raise NotImplementedError("Other input variables are not implemented.")
        # Technically we should raise if obj does not have annotations,
        # but if there are any issues with this it would be caught in the CI
        ann: dict[str, str] = obj.__dict__.get("__annotations__", {})
        return ann


__all__ = [
    "Format",
    "get_annotations",
]
