from __future__ import annotations

import os
import pathlib
import sys
import typing

if sys.version_info >= (3, 12):
    from importlib.resources.abc import Traversable
    from importlib.resources.readers import MultiplexedPath as _MultiplexedPath
else:
    from importlib_resources.abc import Traversable
    from importlib_resources.readers import MultiplexedPath as _MultiplexedPath

from tmt._compat.pathlib import Path

if typing.TYPE_CHECKING:
    from collections.abc import Iterator


class MultiplexedPath(_MultiplexedPath):
    #: Component paths that share the same namespace.
    #: Original class already defines this attribute, but we narrow-type it.
    _paths: list[Path]

    def __new__(cls, *paths: Path | MultiplexedPath | Traversable) -> Path | MultiplexedPath:  # type:ignore[misc]
        if len(paths) == 0:
            return Path()
        if len(paths) > 1 or isinstance(paths[0], _MultiplexedPath):
            return super().__new__(cls)
        return Path(paths[0])  # type:ignore[arg-type]

    def __init__(self, *paths: Path | MultiplexedPath | Traversable) -> None:
        super().__init__(*paths)  # type:ignore[no-untyped-call]
        # Make sure we are using tmt compat Path.
        # Other methods should preserve the type of the children Paths
        original_paths = self._paths.copy()
        self._paths = []
        for p in original_paths:
            # Note: when using importlib_resources, the NamespaceReader (and MultiplexedPath)
            # created are from importlib_resources and not from std paths, so we should be safe
            # on that front. It can still break for custom editable install loaders, but we do not
            # know how to generally support those cases yet.
            if isinstance(p, _MultiplexedPath):
                # Flatten the MultiplexedPaths and make sure the paths are recast to tmt Path
                self._paths.extend(MultiplexedPath(*p._paths)._paths)  # pyright:ignore[reportArgumentType]
            elif isinstance(p, pathlib.Path):  # pyright:ignore[reportUnnecessaryIsInstance]
                self._paths.append(Path(p))
            else:
                raise NotImplementedError(f"Got unexpected traversable [{type(p)}] {p}")

    def glob(self, pattern: str) -> Iterator[Path]:
        for p in self._paths:
            yield from p.glob(pattern)

    def exists(self) -> bool:
        # When the multiplexed path was created, the current directory is implied to exist
        return True

    # Override type-hints of the original definitions
    def joinpath(self, *descendants: str | os.PathLike[str]) -> Path | MultiplexedPath:
        new_path = super().joinpath(*descendants)  # type: ignore[no-untyped-call]
        assert isinstance(new_path, (Path, MultiplexedPath))
        return new_path

    def __truediv__(self, child: str | os.PathLike[str]) -> Path | MultiplexedPath:
        return self.joinpath(child)


__all__ = [
    "MultiplexedPath",
]
