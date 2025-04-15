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


def _copy_tree_reflinks(
    src: Path,
    dst: Path,
    logger: 'tmt.log.Logger',
    workdir_root: Path,  # Keep signature consistent, even if not used here
) -> bool:
    """
    Attempt to copy directory using reflinks.

    Returns True on success, False on failure.
    """
    try:
        logger.debug(f"Attempting reflink copy from '{src}' to '{dst}'")

        # Create destination directory if it doesn't exist
        # Check if src exists first
        if not src.exists():
            logger.debug(f"Source directory '{src}' does not exist, skipping reflink copy")
            return False  # Indicate failure as source doesn't exist

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
        return True
    except subprocess.CalledProcessError as error:
        # Specific error for command failure
        logger.debug(f"Reflink copy command failed: {error}, falling back")
        return False
    except Exception as error:
        # Broad exception for unexpected issues or mock testing
        logger.debug(f"Reflink copy failed (unexpected error): {error}, falling back")
        return False


# TODO finish hardlink strategy
def _copy_tree_hardlinks(  # pyright: ignore[reportUnusedFunction]
    src: Path,
    dst: Path,
    logger: 'tmt.log.Logger',
    workdir_root: Path,
) -> bool:
    """
    Copy directory using hardlinks for unchanged files from a persistent cache.

    Returns True on successful completion, False on major error (e.g., cannot create cache).
    """
    # Fallback to hardlink-based copy for unchanged files when reflinks aren't available
    # This fallback is particularly important for CI/CD environments like GitHub Actions
    # which typically run on Ubuntu with ext4 filesystems that don't support reflinks.
    # Without this fallback, workflows running in such environments would experience
    # significantly higher inode consumption and potential performance issues.

    # Use a persistent cache for hardlinks under the tmt workdir_root
    # Note: The cache directory is located under the tmt workdir_root.
    # Cleanup should be handled by tmt's workdir cleanup mechanisms if needed,
    # or potentially a dedicated 'tmt clean --cache' command.
    cache_dir = workdir_root / 'cache' / 'files'  # Define before try
    try:
        cache_base = workdir_root / 'cache'
        cache_base.mkdir(exist_ok=True)
        # Use a sub-directory for this specific file content cache
        cache_dir.mkdir(exist_ok=True)
        logger.debug(f"Using file cache directory: '{cache_dir}'")
    except OSError as e:
        logger.warning(
            f"Failed to create cache directory '{cache_dir}': {e}. Cannot use hardlink cache."
        )
        return False

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
        logger.debug(f"Source directory '{src}' does not exist, skipping hardlink copy")
        return True  # Not a failure of this method, just nothing to copy

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

    if hardlink_count > 0 or regular_copy_count > 0:
        logger.debug(
            f"Directory copied using hardlink/cache strategy: {hardlink_count} hardlinked, "
            f"{regular_copy_count} regular copies"
        )
    else:
        # This case might happen if src was empty or only contained empty dirs
        logger.debug("Hardlink/cache strategy finished (no files copied/linked).")

    return True


def _copy_tree_basic(
    src: Path,
    dst: Path,
    logger: 'tmt.log.Logger',
    workdir_root: Path,
) -> bool:
    """
    Perform a basic recursive copy of a directory tree.

    Handles files, directories, and symlinks using standard shutil operations.
    Returns True on successful completion.
    """
    logger.debug(f"Performing basic copy from '{src}' to '{dst}'")

    if not dst.exists():
        dst.mkdir(parents=True, exist_ok=True)

    if not src.exists():
        logger.debug(f"Source directory '{src}' does not exist, skipping basic copy")
        return True

    copied_count = 0
    try:
        for item in src.rglob('*'):
            relative_path = item.relative_to(src)
            dst_item = dst / relative_path

            if item.is_dir():
                dst_item.mkdir(parents=True, exist_ok=True)
                shutil.copystat(item, dst_item)
            elif item.is_file():
                dst_item.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, dst_item)  # copy2 preserves metadata
                copied_count += 1
            elif item.is_symlink():
                if dst_item.exists() or dst_item.is_symlink():
                    dst_item.unlink()
                link_target = os.readlink(item)
                os.symlink(link_target, dst_item)
                copied_count += 1  # Count symlinks as copied items
    except Exception as e:
        logger.warning(f"Basic copy failed during processing: {e}")
        return False

    logger.debug(f"Directory copied using basic copy: {copied_count} items processed.")
    return True


def copy_tree(
    src: Path,
    dst: Path,
    logger: 'tmt.log.Logger',
    workdir_root: Path,
) -> None:
    """
    Copy directory efficiently, trying different strategies.

    Attempts strategies in order:
    1. Reflinks (copy-on-write)
    2. Hardlinks with persistent caching for unchanged files
    3. Basic recursive copy

    Symlinks are always preserved.

    :param src: Source directory path
    :param dst: Destination directory path
    :param logger: Logger to use for debug messages
    :param workdir_root: The root directory for tmt's working files (e.g., /var/tmp/tmt),
                         used for the hardlink cache.
    """
    logger.debug(f"Copying directory tree from '{src}' to '{dst}'")

    # 1. Try reflink copy
    if _copy_tree_reflinks(src, dst, logger, workdir_root):
        logger.debug("Copy finished using reflink strategy.")
        return

    # 2. Try hardlink with cache copy
    # TODO Implement this!
    # if _copy_tree_hardlinks(src, dst, logger, workdir_root):
    #    logger.debug("Copy finished using hardlink/cache strategy.")
    #    return

    # 3. Fallback to basic copy
    # This should ideally only be reached if hardlinks failed catastrophically
    # (e.g., cache dir issue) or if we explicitly add conditions to skip hardlinks.
    logger.debug("Falling back to basic copy strategy.")
    if _copy_tree_basic(src, dst, logger, workdir_root):
        logger.debug("Copy finished using basic copy strategy.")
        return

    # Should not be reached if _copy_tree_basic always returns True on completion,
    # unless it encounters an error and returns False.
    logger.warning(f"All copy strategies failed for '{src}' to '{dst}'.")
    # Raise exception here?


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
