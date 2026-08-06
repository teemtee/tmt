"""
Utility functions for filesystem operations.
"""

import contextlib
import enum
import shutil
from collections.abc import Generator
from typing import Optional, Protocol

import tmt.log
from tmt._compat.pathlib import Path
from tmt.utils import Command, GeneralError, RunError, show_exception_as_warning
from tmt.utils.environment import Environment


class TmpDirCreator(Protocol):
    @contextlib.contextmanager
    def __call__(
        self, prefix: Optional[str] = None, suffix: Optional[str] = None
    ) -> Generator[Path, None, None]:  # type: ignore[reportReturnType,unused-ignore]
        pass


class StrategyOutcome(enum.Enum):
    """
    Possible outcomes of a :py:class:`CopyStrategy` strategy.
    """

    #: Strategy was successful, and copied the tree as requested.
    SUCCESS = enum.auto()

    #: Strategy failed to copy the tree.
    FAIL = enum.auto()

    #: For some reason, it was not possible for the strategy to even
    #: attempt copying the tree.
    YIELD = enum.auto()


class CopyStrategy(Protocol):
    def __call__(
        self,
        *,
        src: Path,
        dst: Path,
        tmpdir_creator: Optional[TmpDirCreator] = None,
        logger: tmt.log.Logger,
    ) -> StrategyOutcome:  # type: ignore[reportReturnType,unused-ignore]
        pass


def _copy_tree_cp(
    *,
    src: Path,
    dst: Path,
    tmpdir_creator: Optional[TmpDirCreator] = None,
    logger: tmt.log.Logger,
) -> StrategyOutcome:
    """
    Attempt to copy directory using ``cp -a --reflink=auto``.

    ``cp -a --reflink=auto`` provides copy-on-write, and ``cp``'s own
    fallback).

    * Reflinks provide fast, space-efficient copies that behave like
      normal copies.
    * They don't use additional storage space unless the file is
      modified.
    * Supported on btrfs (Fedora default since F33) and XFS (CentOS
      Stream 8+).
    * Using ``--reflink=auto`` means ``cp`` automatically falls back
      to standard copy if reflink isn't supported by the filesystem.

    :returns: ``True`` if successful, ``False`` if ``cp`` command fails
        with :py:class:`RunError`.
    """

    logger.debug(f"Copy tree '{src}' => '{dst}' using 'cp --reflink=auto' strategy.")

    try:
        # The '/./' at the end of the source path tells cp to copy the
        # *contents* of the directory rather than creating a new
        # subdirectory in the destination
        Command('cp', '-a', '--reflink=auto', f"{src}/./", dst).run(
            cwd=None, environment=Environment.from_environ(), silent=True, logger=logger
        )

    # Let other exceptions (e.g. permissions, disk full) propagate
    except RunError as exc:
        show_exception_as_warning(
            exception=exc, message="'cp --reflink=auto' failed", logger=logger
        )

        return StrategyOutcome.FAIL

    return StrategyOutcome.SUCCESS


def _copy_tree_rsync(
    *,
    src: Path,
    dst: Path,
    tmpdir_creator: Optional[TmpDirCreator] = None,
    logger: tmt.log.Logger,
) -> StrategyOutcome:
    """
    Copy directory using ``rsync -a``.

    :returns: ``True`` if successful, ``False`` if ``rsync`` command
        fails with :py:class:`RunError`.
    """

    if tmpdir_creator is None:
        logger.debug(
            f"Copy tree '{src}' => '{dst}' using 'rsync -a' strategy"
            " not possible without a temporary directory."
        )

        return StrategyOutcome.YIELD

    logger.debug(f"Copy tree '{src}' => '{dst}' using 'rsync -a' strategy.")

    with tmpdir_creator(prefix='rsync-') as rsync_tempdir:
        try:
            Command(
                'rsync',
                '-ar',
                '--temp-dir',
                rsync_tempdir,
                f"{src}/",
                dst,
            ).run(cwd=None, environment=Environment.from_environ(), silent=True, logger=logger)

        # Let other exceptions (e.g. permissions, disk full) propagate
        except RunError as exc:
            show_exception_as_warning(exception=exc, message="'rsync' failed", logger=logger)

            return StrategyOutcome.FAIL

    return StrategyOutcome.SUCCESS


def _copy_tree_shutil(
    *,
    src: Path,
    dst: Path,
    tmpdir_creator: Optional[TmpDirCreator] = None,
    logger: tmt.log.Logger,
) -> StrategyOutcome:
    """
    Perform copy using :py:func:`shutil.copytree`.

    * Typically a safe fallback strategy.
    * Maintains symlinks (``symlinks=True``).
    * Merges with existing destination directories (``dirs_exist_ok=True``).

    :returns: ``True`` if successful. ``False`` is never returned, failed
        operations raise an exception.
    """

    logger.debug(f"Copy tree '{src}' => '{dst}' using 'shutil.copytree' strategy.")

    shutil.copytree(
        src,
        dst,
        symlinks=True,
        dirs_exist_ok=True,
    )

    return StrategyOutcome.SUCCESS


_COPY_TREE_STRATEGIES: tuple[CopyStrategy, ...] = (
    _copy_tree_rsync,
    _copy_tree_cp,
    _copy_tree_shutil,
)


def copy_tree(
    *,
    src: Path,
    dst: Path,
    tmpdir_creator: Optional[TmpDirCreator] = None,
    logger: tmt.log.Logger,
) -> None:
    """
    Copy directory efficiently, trying different strategies.

    * Symlinks are always preserved.
    * The destination directory ``dst`` and its parents will be created
      if they do not exist.
    * File permissions and timestamps are preserved by all copy
      strategies.

    Example usage:

    .. code-block:: python

        # Copy a directory tree with all its content
        copy_tree(Path("/path/to/source"), Path("/path/to/destination"), logger)

        # Copy with relative paths
        copy_tree(workdir / "original", workdir / "backup", logger)

    :param src: Source directory path. Must exist, and must be a
        directory.
    :param dst: Destination directory path. If it does not exist, it
        will be created.
    :param tmpdir_creator: a context manager that, when invoked, would
        create and hold a temporary directory. Some strategies may
        require such a directory for their work.
    :param logger: Logger to use for debug messages.
    :raises GeneralError: when copying fails using all strategies, or if
        ``src`` does not exist or is not a directory.
    """

    logger.debug(f"Copy tree '{src}' => '{dst}'")

    if not src.is_dir():
        # Add an explicit check for src, as strategies might give less
        # clear or varied errors. This ensures a consistent error message.
        raise GeneralError(f"Source path '{src}' is not a directory or does not exist.")

    # Ensure destination directory and its parents exist.
    dst.mkdir(parents=True, exist_ok=True)

    for strategy in _COPY_TREE_STRATEGIES:
        try:
            outcome = strategy(
                src=src, dst=dst, tmpdir_creator=tmpdir_creator, logger=logger.descend()
            )

            if outcome is StrategyOutcome.SUCCESS:
                return

            if outcome in (StrategyOutcome.FAIL, StrategyOutcome.YIELD):
                continue

        except Exception as exc:
            raise GeneralError(f"Failed to copy tree '{src}' => '{dst}'.") from exc

    raise GeneralError(f"Failed to copy tree '{src}' => '{dst}'.")
