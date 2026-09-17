from __future__ import annotations

import sys

if sys.version_info >= (3, 13):
    from warnings import deprecated

else:
    # ``warnings.deprecated`` (PEP 702) is only available since Python 3.13.
    # tmt uses it merely as a runtime decorator emitting a warning, so provide
    # a minimal backport for older, still supported Python versions.
    import functools
    import warnings
    from collections.abc import Callable
    from typing import TypeVar

    _T = TypeVar("_T", bound=Callable[..., object])

    def deprecated(
        message: str,
        /,
        *,
        category: type[Warning] | None = DeprecationWarning,
        stacklevel: int = 1,
    ) -> Callable[[_T], _T]:
        def decorator(func: _T) -> _T:
            @functools.wraps(func)
            def wrapper(*args: object, **kwargs: object) -> object:
                if category is not None:
                    warnings.warn(message, category=category, stacklevel=stacklevel + 1)

                return func(*args, **kwargs)

            return wrapper  # type: ignore[return-value]

        return decorator


__all__ = [
    "deprecated",
]
