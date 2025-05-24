"""
Utility functions for filesystem operations.
"""

import shutil

import tmt.log
from tmt._compat.pathlib import Path
from tmt.utils import Command, GeneralError, RunError


def _copy_tree_cp(
    src: Path,
    dst: Path,
    logger: tmt.log.Logger,
) -> bool:
    """
    Attempt to copy directory using ``cp -a --reflink=auto``.

    The ``cp`` command itself will fall back to a standard copy if
    reflink is not supported by the filesystem.

    :returns: ``True`` if successful, ``False`` if ``cp`` command fails
        with :py:class:`RunError`.
    """
    try:
        # The '/./' at the end of the source path tells cp to copy the *contents* of the directory
        # rather than creating a new subdirectory in the destination
        Command('cp', '-a', '--reflink=auto', f"{src}/./", str(dst)).run(
            cwd=None, logger=logger, join=True, silent=True
        )
        return True
    except RunError:
        return False
    # Let other exceptions (e.g. permissions, disk full) propagate


def _copy_tree_shutil(
    src: Path,
    dst: Path,
    logger: tmt.log.Logger,
) -> None:
    """
    Perform copy using shutil.copytree.

    This is typically a fallback strategy. The destination directory must
    exist before calling this function.
    """
    logger.debug(f"Performing shutil.copytree from '{src}' to '{dst}'")

    shutil.copytree(
        src,
        dst,
        symlinks=True,
        dirs_exist_ok=True,
    )


def copy_tree(
    src: Path,
    dst: Path,
    logger: tmt.log.Logger,
) -> None:
    """
    Copy directory efficiently, trying different strategies.

    Attempts strategies in order:

    #. ``cp -a --reflink=auto`` (copy-on-write, with ``cp``'s own
       fallback).

       * Reflinks provide fast, space-efficient copies that behave like
         normal copies
       * They don't use additional storage space unless the file is
         modified
       * Supported on btrfs (Fedora default since F33) and XFS (CentOS
         Stream 8+)
       * Using ``--reflink=auto`` means ``cp`` automatically falls back
         to standard copy if reflink isn't supported by the filesystem

    #. :py:func:`shutil.copytree` as a final fallback.

       * Used if the ``cp`` command fails for any reason
       * Maintains symlinks (``symlinks=True``)
       * Merges with existing destination directories (``dirs_exist_ok=True``)

    Symlinks are always preserved. The destination directory `dst` and its
    parents will be created if they do not exist. File permissions and timestamps
    are preserved in all copy strategies.

    Example usage:

    .. code-block:: python

        # Copy a directory tree with all its content
        copy_tree(Path("/path/to/source"), Path("/path/to/destination"), logger)

        # Copy with relative paths
        copy_tree(workdir / "original", workdir / "backup", logger)

    :param src: Source directory path. Must exist and be a directory.
    :param dst: Destination directory path.
    :param logger: Logger to use for debug messages.
    :raises GeneralError: when copying fails using all strategies, or if
        ``src`` does not exist or is not a directory.
    """
    logger.debug(f"Copying directory tree from '{src}' to '{dst}'")

    if not src.is_dir():
        # Add an explicit check for src, as 'cp' or 'shutil.copytree' might give
        # less clear or varied errors. This ensures a consistent error message.
        raise GeneralError(f"Source '{src}' for copy_tree is not a directory or does not exist.")

    # Ensure destination directory `dst` and its parents exist.
    # This is crucial for `cp` and helpful for `shutil.copytree` (as it creates parent dirs).
    dst.mkdir(parents=True, exist_ok=True)

    # 1. Try 'cp -a --reflink=auto' copy.
    #    'cp' itself handles fallback from reflink to standard copy if reflink=auto is used.
    logger.debug(f"Attempting copy from '{src}' to '{dst}' using 'cp' with reflink")
    if _copy_tree_cp(src, dst, logger):
        logger.debug(
            "Copy finished using 'cp -a --reflink=auto' strategy (or its internal fallback)."
        )
        return

    # 2. Fallback to shutil.copytree
    logger.debug("cp command failed, falling back to shutil.copytree strategy.")
    try:
        _copy_tree_shutil(src, dst, logger)
        logger.debug("Copy finished using shutil.copytree strategy.")
    except Exception as error:
        # Catching a broad Exception here because shutil.copytree can raise various errors
        # (e.g., OSError, FileExistsError if dst is a file after mkdir, etc.)
        # and we want to wrap them all in GeneralError.
        raise GeneralError(
            f"Failed to copy directory tree from '{src}' to '{dst}' using all strategies."
        ) from error
