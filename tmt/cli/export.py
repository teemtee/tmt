"""``tmt * export`` implementation"""

from typing import Any, Optional

import tmt.base
import tmt.utils
from tmt.cli import Context, pass_context
from tmt.cli._root import (
    _load_policies,
    environment_options,
    filtering_options_long,
    plans,
    policy_options,
    stories,
    story_flags_filter_options,
    tests,
)
from tmt.options import Deprecated, option
from tmt.utils import Path

_test_export_formats = list(tmt.Test.get_export_plugin_registry().iter_plugin_ids())
_test_export_default = 'yaml'


@tests.command(name='export')
@pass_context
@filtering_options_long
@option(
    '-h',
    '--how',
    default=_test_export_default,
    show_default=True,
    help='Output format.',
    choices=_test_export_formats,
)
@option(
    '--format',
    default=_test_export_default,
    show_default=True,
    help='Output format.',
    deprecated=Deprecated('1.21', hint='use --how instead'),
    choices=_test_export_formats,
)
@option(
    '--nitrate',
    is_flag=True,
    help="Export test metadata to Nitrate.",
    deprecated=Deprecated('1.21', hint="use '--how nitrate' instead"),
)
@option(
    '--project-id',
    help='Use specific Polarion project ID.',
)
@option(
    '--link-polarion / --no-link-polarion',
    default=False,
    is_flag=True,
    help='Add Polarion link to fmf testcase metadata',
)
@option(
    '--bugzilla',
    is_flag=True,
    help="""
         Link Nitrate case to Bugzilla specified in the 'link' attribute with the relation
         'verifies'.
         """,
)
@option(
    '--ignore-git-validation',
    is_flag=True,
    help="""
         Ignore unpublished git changes and export to Nitrate. The case might not be able to be
         scheduled!
         """,
)
@option(
    '--append-summary / --no-append-summary',
    default=False,
    is_flag=True,
    help="""
         Include test summary in the Nitrate/Polarion test case summary as well. By default, only
         the repository name and test name are used.
         """,
)
@option(
    '--create',
    is_flag=True,
    help="Create test cases in nitrate if they don't exist.",
)
@option(
    '--general / --no-general',
    default=False,
    is_flag=True,
    help="""
         Link Nitrate case to component's General plan. Disabled by default. Note that this will
         unlink any previously connected general plans.
         """,
)
@option(
    '--link-runs / --no-link-runs',
    default=False,
    is_flag=True,
    help="""
         Link Nitrate case to all open runs of descendant plans of General plan. Disabled by
         default. Implies --general option.
         """,
)
@option(
    '--fmf-id',
    is_flag=True,
    help='Show fmf identifiers instead of test metadata.',
)
@option(
    '--duplicate / --no-duplicate',
    default=False,
    show_default=True,
    is_flag=True,
    help="""
         Allow or prevent creating duplicates in Nitrate by searching for existing test cases with
         the same fmf identifier.
         """,
)
@option(
    '-n',
    '--dry',
    is_flag=True,
    help="Run in dry mode. No changes, please.",
)
@option(
    '-d',
    '--debug',
    is_flag=True,
    help='Provide as much debugging details as possible.',
)
# TODO: move to `template` export plugin options
@option(
    '--template',
    metavar='PATH',
    help="Path to a template to use for rendering the export. Used with '--how=template' only.",
)
@policy_options
def tests_export(
    context: Context,
    format: str,
    how: str,
    nitrate: bool,
    bugzilla: bool,
    template: Optional[str],
    policy_file: Optional[Path],
    policy_name: Optional[str],
    policy_root: Optional[Path],
    **kwargs: Any,
) -> None:
    """
    Export test data into the desired format.

    Regular expression can be used to filter tests by name.
    Use '.' to select tests under the current working directory.
    """

    tmt.Test.store_cli_invocation(context)

    if nitrate:
        context.obj.logger.warning(
            "Option '--nitrate' is deprecated, please use '--how nitrate' instead."
        )
        how = 'nitrate'

    if format != _test_export_default:
        context.obj.logger.warning("Option '--format' is deprecated, please use '--how' instead.")

        how = format

    # TODO: move this "requires bugzilla" flag to export plugin level.
    if bugzilla and how not in ('nitrate', 'polarion'):
        raise tmt.utils.GeneralError(
            "The --bugzilla option is supported only with --nitrate or --polarion for now."
        )

    if kwargs.get('fmf_id'):
        context.obj.print(
            tmt.base.FmfId.export_collection(
                collection=[test.fmf_id for test in context.obj.tree.tests()],
                format=how,
                template=Path(template) if template else None,
            )
        )

    else:
        tests = context.obj.tree.tests()

        policies = _load_policies(policy_name, policy_file, policy_root)

        for policy in policies:
            policy.apply_to_tests(tests=tests, logger=context.obj.logger)

        context.obj.print(
            tmt.Test.export_collection(
                collection=tests,
                format=how,
                template=Path(template) if template else None,
            )
        )


_plan_export_formats = list(tmt.Plan.get_export_plugin_registry().iter_plugin_ids())
_plan_export_default = 'yaml'


@plans.command(name='export')
@pass_context
@filtering_options_long
@option(
    '-h',
    '--how',
    default=_plan_export_default,
    show_default=True,
    help='Output format.',
    choices=_plan_export_formats,
)
@option(
    '--format',
    default=_plan_export_default,
    show_default=True,
    help='Output format.',
    deprecated=Deprecated('1.21', hint='use --how instead'),
    choices=_plan_export_formats,
)
@option(
    '-d',
    '--debug',
    is_flag=True,
    help='Provide as much debugging details as possible.',
)
# TODO: move to `template` export plugin options
@option(
    '--template',
    metavar='PATH',
    help="Path to a template to use for rendering the export. Used with '--how=template' only.",
)
@environment_options
def plans_export(
    context: Context, how: str, format: str, template: Optional[str], **kwargs: Any
) -> None:
    """
    Export plans into desired format.

    Regular expression can be used to filter plans by name.
    Use '.' to select plans under the current working directory.
    """
    tmt.Plan.store_cli_invocation(context)

    if format != _test_export_default:
        context.obj.logger.warning("Option '--format' is deprecated, please use '--how' instead.")

        how = format

    context.obj.print(
        tmt.Plan.export_collection(
            collection=context.obj.tree.plans(),
            format=how,
            template=Path(template) if template else None,
        )
    )


_story_export_formats = list(tmt.Story.get_export_plugin_registry().iter_plugin_ids())
_story_export_default = 'yaml'


@stories.command(name='export')
@pass_context
@filtering_options_long
@story_flags_filter_options
@option(
    '-h',
    '--how',
    default=_story_export_default,
    show_default=True,
    help='Output format.',
    choices=_story_export_formats,
)
@option(
    '--format',
    default=_story_export_default,
    show_default=True,
    help='Output format.',
    deprecated=Deprecated('1.21', hint='use --how instead'),
    choices=_story_export_formats,
)
@option(
    '-d',
    '--debug',
    is_flag=True,
    help='Provide as much debugging details as possible.',
)
# TODO: move to `template` export plugin options
@option(
    '--template',
    metavar='PATH',
    help="""
         Path to a template to use for rendering the export. Used with '--how=rst|template' only.
         """,
)
def stories_export(
    context: Context,
    how: str,
    format: str,
    implemented: bool,
    verified: bool,
    documented: bool,
    covered: bool,
    unimplemented: bool,
    unverified: bool,
    undocumented: bool,
    uncovered: bool,
    template: Optional[str],
    **kwargs: Any,
) -> None:
    """
    Export selected stories into desired format.

    Regular expression can be used to filter stories by name.
    Use '.' to select stories under the current working directory.
    """
    tmt.Story.store_cli_invocation(context)

    if format != _test_export_default:
        context.obj.logger.warning("Option '--format' is deprecated, please use '--how' instead.")

        how = format

    stories = [
        story
        for story in context.obj.tree.stories(whole=True)
        if story._match(
            implemented,
            verified,
            documented,
            covered,
            unimplemented,
            unverified,
            undocumented,
            uncovered,
        )
    ]

    context.obj.print(
        tmt.Story.export_collection(
            collection=stories, format=how, template=Path(template) if template else None
        )
    )
