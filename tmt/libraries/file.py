import shutil
from typing import Optional

import fmf
import fmf.utils

import tmt
import tmt.base
import tmt.log
import tmt.utils
from tmt.base import DependencyFile
from tmt.utils import Path

from . import Library


class File(Library):
    """
    Required files

    Takes care of copying required files for specific test or library,
    more details here:
    https://tmt.readthedocs.io/en/latest/spec/tests.html#require

    Optional 'parent' object inheriting from tmt.utils.Common can be
    provided in order to share the cache of already fetched libraries.

    The following attributes are available in the object:

    repo ........ library prefix (git repository name or nick if provided)
    pattern ..... filename paths and regexes which need to be copied
    """

    def __init__(
            self,
            *,
            identifier: DependencyFile,
            parent: Optional[tmt.utils.Common] = None,
            logger: tmt.log.Logger,
            source_location: Path,
            target_location: Path) -> None:
        super().__init__(parent=parent, logger=logger)

        self.identifier = identifier
        self.format = 'file'
        self.repo = Path(target_location.name)
        self.name = "/files"
        self.pattern: list[str] = identifier.pattern if hasattr(identifier, 'pattern') else []
        self.source_location: Path = source_location
        self.target_location: Path = target_location

    def fetch(self) -> None:
        """ Copy the files over to target location """
        patterns = fmf.utils.listed(self.pattern, quote="'")
        self.parent.debug(
            f"Searching for patterns {patterns} in directory '{self.source_location}.")
        files: list[Path] = tmt.utils.filter_paths(self.source_location, self.pattern)
        if not files:
            self.parent.debug('No files found.')
            raise tmt.utils.MetadataError(
                f"Patterns {patterns} don't match any files in '{self.source_location}'.")

        # Nothing to do if source and target directory are identical.
        # Could be called at the very start of the method but we still
        # want to check for invalid patterns to warn users about
        # possible typos even before the file prunning is enabled.
        if self.source_location == self.target_location:
            self.parent.debug('Source path and target path are the same, ignoring.')
            return

        self.parent.debug(f'Found paths: {", ".join(str(f) for f in files)}')
        for path in files:
            if path.is_dir():
                local_path = path.relative_to(self.source_location)
            else:
                local_path = path.relative_to(self.source_location).parent
            target_path = Path(self.target_location) / local_path
            if path.is_dir():
                try:
                    shutil.copytree(path, target_path, dirs_exist_ok=True)
                except shutil.Error as exc:  # ignore individual files exist error
                    self.parent.debug(str(exc))
            else:
                target_path.mkdir(parents=True, exist_ok=True)
                target_path = target_path / path.name
                if not target_path.exists():
                    shutil.copyfile(path, target_path)
                    shutil.copymode(path, target_path)
