import typing
from functools import cached_property

from sphinx.domains import Domain
from sphinx.util import logging

import tmt
import tmt.log

if typing.TYPE_CHECKING:
    from docutils import nodes
    from sphinx.addnodes import pending_xref
    from sphinx.builders import Builder
    from sphinx.environment import BuildEnvironment

    from tmt._compat.pathlib import Path


logger = logging.getLogger(__name__)


class TmtDomain(Domain):
    name = "tmt"
    label = "Internal tmt sphinx domain"
    roles = {}
    directives = {}
    indices = []
    initial_data = {}
    data_version = 0

    # TODO: Cannot save many of these attributes in data because we need a mechanism to invalidate
    #  the data
    _trees: dict["Path", tmt.Tree] | None = None

    @cached_property
    def tmt_logger(self) -> tmt.log.Logger:
        # TODO: Figure out how to pass it the logger.logger and how to skip all the messages
        return tmt.log.Logger.create(quiet=True)

    @property
    def tmt_trees(self) -> dict["Path", tmt.Tree]:
        if self._trees is None:
            self._trees = {}
        return self._trees

    def resolve_any_xref(
        self,
        env: "BuildEnvironment",
        fromdocname: str,
        builder: "Builder",
        target: str,
        node: "pending_xref",
        contnode: "nodes.Element",
    ) -> list[tuple[str, "nodes.reference"]]:
        # TODO: Convert the current :ref:`/plugins/...` for easier transition
        return []
