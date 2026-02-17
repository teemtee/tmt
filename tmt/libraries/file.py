import shutil
from typing import Literal, Optional

import fmf
import fmf.utils

import tmt
import tmt.log
import tmt.utils
from tmt.base import Dependency, DependencyFile
from tmt.container import container
from tmt.utils import Path

from . import Library, LibraryError


@container
class File(Library):
    """
    Required files

    Takes care of copying required files for specific test or library,
    more details here:
    https://tmt.readthedocs.io/en/latest/spec/tests.html#require
    """

    identifier: DependencyFile  # pyright: ignore[reportIncompatibleVariableOverride]
    format: Literal['file']  # pyright: ignore[reportIncompatibleVariableOverride]

    #: Filename paths and regexes which need to be copied
    pattern: list[str]
    #: Root source location of the tests directory of the Discover phase (``test_dir``)
    source_location: Path
    #: Root target location where to copy the file into
    target_location: Path

    @classmethod
    def from_identifier(
        cls,
        *,
        identifier: Dependency,
        parent: Optional[tmt.utils.Common] = None,
        logger: tmt.log.Logger,
        source_location: Optional[Path] = None,
        target_location: Optional[Path] = None,
    ) -> Library:
        assert parent is not None  # narrow type
        assert isinstance(identifier, DependencyFile)  # narrow type
        assert source_location is not None  # narrow type
        assert target_location is not None  # narrow type
        return File(
            parent=parent,
            _logger=logger,
            identifier=identifier,
            format="file",
            repo=Path(target_location.name),
            name="/files",
            pattern=identifier.pattern if hasattr(identifier, 'pattern') else [],
            source_location=source_location,
            target_location=target_location,
        )

    def fetch(self) -> None:
        patterns = fmf.utils.listed(self.pattern, quote="'")
        self.parent.debug(
            f"Searching for patterns {patterns} in directory '{self.source_location}."
        )
        files: list[Path] = tmt.utils.filter_paths(self.source_location, self.pattern)
        if not files:
            self.parent.debug('No files found.')
            raise LibraryError

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
