import re
import typing
from collections.abc import Callable, Iterable

import fmf.utils
from docutils import nodes
from docutils.parsers.rst import directives
from sphinx import addnodes
from sphinx.domains import Index, IndexEntry
from sphinx.util import logging

import tmt.base
from tmt._compat.pathlib import Path
from tmt.base import Story
from tmt.utils.git import web_git_url

from .autodoc import Content
from .base import TmtAutodocDirective, TmtDirective, TmtXRefRole

if typing.TYPE_CHECKING:
    from .domain import TmtDomain


logger = logging.getLogger(__name__)

EXAMPLE_SYNTAX = re.compile(r"^# syntax: (?P<syntax>[a-z]+)")
DOCS_LINK = re.compile(r"^/docs(?P<doc>/.+)\.rst(?:#.*)?$")


# Note: Cannot make this a TmtObjectDirective because this injects a signature node that we
# otherwise want to remove and it cannot inject titles as we want instead.
# TODO: Move to `ObjectDescription` once upstream generalizes it
#  https://github.com/sphinx-doc/sphinx/issues/14042
class StoryDirective(TmtDirective):
    has_content = True
    required_arguments = 1
    option_spec = {
        "title": directives.unchanged_required,
    }

    def run(self):
        name = self.arguments[0]
        title = self.options.get("title", name.split("/")[-1])

        self.tmt_domain.note_object(
            typ="story",
            name=name,
            entry=IndexEntry(
                name=title,
                subtype=0,
                docname=self.env.docname,
                # TODO: Would this anchor actually work?
                anchor=name,
                extra="",
                qualifier="",
                # TODO: What to actually add for the descr?
                descr=title,
            ),
        )

        # Replicating much of the logic of `ObjectDescription`
        # Include a compatibility target for `/spec/plans/provision` to `spec-plans-provision`
        # This was the older target with global refs
        compat_target = name[1:].replace("/", "-")
        target_node = nodes.target(ids=[name, compat_target])
        node = nodes.paragraph()
        index_node = addnodes.index(entries=[])
        node += self.parse_content_to_nodes(allow_section_headings=True)
        return [
            index_node,
            target_node,
            *node.children,
        ]


class AutoStoryDirective(TmtAutodocDirective[Story]):
    option_spec = {
        "title": directives.unchanged_required,
    }

    @property
    def story(self) -> Story:
        return self.tmt_object

    def _get_tmt_object(self) -> None:
        name = self.arguments[0]
        name_re = f"^{re.escape(name)}$"
        stories = self.tmt_tree.stories(names=[name_re], whole=True)
        if not stories:
            raise ValueError(f"Story {name} not found in tree {self.tmt_tree.root}")
        if len(stories) > 1:
            raise ValueError(f"Multiple stories matched '{name_re}'")
        self.tmt_object = stories[0]
        for source in self.story.node.sources:
            self.env.note_dependency(source)

    def _has_story_attr(self, attr: str) -> bool:
        value = getattr(self.story, attr)
        if not value:
            # Attribute was not provided
            return False
        if not self.story.node.parent:
            # There is no parent story, so we know this attribute belongs to this
            return True
        # Otherwise we check if we have inherited the value (return False if it was inherited)
        return value != self.story.node.parent.get(attr)

    def _add_title_content(self, title: str) -> None:
        # TODO: Find a better way to insert the title
        self.append(title)
        self.append("=" * len(title))
        self.new_line()

    def _add_story_content(
        self,
        section: str,
        *,
        source_suffix: str = "",
        content: typing.Optional[str] = None,
        transform_line: Callable[[str], str] = lambda x: x,
        new_line: bool = True,
    ) -> None:
        """
        Add content lines from a story section in the current content object.

        :param section: story section used as the source reference
        :param source_suffix: additional info used for the source annotation
        :param content: content to use instead of the ``section`` story attribute
        :param transform_line: transformation function applied for each line in the content
        :param new_line: make sure the content is terminated by a blank new line
        """
        if not self._has_story_attr(section):
            # Do nothing if the story does not have the current section
            return

        # TODO: better handling of `source` reference directly from the fmf files.
        source = f"story[{self.story.name}].{section}{source_suffix}"
        content = content or getattr(self.story, section)
        assert isinstance(content, str)
        if not content.strip():
            return
        content_lines = content.splitlines()
        content_lines = [transform_line(line) for line in content_lines]
        if new_line and content_lines[-1].strip():
            content_lines.append("")
        section_content = Content(
            content_lines,
            source=source,
            parent=self.content,
            parent_offset=next(self.content_offset_count),
        )
        self.content.extend(section_content)

    def _generate_leaf_story_content(self) -> None:
        title = self.story.name.split("/")[-1]
        if self._has_story_attr("title"):
            # We only use the title if it is specific to the current story (not inherited)
            title = self.story.title
        if "title" in self.options:
            title = self.options["title"]
        with self.directive(
            "tmt:story",
            self.story.name,
            title=title,
        ):
            self._add_title_content(title)
            self._add_story_content("summary")
            self._add_story_content("story", transform_line=lambda line: f"*{line}*")
            if not self.story.implemented:
                # We are assuming we only document leaf stories
                with self.directive("note"):
                    self.append("This is a draft, the story is not implemented yet.")
            self._add_story_content("description")
            if self._has_story_attr("example"):
                self.append("**Examples:**")
                self.new_line()
                for ind, example in enumerate(self.story.example):
                    syntax = "yaml"
                    if match := EXAMPLE_SYNTAX.search(example):
                        syntax = match.group("syntax")
                        example = example.replace(match.group(0), "")
                    with self.directive("code-block", syntax):
                        self._add_story_content(
                            "example",
                            source_suffix=f"[{ind}]",
                            content=example,
                        )
            self.append(f"**Status:** {fmf.utils.listed(self.story.status) or 'idea'}")
            self.new_line()
            self._generate_links_content()

    def _generate_branch_story_content(self) -> None:
        if "title" in self.options:
            title = self.options["title"]
        elif self._has_story_attr("title"):
            title = self.story.title
        else:
            title = self.story.name.split("/")[-1]

        with self.directive("tmt:story", self.story.name, title=title):
            self._add_title_content(title)
            self._add_story_content("story", transform_line=lambda line: f"*{line}*")
            self._generate_links_content()

            for child in self.story.node.children:
                with self.directive("tmt:autostory", f"{self.story.name}/{child}"):
                    pass

    def _generate_links_content(self) -> None:
        if not self.story.link:
            return
        with self.new_list():
            for ind, link in enumerate(self.story.link.get()):
                self.new_item()
                self._add_story_content(
                    "link",
                    source_suffix=f"[{ind}]",
                    content=self._handle_link(link),
                    new_line=False,
                )

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
            target = f"`{link.target} <{link.target}>`_"
        elif (self.tmt_tree.root / Path(link.target).unrooted()).exists():
            # If these are files relative to the tmt tree use git repo links
            target_url = web_git_url(
                self.story.fmf_id.url, self.story.fmf_id.ref, Path(link.target)
            )
            label = link.target
            target = f"`{label} <{target_url}>`_"
        else:
            target = f"``{link.target}``"
        return f"{relation} {target} {link.note or ''}"


class StoryIndex(Index):
    name = "storyindex"
    localname = "Tmt Story Index"
    shortname = "story"
    domain: "TmtDomain"

    def generate(
        self, docnames: Iterable[str] | None = None
    ) -> tuple[list[tuple[str, list[IndexEntry]]], bool]:
        content = {}
        # TODO: What to actually use for key-value in the index?
        for story, index_item in self.domain.objects.get("story", {}).items():
            index_key = story.split("/")[0]
            entries = content.setdefault(index_key, [])
            entries.append(index_item)
        return sorted(content.items()), True


class StoryRole(TmtXRefRole):
    # The default literal node formats the string as a code.
    # Using inline instead, same as sphinx's `ref` role (`sphinx.domains.std`)
    innernodeclass = nodes.inline
    # We want to use the story titles here. See `tmt_domain.note_object` call in
    # `StoryDirective.run` for the index entry that we created.
    use_obj_name = True
