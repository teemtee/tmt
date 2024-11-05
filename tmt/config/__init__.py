import functools
import os
from contextlib import suppress
from typing import Optional, cast

import fmf
import fmf.utils

import tmt.utils
from tmt._compat.pathlib import Path
from tmt._compat.pydantic import ValidationError
from tmt.config.models.link import LinkConfig

# Config directory
DEFAULT_CONFIG_DIR = Path('~/.config/tmt')


def effective_config_dir() -> Path:
    """
    Find out what the actual config directory is.

    If ``TMT_CONFIG_DIR`` variable is set, it is used. Otherwise,
    :py:const:`DEFAULT_CONFIG_DIR` is picked.
    """

    if 'TMT_CONFIG_DIR' in os.environ:
        return Path(os.environ['TMT_CONFIG_DIR']).expanduser()

    return DEFAULT_CONFIG_DIR.expanduser()


class Config:
    """ User configuration """

    def __init__(self) -> None:
        """ Initialize config directory path """
        self.path = effective_config_dir()
        self.logger = tmt.utils.log

        try:
            self.path.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise tmt.utils.GeneralError(
                f"Failed to create config '{self.path}'.") from error

    @property
    def _last_run_symlink(self) -> Path:
        return self.path / 'last-run'

    @property
    def last_run(self) -> Optional[Path]:
        """ Get the last run workdir path """
        return self._last_run_symlink.resolve() if self._last_run_symlink.is_symlink() else None

    @last_run.setter
    def last_run(self, workdir: Path) -> None:
        """ Set the last run to the given run workdir """

        with suppress(OSError):
            self._last_run_symlink.unlink()

        try:
            self._last_run_symlink.symlink_to(workdir)
        except FileExistsError:
            # Race when tmt runs in parallel
            self.logger.warning(
                f"Unable to mark '{workdir}' as the last run, "
                "'tmt run --last' might not pick the right run directory.")
        except OSError as error:
            raise tmt.utils.GeneralError(
                f"Unable to save last run '{self.path}'.\n{error}")

    @functools.cached_property
    def fmf_tree(self) -> fmf.Tree:
        """ Return the configuration tree """
        try:
            return fmf.Tree(self.path)
        except fmf.utils.RootError as error:
            raise tmt.utils.MetadataError(f"Config tree not found in '{self.path}'.") from error

    @property
    def link(self) -> Optional[LinkConfig]:
        """ Return the link configuration, if present. """
        link_config = cast(Optional[fmf.Tree], self.fmf_tree.find('/link'))
        if not link_config:
            return None
        try:
            return LinkConfig.parse_obj(link_config.data)
        except ValidationError as error:
            raise tmt.utils.SpecificationError(
                f"Invalid link configuration in '{link_config.name}'.") from error
