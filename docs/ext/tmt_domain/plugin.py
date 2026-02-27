import inspect
from typing import Generic, Optional

from docutils.statemachine import string2lines
from sphinx.util import logging

from tmt.plugins import REGISTRIES, PluginRegistry, RegisterableT

from .autodoc import Content
from .base import TmtAutodocDirective

logger = logging.getLogger(__name__)


class AutoPluginDirective(TmtAutodocDirective[RegisterableT], Generic[RegisterableT]):
    plugin_id: Optional[str] = None
    registry: PluginRegistry[RegisterableT]

    def _get_tmt_object(self) -> None:
        raw_names = self.arguments[0].split("/", maxsplit=1)
        registry_name = raw_names[0]
        try:
            self.registry = next(
                registry for registry in REGISTRIES if registry.name == registry_name
            )
        except Exception as exc:
            raise ValueError(f"Registry '{registry_name}' not found.") from exc
        if len(raw_names) == 1:
            # Requested to document all plugins, nothing more to do here
            self.tmt_object = None
            return
        self.plugin_id = raw_names[1]
        plugin = self.registry.get_plugin(self.plugin_id)
        if not plugin:
            raise ValueError(f"Plugin '{self.plugin_id}' in '{registry_name}' registry not found.")
        self.tmt_object = plugin

    def _generate_plugin_content(self) -> None:
        assert self.tmt_object  # Narrow type
        assert self.plugin_id  # Narrow type
        docstring = inspect.getdoc(self.tmt_object)
        with self.directive("tmt:plugin", f"{self.plugin_id}"):
            if docstring:
                # TODO: see if we can reuse something from sphinx autodoc? We might not be able to
                #  without hitting the same import issues we had with z_autodoc.
                source_file = inspect.getsourcefile(self.tmt_object)
                source_name = ""
                if not source_file:
                    source_name = f"{source_file}:doscstring of {self.plugin_id}"
                    self.env.note_dependency(source_file)
                else:
                    logger.warning(f"Could not find source_file of {self.tmt_object}")
                self.content.extend(
                    Content(
                        string2lines(docstring),
                        source=source_name,
                        parent=self.content,
                        parent_offset=next(self.content_offset_count),
                    )
                )

    def _generate_all_plugins_content(self) -> None:
        for plugin_id in self.registry.iter_plugin_ids():
            with self.directive("tmt:autoplugin", f"{self.registry.name}/{plugin_id}"):
                pass

    def _generate_autodoc_content(self) -> None:
        if not self.tmt_object:
            self._generate_all_plugins_content()
        else:
            self._generate_plugin_content()
