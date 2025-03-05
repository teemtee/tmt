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
    Attempt to copy directory using 'cp -a --reflink=auto'.

    The 'cp' command itself will fall back to a standard copy if reflink is
    not supported by the filesystem.
    Returns True if successful, False if `cp` command fails with `RunError`.
    """
    cmd = ['cp', '-a', '--reflink=auto']

    logger.debug(f"Attempting copy from '{src}' to '{dst}' with {cmd}")

    try:
        # The '/./' at the end of the source path tells cp to copy the *contents* of the directory
        # rather than creating a new subdirectory in the destination
        Command(*cmd, f"{src}/./", str(dst)).run(cwd=None, logger=logger, join=True, silent=True)
        return True
    except RunError as error:
        logger.debug(f"cp copy command failed: {error}, falling back")
        return False
    # Let other exceptions (e.g. permissions, disk full) propagate


def _copy_tree_shutil(
    src: Path,
    dst: Path,
    logger: tmt.log.Logger,
) -> None:
    """
    Perform copy using shutil.copytree.

    This is typically a fallback strategy. It ensures that the destination
    directory `dst` and its parents exist before attempting the copy.
    """
    logger.debug(f"Performing shutil.copytree from '{src}' to '{dst}'")

    # Ensure destination directory `dst` and its parents exist.
    # shutil.copytree with dirs_exist_ok=True will then copy contents into `dst`,
    # merging if `dst` already contains files (e.g. from a previous failed attempt).
    dst.mkdir(parents=True, exist_ok=True)

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
    1. 'cp -a --reflink=auto' (copy-on-write, with cp's own fallback).
    2. shutil.copytree as a final fallback.

    Symlinks are always preserved. The destination directory `dst` and its
    parents will be created if they do not exist.

    :param src: Source directory path. Must exist and be a directory.
    :param dst: Destination directory path.
    :param logger: Logger to use for debug messages.
    :raises GeneralError: when copying fails using all strategies, or if `src`
                         does not exist or is not a directory.
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
    if _copy_tree_cp(src, dst, logger):
        logger.debug(
            "Copy finished using 'cp -a --reflink=auto' strategy (or its internal fallback)."
        )
        return

    # 2. Fallback to shutil.copytree
    logger.debug("Falling back to shutil.copytree strategy.")
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
