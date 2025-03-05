"""
Utility functions for filesystem operations.
"""

import filecmp
import os
import shutil
import subprocess
import tempfile
import zlib
from typing import Optional, Union

import tmt.log
from tmt._compat.pathlib import Path


def copy_tree(
    src: Union[str, Path],
    dst: Union[str, Path],
    symlinks: bool = True,
    logger: Optional['tmt.log.Logger'] = None,
) -> None:
    """
    Copy directory efficiently using reflinks when possible,
    falling back to hardlinks for unchanged files.

    This function aims to reduce inode consumption by leveraging
    filesystem-specific features like reflinks (copy-on-write)
    when available.

    Args:
        src: Source directory path
        dst: Destination directory path
        symlinks: Whether to preserve symlinks (default: True)
        logger: Logger to use for debug messages (optional)
    """
    src_path = Path(src)
    dst_path = Path(dst)

    # Try reflink copy first (supported by btrfs, xfs with reflink, and some other filesystems)
    try:
        if logger:
            logger.debug(f"Attempting reflink copy from '{src_path}' to '{dst_path}'")

        # Create destination directory
        dst_path.mkdir(parents=True, exist_ok=True)

        # Use cp with --reflink=auto which falls back to regular copy if reflinks not supported
        # The '/./' at the end of the source path tells cp to copy the *contents* of the directory
        # rather than creating a new subdirectory in the destination
        subprocess.run(
            ['cp', '-a', '--reflink=auto', f"{src_path}/./", str(dst_path)],
            check=True,
            stderr=subprocess.PIPE,
        )
        if logger:
            logger.debug("Directory copied using reflink")
        return
    except (subprocess.SubprocessError, FileNotFoundError) as error:
        if logger:
            logger.debug(f"Reflink copy failed: {error}, falling back to hardlink strategy")

    # Fallback to hardlink-based copy for unchanged files when reflinks aren't available
    # This fallback is particularly important for CI/CD environments like GitHub Actions
    # which typically run on Ubuntu with ext4 filesystems that don't support reflinks.
    # Without this fallback, workflows running in such environments would experience
    # significantly higher inode consumption and potential performance issues.
    # Use a persistent cache for hardlinks
    cache_dir = Path(tempfile.gettempdir()) / 'tmt_file_cache'
    cache_dir.mkdir(exist_ok=True)

    if not dst_path.exists():
        dst_path.mkdir(parents=True, exist_ok=True)

    hardlink_count = 0
    regular_copy_count = 0

    for item in src_path.rglob('*'):
        relative_path = item.relative_to(src_path)
        dst_item = dst_path / relative_path

        # Create a path in cache using a hash of the relative path to avoid path length issues
        cache_key = relative_path_to_cache_key(relative_path)
        cache_path = cache_dir / cache_key

        if item.is_dir():
            dst_item.mkdir(parents=True, exist_ok=True)
        elif item.is_file():
            # Create parent directories if they don't exist
            dst_item.parent.mkdir(parents=True, exist_ok=True)

            # Use cached version if it exists and has identical content
            content_identical = False
            if cache_path.exists():
                try:
                    content_identical = filecmp.cmp(item, cache_path, shallow=False)
                except OSError:
                    # Handle cases where the file might be inaccessible
                    content_identical = False

            if content_identical:
                try:
                    # Remove destination if it exists (needed for hardlink)
                    if dst_item.exists():
                        dst_item.unlink()

                    # Create hardlink from cache
                    os.link(cache_path, dst_item)
                    hardlink_count += 1
                    continue
                except (OSError, FileExistsError):
                    # Fall through to regular copy if hardlink fails
                    pass

            # Regular copy if hardlink approach didn't work
            shutil.copy2(item, dst_item)
            regular_copy_count += 1

            # Update cache with this file
            try:
                if cache_path.exists():
                    cache_path.unlink()
                os.link(dst_item, cache_path)
            except OSError:
                # Ignore cache errors - they shouldn't affect the main operation
                pass

        elif item.is_symlink() and symlinks:
            # Handle symbolic links if requested
            if dst_item.exists() or dst_item.is_symlink():
                dst_item.unlink()
            link_target = os.readlink(item)
            os.symlink(link_target, dst_item)

    if logger:
        if hardlink_count > 0:
            logger.debug(
                f"Directory copied using hardlinks: {hardlink_count} hardlinked, "
                f"{regular_copy_count} regular copies"
            )
        else:
            logger.debug("Directory copied using regular copy method")

    return


def relative_path_to_cache_key(relative_path: Union[str, Path]) -> str:
    """
    Convert a relative path to a flat, unique filename suitable for caching.

    This function takes a relative path (which may contain directories)
    and converts it to a deterministic, collision-resistant string that
    can be used as a filename in a flat cache directory.

    Args:
        relative_path: Relative path

    Returns:
        A string suitable for use as a filename in a cache directory
    """
    path_str = str(relative_path)
    return f"{zlib.crc32(path_str.encode()) & 0xFFFFFFFF:08x}"
