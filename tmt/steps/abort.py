import functools

import tmt.log
import tmt.steps.scripts
import tmt.utils
from tmt.container import container
from tmt.utils import (
    Path,
)


class AbortStep(tmt.utils.GeneralError):
    """
    Raised by a plugin phases when the entire step should abort.
    """


@container
class AbortContext:
    """
    Provides API for handling a phase-requested abort of a step.
    """

    #: Path in which the abort request file should be stored.
    path: Path

    #: Used for logging.
    logger: tmt.log.Logger

    @functools.cached_property
    def request_path(self) -> Path:
        """
        A path to the abort request file.
        """

        return self.path / tmt.steps.scripts.TMT_ABORT_SCRIPT.created_file

    @property
    def requested(self) -> bool:
        """
        Whether a testing abort was requested
        """

        return self.request_path.exists()
