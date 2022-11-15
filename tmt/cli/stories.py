""" Command line interface for tmt stories command """

from typing import Any, cast

import click
from click import echo, style
from fmf.utils import listed

import tmt
import tmt.identifier
import tmt.templates
from tmt.cli.click_group import CustomGroup
from tmt.cli.common_options import (filter_options, filter_options_long,
                                    fmf_source_options, force_dry_options,
                                    story_flags_filter_options,
                                    verbosity_options)


@click.group(invoke_without_command=True, cls=CustomGroup)
@click.pass_context
@verbosity_options
def stories(context: click.core.Context, **kwargs: Any) -> None:
    """
    Manage user stories.

    \b
    Check available user stories.
    Explore coverage (test, implementation, documentation).
    """
    tmt.Story._save_context(context)

    # Show overview of available stories
    if context.invoked_subcommand is None:
        tmt.Story.overview(context.obj.tree)


@stories.command(name='ls')
@click.pass_context
@filter_options_long
@story_flags_filter_options
@verbosity_options
def stories_ls(
        context: click.core.Context,
        implemented: bool,
        verified: bool,
        documented: bool,
        covered: bool,
        unimplemented: bool,
        unverified: bool,
        undocumented: bool,
        uncovered: bool,
        **kwargs: Any) -> None:
    """
    List available stories.

    Regular expression can be used to filter stories by name.
    Use '.' to select stories under the current working directory.
    """
    tmt.Story._save_context(context)
    # FIXME: cast() - https://github.com/teemtee/tmt/pull/1592
    for story in cast(tmt.Tree, context.obj.tree).stories():
        if story._match(implemented, verified, documented, covered,
                        unimplemented, unverified, undocumented, uncovered):
            story.ls()


@stories.command(name='show')
@click.pass_context
@filter_options_long
@story_flags_filter_options
@verbosity_options
def stories_show(
        context: click.core.Context,
        implemented: bool,
        verified: bool,
        documented: bool,
        covered: bool,
        unimplemented: bool,
        unverified: bool,
        undocumented: bool,
        uncovered: bool,
        **kwargs: Any) -> None:
    """
    Show story details.

    Regular expression can be used to filter stories by name.
    Use '.' to select stories under the current working directory.
    """
    tmt.Story._save_context(context)
    # FIXME: cast() - https://github.com/teemtee/tmt/pull/1592
    for story in cast(tmt.Tree, context.obj.tree).stories():
        if story._match(implemented, verified, documented, covered,
                        unimplemented, unverified, undocumented, uncovered):
            story.show()
            echo()


_story_templates = listed(tmt.templates.STORY, join='or')


@stories.command(name='create')
@click.pass_context
@click.argument('name')
@click.option(
    '-t', '--template', metavar='TEMPLATE',
    prompt='Template ({})'.format(_story_templates),
    help='Story template ({}).'.format(_story_templates))
@verbosity_options
@force_dry_options
def stories_create(
        context: click.core.Context,
        name: str,
        template: str,
        force: bool,
        **kwargs: Any) -> None:
    """ Create a new story based on given template. """
    tmt.Story._save_context(context)
    tmt.Story.create(name, template, context.obj.tree.root, force)


@stories.command(name='coverage')
@click.option(
    '--docs', is_flag=True, help='Show docs coverage.')
@click.option(
    '--test', is_flag=True, help='Show test coverage.')
@click.option(
    '--code', is_flag=True, help='Show code coverage.')
@click.pass_context
@filter_options_long
@story_flags_filter_options
@verbosity_options
def stories_coverage(
        context: click.core.Context,
        code: bool,
        test: bool,
        docs: bool,
        implemented: bool,
        verified: bool,
        documented: bool,
        covered: bool,
        unimplemented: bool,
        unverified: bool,
        undocumented: bool,
        uncovered: bool,
        **kwargs: Any) -> None:
    """
    Show code, test and docs coverage for given stories.

    Regular expression can be used to filter stories by name.
    Use '.' to select stories under the current working directory.
    """
    tmt.Story._save_context(context)

    def headfoot(text: str) -> None:
        """ Format simple header/footer """
        echo(style(text.rjust(4) + ' ', fg='blue'), nl=False)

    header = False
    total = code_coverage = test_coverage = docs_coverage = 0
    if not any([code, test, docs]):
        code = test = docs = True
    # FIXME: cast() - https://github.com/teemtee/tmt/pull/1592
    for story in cast(tmt.Tree, context.obj.tree).stories():
        # Check conditions
        if not story._match(
                implemented, verified, documented, covered, unimplemented,
                unverified, undocumented, uncovered):
            continue
        # Show header once
        if not header:
            if code:
                headfoot('code')
            if test:
                headfoot('test')
            if docs:
                headfoot('docs')
            headfoot('story')
            echo()
            header = True
        # Show individual stats
        status = story.coverage(code, test, docs)
        total += 1
        code_coverage += status[0]
        test_coverage += status[1]
        docs_coverage += status[2]
    # Summary
    if not total:
        return
    if code:
        headfoot('{}%'.format(round(100 * code_coverage / total)))
    if test:
        headfoot('{}%'.format(round(100 * test_coverage / total)))
    if docs:
        headfoot('{}%'.format(round(100 * docs_coverage / total)))
    headfoot('from {}'.format(listed(total, 'story')))
    echo()


@stories.command(name='export')
@click.pass_context
@filter_options_long
@story_flags_filter_options
@click.option(
    '--format', 'format_', default='rst', show_default=True, metavar='FORMAT',
    help='Output format.')
@click.option(
    '-d', '--debug', is_flag=True,
    help='Provide as much debugging details as possible.')
def stories_export(
        context: click.core.Context,
        format_: str,
        implemented: bool,
        verified: bool,
        documented: bool,
        covered: bool,
        unimplemented: bool,
        unverified: bool,
        undocumented: bool,
        uncovered: bool,
        **kwargs: Any) -> None:
    """
    Export selected stories into desired format.

    Regular expression can be used to filter stories by name.
    Use '.' to select stories under the current working directory.
    """
    tmt.Story._save_context(context)

    # FIXME: cast() - https://github.com/teemtee/tmt/pull/1592
    for story in cast(tmt.Tree, context.obj.tree).stories(whole=True):
        if not story._match(implemented, verified, documented, covered,
                            unimplemented, unverified, undocumented, uncovered):
            continue

        # ignore[call-overload]: overladed superclass methods allow only
        # literal types, and format_ is not a literal. Even when it's a
        # member of ExportFormat enum, it's still a variable.
        # Unfortunately, there's no way to amend this and different
        # return value types depending on input parameter type.
        echo(story.export(format_=tmt.base.ExportFormat(format_)))  # type: ignore[call-overload]


@stories.command(name='lint')
@click.pass_context
@filter_options
@fmf_source_options
@verbosity_options
def stories_lint(context: click.core.Context, **kwargs: Any) -> None:
    """
    Check stories against the L3 metadata specification.

    Regular expression can be used to filter stories by name.
    Use '.' to select stories under the current working directory.
    """
    # FIXME: Workaround https://github.com/pallets/click/pull/1840 for click 7
    context.params.update(**kwargs)
    tmt.Story._save_context(context)
    exit_code = 0
    for story in context.obj.tree.stories():
        if not story.lint():
            exit_code = 1
        echo()
    raise SystemExit(exit_code)


@stories.command(name="id")
@click.pass_context
@filter_options_long
@story_flags_filter_options
@verbosity_options
@force_dry_options
def stories_id(
        context: click.core.Context,
        implemented: bool,
        verified: bool,
        documented: bool,
        covered: bool,
        unimplemented: bool,
        unverified: bool,
        undocumented: bool,
        uncovered: bool,
        **kwargs: Any) -> None:
    """
    Generate a unique id for each selected story.

    A new UUID is generated for each story matching the provided
    filter and the value is stored to disk. Existing identifiers
    are kept intact.
    """
    tmt.Story._save_context(context)
    # FIXME: cast() - https://github.com/teemtee/tmt/pull/1592
    for story in cast(tmt.Tree, context.obj.tree).stories():
        if story._match(implemented, verified, documented, covered,
                        unimplemented, unverified, undocumented, uncovered):
            tmt.identifier.id_command(story.node, "story", dry=kwargs["dry"])
