import sys

if sys.version_info >= (3, 10):
    from importlib.metadata import entry_points
else:
    from importlib_metadata import entry_points  # pyright: ignore[reportUnknownVariableType]

__all__ = [
    "entry_points",
]
