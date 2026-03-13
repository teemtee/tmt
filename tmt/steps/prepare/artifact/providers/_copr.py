"""
Shared COPR utilities for copr-based artifact providers.
"""

import types
from abc import abstractmethod
from functools import cached_property
from typing import Any, Optional

import tmt.log
import tmt.utils
import tmt.utils.hints
from tmt.steps.prepare.artifact.providers import ArtifactProvider

copr: Optional[types.ModuleType] = None

# To silence mypy
Client: Any

tmt.utils.hints.register_hint(
    'artifact-provider/copr',
    """
The ``copr`` Python package is required by tmt for Copr integration.

To quickly test Copr presence, you can try running:

    python -c 'import copr'

* Users who installed tmt from PyPI should install the ``copr`` package
  via ``pip install copr``.
""",
)


def import_copr(logger: tmt.log.Logger) -> None:
    """Import copr module with error handling."""
    global copr, Client
    try:
        import copr
        from copr.v3 import Client
    except ImportError as error:
        from tmt.utils.hints import print_hints

        print_hints('artifact-provider/copr', logger=logger)

        raise tmt.utils.GeneralError("Could not import copr package.") from error


class CoprArtifactProvider(ArtifactProvider):
    """
    Base class for COPR-based artifact providers.
    """

    def __init__(self, raw_id: str, repository_priority: int, logger: tmt.log.Logger) -> None:
        super().__init__(raw_id, repository_priority, logger)
        self._session = self._initialize_session()

    def _initialize_session(self) -> 'Client':
        """
        Initialize copr client session.
        """
        import_copr(self.logger)

        try:
            config = {"copr_url": "https://copr.fedorainfracloud.org"}
            return Client(config)
        except Exception as error:
            raise tmt.utils.GeneralError("Failed to initialize Copr client session.") from error

    @property
    @abstractmethod
    def _copr_owner(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def _copr_project(self) -> str:
        raise NotImplementedError

    @cached_property
    def project_info(self) -> Any:
        """
        Fetch and return the COPR project metadata.
        """
        try:
            return self._session.project_proxy.get(
                ownername=self._copr_owner, projectname=self._copr_project
            )
        except Exception as error:
            raise tmt.utils.GeneralError(
                f"Failed to fetch COPR project info for '{self._copr_owner}/{self._copr_project}'."
            ) from error
