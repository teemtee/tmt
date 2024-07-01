import os
import pathlib
from typing import Union


class Path(pathlib.PosixPath):
    # Apparently, `pathlib`` does not offer `relpath` transition between
    # parallel trees, instead, a `ValueError`` is raised when `self` does not
    # lie under `other`. Overriding the original implementation with one based
    # on `os.path.relpath()`, which is more suited to tmt code base needs.
    #
    # ignore[override]: does not match the signature on purpose, our use is
    # slightly less generic that what pathlib supports, to be usable with
    # os.path.relpath.
    def relative_to(self, other: Union[str, "Path"]) -> "Path":  # type: ignore[override]
        return Path(os.path.relpath(self, other))

    # * `Path.is_relative_to()`` has been added in 3.9
    # https://docs.python.org/3/library/pathlib.html#pathlib.PurePath.is_relative_to
    #
    # * The original implementation calls `relative_to()`, which we just made
    # to return a relative path for all possible inputs, even those the original
    # implementation considers to not be relative to each other. Therefore, we
    # need to override `is_relative_to()` even for other Python versions, to not
    # depend on `ValueError` raised by the original `relative_to()`.
    def is_relative_to(self, other: "Path") -> bool:  # type: ignore[override]
        # NOTE: the following is not perfect, but it should be enough for
        # what tmt needs to know about its paths.

        # Acquire the relative path from the one we're given and the other...
        relpath = os.path.relpath(str(self), str(other))

        # ... and if the relative path starts with `..`, it means we had to
        # walk *up* from `other` and descend to `path`, therefore `path` cannot
        # be a subtree of `other`.

        return not relpath.startswith("..")

    def unrooted(self) -> "Path":
        """Return the path as if it was not starting in file system root"""

        if self.is_absolute():
            return self.relative_to("/")

        return self
