"""
Utility functions for filesystem operations.
"""

import shutil
from typing import Optional

import tmt.log
import tmt.utils.git
from tmt._compat.pathlib import Path
from tmt.utils import Command, GeneralError, RunError


def _git_root(src: Path, logger: tmt.log.Logger) -> Optional[Path]:
    """
    Return the git repository root containing ``src``, or ``None``.
    """
    try:
        return tmt.utils.git.git_root(fmf_root=src, logger=logger)
    except Exception:
        return None


def _get_git_excludes(src: Path, logger: tmt.log.Logger) -> list[Path]:
    """
    Collect paths to exclude based on git configuration.

    Used only as input for the :py:func:`shutil.copytree` fallback.
    Returns ``.git`` plus all paths ignored by git, or an empty list
    on failure.
    """
    excludes: list[Path] = [Path('.git')]

    try:
        excludes.extend(tmt.utils.git.git_ignore(root=src, logger=logger))
    except Exception:
        logger.debug("Failed to collect git-ignored paths, proceeding without exclusions.")
        return []

    return excludes


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
        Command('cp', '-a', '--reflink=auto', f"{src}/./", str(dst)).run(
            cwd=None, logger=logger, join=True, silent=True
        )
        return True
    except RunError:
        return False


def rsync_with_gitignore_filter(
    src: Path,
    dst: Path,
    logger: tmt.log.Logger,
    *,
    git_root: Optional[Path] = None,
    temp_dir: Optional[Path] = None,
) -> None:
    """
    Copy directory using ``rsync -a`` with native ``.gitignore``
    filtering.

    Uses rsync's ``--filter=':- .gitignore'`` to honour
    ``.gitignore`` rules at every directory level within the source
    tree, without needing ``git`` to be invoked.  When ``src`` is a
    subdirectory of ``git_root``, any ``.gitignore`` files between
    ``src`` and ``git_root`` are included as additional merge filters
    so that repository-wide ignore rules still apply.

    The ``.git`` directory is always excluded.

    :param git_root: path to the git repository root.  When ``None``,
        only ``.gitignore`` files inside ``src`` are honoured.
    :param temp_dir: optional directory for rsync temporary files,
        useful when the default temp directory is on a different
        filesystem.
    :raises RunError: when the rsync command fails.
    """

    parent_filters: list[str] = []
    if git_root:
        current = src.resolve()
        root = git_root.resolve()
        while current not in (root, current.parent):
            current = current.parent
            gitignore = current / '.gitignore'
            if gitignore.is_file():
                parent_filters.extend(('--filter', f'dir-merge,- {gitignore}'))

    temp_dir_args = ('--temp-dir', str(temp_dir)) if temp_dir else ()

    Command(
        'rsync',
        '-a',
        *temp_dir_args,
        *parent_filters,
        "--include=**.gitignore",
        "--exclude=/.git",
        "--filter=:- .gitignore",
        f"{src}/",
        str(dst),
    ).run(cwd=None, logger=logger, join=True, silent=True)


def _copy_tree_rsync(
    src: Path,
    dst: Path,
    logger: tmt.log.Logger,
    git_root: Path,
) -> bool:
    """
    :py:func:`rsync_with_gitignore_filter` wrapper returning a
    boolean success status for the :py:func:`copy_tree` fallback
    chain.
    """
    try:
        rsync_with_gitignore_filter(src, dst, logger, git_root=git_root)
        return True
    except RunError:
        return False


def _copy_tree_shutil(
    src: Path,
    dst: Path,
    logger: tmt.log.Logger,
    excludes: list[Path],
) -> None:
    """
    Perform copy using shutil.copytree.

    This is typically a fallback strategy. The destination directory must
    exist before calling this function.

    :param excludes: list of relative paths to exclude from the copy.
    """
    logger.debug(f"Performing shutil.copytree from '{src}' to '{dst}'")

    exclude_names = {str(path).rstrip('/') for path in excludes}

    def _ignore(directory: str, contents: list[str]) -> set[str]:
        rel = Path(directory).relative_to(src)
        return {
            name
            for name in contents
            if str(rel / name).rstrip('/') in exclude_names or name.rstrip('/') in exclude_names
        }

    shutil.copytree(
        src,
        dst,
        symlinks=True,
        dirs_exist_ok=True,
        ignore=_ignore if excludes else None,
    )


def copy_tree(
    src: Path,
    dst: Path,
    logger: tmt.log.Logger,
) -> None:
    """
    Copy directory efficiently, trying different strategies.

    Files and directories ignored by git (per ``.gitignore`` rules) and
    the ``.git`` directory itself are excluded from the copy when the
    source is inside a git repository. When outside a git repo, all
    files are copied.

    Attempts strategies in order, depending on context:

    When inside a git repository:

    #. ``rsync -a`` with native ``.gitignore`` filtering via
       ``--filter=':- .gitignore'``.
    #. :py:func:`shutil.copytree` with ``ignore`` as a fallback.

    When outside a git repository:

    #. ``cp -a --reflink=auto`` (copy-on-write when supported).
    #. :py:func:`shutil.copytree` as a fallback.

    Symlinks are always preserved. The destination directory `dst` and its
    parents will be created if they do not exist. File permissions and timestamps
    are preserved in all copy strategies.

    :param src: Source directory path. Must exist and be a directory.
    :param dst: Destination directory path.
    :param logger: Logger to use for debug messages.
    :raises GeneralError: when copying fails using all strategies, or if
        ``src`` does not exist or is not a directory.
    """
    logger.debug(f"Copying directory tree from '{src}' to '{dst}'")

    if not src.is_dir():
        raise GeneralError(f"Source '{src}' for copy_tree is not a directory or does not exist.")

    dst.mkdir(parents=True, exist_ok=True)

    git_root = _git_root(src, logger)

    if git_root is not None:
        logger.debug(f"Attempting copy from '{src}' to '{dst}' using rsync with .gitignore filter")
        if _copy_tree_rsync(src, dst, logger, git_root):
            logger.debug("Copy finished using rsync strategy.")
            return

        logger.debug("rsync failed, falling back to shutil.copytree strategy.")
        excludes = _get_git_excludes(src, logger)
        try:
            _copy_tree_shutil(src, dst, logger, excludes)
            logger.debug("Copy finished using shutil.copytree strategy.")
        except Exception as error:
            raise GeneralError(
                f"Failed to copy directory tree from '{src}' to '{dst}' using all strategies."
            ) from error
    else:
        logger.debug(f"Attempting copy from '{src}' to '{dst}' using cp with reflink")
        if _copy_tree_cp(src, dst, logger):
            logger.debug("Copy finished using cp --reflink=auto strategy.")
            return

        logger.debug("cp command failed, falling back to shutil.copytree strategy.")
        try:
            _copy_tree_shutil(src, dst, logger, [])
            logger.debug("Copy finished using shutil.copytree strategy.")
        except Exception as error:
            raise GeneralError(
                f"Failed to copy directory tree from '{src}' to '{dst}' using all strategies."
            ) from error
