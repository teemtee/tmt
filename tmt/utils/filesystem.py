"""
Utility functions for filesystem operations.
"""

import filecmp
import os
import shutil
import subprocess
import zlib
from contextlib import suppress

import filelock

import tmt.log
from tmt._compat.pathlib import Path


def copy_tree(
    src: Path,
    dst: Path,
    logger: 'tmt.log.Logger',
    workdir_root: Path,
) -> None:
    """
    Copy directory efficiently using reflinks when possible,
    falling back to hardlinks for unchanged files.

    This function aims to reduce inode consumption by leveraging
    filesystem-specific features like reflinks (copy-on-write)
    when available. Symlinks are always preserved.

    :param src: Source directory path
    :param dst: Destination directory path
    :param logger: Logger to use for debug messages
    :param workdir_root: The root directory for tmt's working files (e.g., /var/tmp/tmt)
    """
    # Try reflink copy first (supported by btrfs, xfs with reflink, and some other filesystems)
    try:
        logger.debug(f"Attempting reflink copy from '{src}' to '{dst}'")

        # Create destination directory
        dst.mkdir(parents=True, exist_ok=True)

        # Use cp with --reflink=auto which falls back to regular copy if reflinks not supported
        # The '/./' at the end of the source path tells cp to copy the *contents* of the directory
        # rather than creating a new subdirectory in the destination
        subprocess.run(
            ['cp', '-a', '--reflink=auto', f"{src}/./", str(dst)],
            check=True,
            stderr=subprocess.PIPE,
        )
        logger.debug("Directory copied using reflink")
        return
    except subprocess.CalledProcessError as error:
        # Specific error for command failure
        logger.debug(f"Reflink copy command failed: {error}, falling back to hardlink strategy")
    except Exception as error:
        # Broad exception for unexpected issues or mock testing
        logger.debug(
            f"Reflink copy failed (unexpected error): {error}, falling back to hardlink strategy"
        )

    # Fallback to hardlink-based copy for unchanged files when reflinks aren't available
    # This fallback is particularly important for CI/CD environments like GitHub Actions
    # which typically run on Ubuntu with ext4 filesystems that don't support reflinks.
    # Without this fallback, workflows running in such environments would experience
    # significantly higher inode consumption and potential performance issues.

    # Use a persistent cache for hardlinks under the tmt workdir_root
    # Note: The cache directory is located under the tmt workdir_root.
    # Cleanup should be handled by tmt's workdir cleanup mechanisms if needed,
    # or potentially a dedicated 'tmt clean --cache' command.
    cache_base = workdir_root / 'cache'
    cache_base.mkdir(exist_ok=True)  # Ensure base cache dir exists
    # Use a sub-directory for this specific file content cache
    cache_dir = cache_base / 'files'
    cache_dir.mkdir(exist_ok=True)
    logger.debug(f"Using file cache directory: '{cache_dir}'")

    # Note: This fallback uses shutil.copy2/copystat, which attempts to preserve
    # permissions and timestamps but, per Python docs, cannot preserve all POSIX
    # metadata (e.g., owner, group, ACLs are lost). This matches the behavior
    # of the previously used shutil.copytree. https://docs.python.org/3/library/shutil.html

    if not dst.exists():
        dst.mkdir(parents=True, exist_ok=True)

    hardlink_count = 0
    regular_copy_count = 0

    # Skip if source doesn't exist
    if not src.exists():
        logger.debug(f"Source directory '{src}' does not exist, skipping copy")
        return

    for item in src.rglob('*'):
        relative_path = item.relative_to(src)
        dst_item = dst / relative_path

        # Create a path in cache using a hash of the relative path to avoid path length issues
        cache_path = cache_dir / relative_path_to_cache_key(relative_path)

        if item.is_dir():
            dst_item.mkdir(parents=True, exist_ok=True)
            # Copy directory attributes (mode, timestamps)
            shutil.copystat(item, dst_item)
        elif item.is_file():
            # Create parent directories if they don't exist
            dst_item.parent.mkdir(parents=True, exist_ok=True)

            # --- Concurrency Lock ---
            # Use a lock file based on the cache key to synchronize access
            lock_path = cache_dir / (relative_path_to_cache_key(relative_path) + ".lock")
            lock = filelock.FileLock(lock_path)
            copied_via_regular = False

            try:
                with lock.acquire(timeout=10):  # Timeout after 10 seconds
                    # --- Cache Check (inside lock) ---
                    content_identical = False
                    if cache_path.exists():
                        try:
                            # Compare file content thoroughly
                            content_identical = filecmp.cmp(item, cache_path, shallow=False)
                        except OSError as e:
                            logger.debug(f"Could not compare with cache file {cache_path}: {e}")
                            content_identical = False  # Treat as not identical if compare fails

                    # --- Attempt Hardlink from Cache (inside lock) ---
                    if content_identical:
                        try:
                            # Ensure destination doesn't exist before linking
                            if dst_item.exists() or dst_item.is_symlink():
                                dst_item.unlink()

                            os.link(cache_path, dst_item)
                            hardlink_count += 1
                            # Successfully hardlinked, skip regular copy and cache update
                            continue  # Move to the next item in src.rglob

                        except (OSError, FileExistsError) as e:
                            logger.debug(
                                f"Hardlink from cache {cache_path} failed: {e}, falling back to regular copy."  # noqa: E501
                            )
                            # Fall through to regular copy

                    # --- Regular Copy (inside lock if hardlink failed/not applicable) ---
                    # This copy happens if file is not in cache, not identical, or hardlink failed
                    shutil.copy2(item, dst_item)  # copy2 preserves metadata
                    regular_copy_count += 1
                    copied_via_regular = True  # Mark that we need to update cache

                    # --- Update Cache (inside lock) ---
                    if copied_via_regular:
                        temp_cache_path = None  # Define outside try block
                        try:
                            # Use temporary file for atomic update
                            temp_cache_path = cache_dir / (
                                relative_path_to_cache_key(relative_path) + ".tmp"
                            )
                            if temp_cache_path.exists():
                                temp_cache_path.unlink()  # Clean up from previous failed attempt

                            os.link(
                                dst_item, temp_cache_path
                            )  # Link the newly copied file to temp

                            # Atomically replace the cache file
                            # Rename is atomic on POSIX if src/dest are on the same filesystem
                            temp_cache_path.rename(cache_path)

                        except OSError as e:
                            logger.debug(f"Could not update cache file {cache_path}: {e}")
                            # If cache update fails, clean up temp file if it exists
                            if temp_cache_path and temp_cache_path.exists():
                                with suppress(OSError):
                                    temp_cache_path.unlink()  # Ignore cleanup error
                            # Ignore cache update errors, main copy succeeded

            except filelock.Timeout:
                logger.warning(
                    f"Could not acquire lock for cache entry {cache_path} after 10 seconds. "
                    f"Performing regular copy without cache interaction for {item}."
                )
                # --- Regular Copy (outside lock due to timeout) ---
                shutil.copy2(item, dst_item)
                regular_copy_count += 1

        elif item.is_symlink():
            # Handle symbolic links (outside the file lock)
            if dst_item.exists() or dst_item.is_symlink():
                dst_item.unlink()
            link_target = os.readlink(item)
            os.symlink(link_target, dst_item)

    if hardlink_count > 0:
        logger.debug(
            f"Directory copied using hardlinks: {hardlink_count} hardlinked, "
            f"{regular_copy_count} regular copies"
        )
    else:
        logger.debug("Directory copied using regular copy method")

    return


def relative_path_to_cache_key(relative_path: Path) -> str:
    """
    Convert a relative path to a flat, unique filename suitable for caching.

    This function takes a relative path (which may contain directories)
    and converts it to a deterministic, collision-resistant string that
    can be used as a filename in a flat cache directory.

    :param relative_path: Relative path
    :return: A string suitable for use as a filename in a cache directory
    """
    path_str = str(relative_path)
    return f"{zlib.crc32(path_str.encode()) & 0xFFFFFFFF:08x}"
