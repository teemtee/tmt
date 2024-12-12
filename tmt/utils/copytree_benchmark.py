"""Benchmark different copytree implementations for tmt testing.

This module provides alternative implementations of shutil.copytree for
benchmarking purposes. It allows switching between different copy methods
via the TMT_COPYTREE_METHOD environment variable to measure their performance
impact on tmt testing.

Available methods:
- 'default': Use shutil.copytree (default)
- 'rsync': Use rsync-based implementation
- 'tar': Use tar-based implementation
"""

import os
import shutil
from collections.abc import Iterable
from os import PathLike
from typing import Any, Callable, Optional, Union

from tmt._compat.pathlib import Path
from tmt.log import Logger
from tmt.utils import Command

__all__ = ['copytree', 'install_benchmarks']

# Store original copytree for restoration if needed
_original_copytree = shutil.copytree


def copytree(
        src: Union[str, PathLike[str]],
        dst: Union[str, PathLike[str]],
        symlinks: bool = False,
        ignore: Optional[Union[
            Callable[[str, list[str]], Iterable[str]],
            Callable[[Union[str, PathLike[str]], list[str]], Iterable[str]]
            ]] = None,
        copy_function: Callable[[str, str], Any] = shutil.copy2,
        ignore_dangling_symlinks: bool = False,
        dirs_exist_ok: bool = False,
        logger: Optional[Logger] = None,
        ) -> str:
    """
    Benchmark-enabled version of shutil.copytree.

    The copy method is determined by the TMT_COPYTREE_METHOD environment variable:
    - 'default': Use shutil.copytree (default)
    - 'rsync': Use rsync-based implementation
    - 'tar': Use tar-based implementation

    All parameters match shutil.copytree for drop-in compatibility.
    """
    method = os.getenv("TMT_COPYTREE_METHOD", "default").lower()

    if method == "rsync":
        # Create destination directory
        dst_path = Path(dst)
        dst_path.mkdir(parents=True, exist_ok=dirs_exist_ok)

        # Build rsync command with optimized options
        cmd = [
            "rsync",
            # -a is archive mode, which is equivalent to:
            # -rlptgoD (recursive, symlinks, perms, times, group, owner, devices)
            # This ensures we preserve all file attributes and structure
            "-a",
            ]

        if not symlinks:
            # -L: transform symlinks into referent files/dirs
            # This matches shutil.copytree's symlinks=False behavior
            cmd.append("-L")

        # Additional performance optimizations
        cmd.extend(
            [
                # --whole-file: don't use rsync's delta-transfer algorithm
                # Since we're copying locally, it's faster to just copy the whole file
                # than to calculate and transfer deltas
                "--whole-file",
                # --inplace: write files directly to their final location
                # This avoids the overhead of writing to a temp file and then moving it
                # Especially beneficial when copying many small files
                "--inplace",
                # --no-compress: disable compression
                # Since we're copying locally, compression only adds CPU overhead
                "--no-compress",
                # --sparse: handle sparse files efficiently
                # This preserves sparseness when copying files
                "--sparse",
                # --numeric-ids: don't map uid/gid to user/group names
                # Faster since we don't need to look up names in passwd/group
                "--numeric-ids",
                # --hard-links: preserve hard links
                # This ensures hard links are preserved in the copy
                "--hard-links",
                ]
            )

        # Handle ignore patterns if provided
        if ignore:
            # Convert ignore patterns to rsync exclude rules
            patterns = ignore(str(src), os.listdir(str(src)))
            for pattern in patterns:
                cmd.extend(["--exclude", pattern])

        # Ensure trailing slash on source to copy contents
        # This makes rsync copy the contents of src into dst
        # rather than creating a new directory under dst
        src_str = str(src) + "/"
        dst_str = str(dst)

        cmd.extend([src_str, dst_str])

        # Execute rsync
        if logger:
            Command(*cmd).run(cwd=Path(src), logger=logger)
        else:
            Command(*cmd).run(cwd=Path(src), logger=Logger.create())

        return str(dst_path)

    elif method == "tar":  # noqa: RET505
        # Create destination directory
        dst_path = Path(dst)
        dst_path.mkdir(parents=True, exist_ok=dirs_exist_ok)

        # Build tar pipeline command
        cmd = [
            "tar",
            "--create",
            # --directory: change to directory before performing any operations
            # This preserves relative paths in the archive
            "--directory",
            str(src),
            # --one-file-system: don't cross filesystem boundaries
            # This prevents copying from other mounted filesystems
            "--one-file-system",
            # --sparse: handle sparse files efficiently
            # This preserves sparseness in the archive
            "--sparse",
            # --numeric-owner: use numbers for user/group names
            # Faster since we don't need to look up names
            "--numeric-owner",
            # --hard-dereference: preserve hard links
            # This ensures hard links are preserved in the copy
            "--hard-dereference",
            ]

        if symlinks:
            # --dereference: follow symlinks, store target files
            # This matches shutil.copytree's symlinks=True behavior
            cmd.append("--dereference")

        # Handle ignore patterns if provided
        if ignore:
            # Convert ignore patterns to tar exclude rules
            patterns = ignore(str(src), os.listdir(str(src)))
            for pattern in patterns:
                cmd.extend(["--exclude", pattern])

        cmd.extend(
            [
                # Since we changed directory with --directory, this gets all content
                ".",
                # pipe the archive to the next command
                # This avoids writing to disk, streaming directly to extraction
                "|",
                "tar",
                "--extract",
                "--directory",
                str(dst),
                # --preserve-permissions: apply the exact permissions from the archive
                # This ensures file modes are preserved
                "--preserve-permissions",
                # --touch: touch files to set their times
                # This ensures modification times are preserved
                "--touch",
                # --sparse: handle sparse files efficiently
                "--sparse",
                # --numeric-owner: use numbers for user/group names
                "--numeric-owner",
                ]
            )

        # Execute tar pipeline
        # The pipeline streams data directly from creation to extraction
        # without writing a temporary archive to disk
        if logger:
            Command(" ".join(cmd)).run(shell=True, cwd=Path(src), logger=logger)  # noqa: S604
        else:
            Command(" ".join(cmd)).run(shell=True, cwd=Path(src), logger=Logger.create())  # noqa: S604

        return str(dst_path)

    else:  # method == 'default' or unknown
        return str(_original_copytree(
            src,
            dst,
            symlinks=symlinks,
            ignore=ignore,
            copy_function=copy_function,
            ignore_dangling_symlinks=ignore_dangling_symlinks,
            dirs_exist_ok=dirs_exist_ok,
            ))


def install_benchmarks() -> None:
    """Install benchmark implementations by monkey patching shutil.copytree."""
    import shutil
    shutil.copytree = copytree
