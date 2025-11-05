from __future__ import annotations

import re
import typing

import fmf.utils
from docutils.parsers.rst import directives
from sphinx.domains import Index, IndexEntry
from sphinx.util import logging

import tmt.base
from tmt._compat.pathlib import Path
from tmt.base import Story
from tmt.utils.git import web_git_url

from .autodoc import Content
from .base import TmtAutodocDirective, TmtDirective

if typing.TYPE_CHECKING:
    from collections.abc import Iterable

    from .domain import TmtDomain


logger = logging.getLogger(__name__)

EXAMPLE_SYNTAX = re.compile(r"^# syntax: (?P<syntax>[a-z]+)")
DOCS_LINK = re.compile(r"^/docs(?P<doc>/.+)\.rst(?:#.*)?$")


# Note: Cannot make this a TmtObjectDirective because this directive has page titles
class StoryDirective(TmtDirective):
    has_content = True
    required_arguments = 1
    option_spec = {
        "title": directives.unchanged_required,
    }

    def run(self):
        name = self.arguments[0]
        title = self.options.get("title", name.split("/")[-1])

        self.tmt_domain.stories[name] = IndexEntry(
            name=title,
            subtype=0,
            docname=self.env.docname,
            # TODO: Would this anchor actually work?
            anchor=name,
            extra="",
            qualifier="",
            # TODO: What to actually add for the descr?
            descr=title,
        )

        return self.parse_content_to_nodes(allow_section_headings=True)


class AutoStoryDirective(TmtAutodocDirective[Story]):
    option_spec = {
        "title": directives.unchanged_required,
    }

    @property
    def story(self) -> Story:
        return self.tmt_object

    def _get_tmt_object(self) -> None:
        name = self.arguments[0]
        name_re = f"^{name}$"
        stories = self.tmt_tree.stories(names=[name_re])
        if not stories:
            raise ValueError(f"Story {name} not found in tree {self.tmt_tree.root}")
        if len(stories) > 1:
            raise ValueError(f"Multiple stories matched '{name_re}'")
        self.tmt_object = stories[0]
        for source in self.story.node.sources:
            self.env.note_dependency(source)

    def _has_story_attr(self, attr: str) -> bool:
        return (value := getattr(self.story, attr)) and value != self.story.node.parent.get(attr)

    def _add_title_content(self, title: str) -> None:
        # TODO: Find a better way to insert the anchor
        self.content.append(f".. _{self.story.name}:", source="")
        self.content.append("", source="")
        self.content.append(title, source="")
        self.content.append("=" * len(title), source="")
        self.content.append("", source="")

    def _generate_leaf_story_content(self) -> None:
        title = self.story.name.split("/")[-1]
        if self._has_story_attr("title"):
            # We only use the title if it is specific to the current story (not inherited)
            title = self.story.title
        if "title" in self.options:
            title = self.options["title"]
        with self.content.directive("tmt:story", self.story.name, title=title):
            # TODO: better handling of `source` reference.
            self._add_title_content(title)
            if self._has_story_attr("summary"):
                self.content.append(self.story.summary, source="")
                self.content.append("", source="")
            if self._has_story_attr("story"):
                self.content.append(f"*{self.story.story}*", source="")
                self.content.append("", source="")
            if not self.story.implemented:
                # We are assuming we only document leaf stories
                self.content.append(
                    ".. note:: This is a draft, the story is not implemented yet.", source=""
                )
                self.content.append("", source="")
            if self._has_story_attr("description"):
                self.content.extend(Content(self.story.description.splitlines(), source=""))
                self.content.append("", source="")
            if self._has_story_attr("example"):
                self.content.append("**Examples:**", source="")
                self.content.append("", source="")
                for example in self.story.example:
                    syntax = "yaml"
                    if match := EXAMPLE_SYNTAX.search(example):
                        syntax = match.group("syntax")
                    with self.content.directive("code-block", syntax):
                        self.content.extend(Content(example.splitlines(), source=""))
            self.content.append(
                f"**Status:** {fmf.utils.listed(self.story.status) or 'idea'}", source=""
            )
            self.content.append("", source="")
            if self.story.link:
                with self.content.list():
                    for link in self.story.link.get():
                        self.content.new_item()
                        self.content.append(self._handle_link(link), source="")

    def _generate_branch_story_content(self) -> None:
        title = self.story.title or self.story.name.split("/")[-1]
        if "title" in self.options:
            title = self.options["title"]
        with self.content.directive("tmt:story", self.story.name, title=title):
            self._add_title_content(title)
            if self.story.story:
                self.content.append(f"*{self.story.story}*", source="")
                self.content.append("", source="")

            if self.story.link:
                with self.content.list():
                    for link in self.story.link.get():
                        self.content.new_item()
                        self.content.append(self._handle_link(link), source="")

            for child in self.story.node.children:
                with self.content.directive("tmt:autostory", f"{self.story.name}/{child}"):
                    pass

    def _generate_autodoc_content(self) -> None:
        if self.story.node.children:
            self._generate_branch_story_content()
        else:
            self._generate_leaf_story_content()

    def _handle_link(self, link: tmt.base.Link) -> str:
        relation = link.relation.replace("relates", "relates-to").replace("-", " ").capitalize()
        # TODO: Generalize this handling to a custom xref role
        # TODO: Handle tmt objects, plugins etc.
        if match := DOCS_LINK.search(link.target):
            # Special handling for doc links
            target = f":doc:`{match.group('doc')}`"
        elif link.target.startswith(("https://", "http://")):
            # External links
            target = f"``<{link.target}>_"
        elif (self.tmt_tree.root / Path(link.target).unrooted()).exists():
            # If these are files relative to the tmt tree use git repo links
            target_url = web_git_url(
                self.story.fmf_id.url, self.story.fmf_id.ref, Path(link.target)
            )
            label = link.target
            target = f"`{label} <{target_url}>`_"
        else:
            target = f"``{link.target}``"
        return f"{relation} {target}{link.note or ''}"


class StoryIndex(Index):
    name = "storyindex"
    localname = "Tmt Story Index"
    shortname = "story"
    domain: TmtDomain

    def generate(
        self, docnames: Iterable[str] | None = None
    ) -> tuple[list[tuple[str, list[IndexEntry]]], bool]:
        content = {}
        # TODO: What to actually use for key-value in the index?
        for story, index_item in self.domain.stories.items():
            index_key = story.split("/")[0]
            entries = content.setdefault(index_key, [])
            entries.append(index_item)
        return sorted(content.items()), True
