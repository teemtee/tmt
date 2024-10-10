import email.utils
import os
import re
import types
import urllib.parse
from collections.abc import Iterator
from contextlib import suppress
from functools import cache
from typing import (
    TYPE_CHECKING,
    Any,
    Optional,
    Union,
    cast,
    )

import fmf.context
from click import echo, style

import tmt.export
import tmt.identifier
import tmt.utils
import tmt.utils.git
from tmt.utils import ConvertError, Path
from tmt.utils.structured_field import StructuredField

if TYPE_CHECKING:
    import tmt.base


NITRATE_TRACKER_ID = 69  # ID of nitrate in RH's bugzilla
DEFAULT_NITRATE_CATEGORY = 'Sanity'

WARNING = """
Test case has been migrated to git. Any changes made here might be overwritten.
See: https://tmt.readthedocs.io/en/latest/questions.html#nitrate-migration
""".lstrip()

gssapi: Optional[types.ModuleType] = None
nitrate: Optional[types.ModuleType] = None

# FIXME: Any - https://github.com/teemtee/tmt/issues/1602

# Until nitrate gets its own annotations and recognizable imports...
Nitrate = Any
NitrateTestPlan = Any
NitrateTestCase = Any

DEFAULT_PRODUCT: Any = None

SectionsReturnType = tuple[str, str, str, str]
HeadingsType = list[list[Union[int, str]]]
SectionsHeadingsType = dict[str, HeadingsType]

# TODO: why this exists?
log = fmf.utils.Logging('tmt').logger


def import_nitrate() -> Nitrate:
    """ Conditionally import the nitrate module """
    # Need to import nitrate only when really needed. Otherwise we get
    # traceback when nitrate not installed or config file not available.
    # And we want to keep the core tmt package with minimal dependencies.
    try:
        global nitrate, DEFAULT_PRODUCT, gssapi
        import gssapi
        import nitrate
        assert nitrate
        DEFAULT_PRODUCT = nitrate.Product(name='RHEL Tests')
        return nitrate
    except ImportError:
        raise ConvertError(
            "Install tmt+test-convert to export tests to nitrate.")
    # FIXME: ignore[union-attr]: https://github.com/teemtee/tmt/issues/1616
    except nitrate.NitrateError as error:  # type: ignore[union-attr]
        raise ConvertError(error)


def _nitrate_find_fmf_testcases(test: 'tmt.Test') -> Iterator[Any]:
    """
    Find all Nitrate test cases with the same fmf identifier

    All component general plans are explored for possible duplicates.
    """
    import tmt.base
    assert nitrate
    for component in test.component:
        try:
            for testcase in find_general_plan(component).testcases:
                struct_field = StructuredField(testcase.notes)
                try:
                    fmf_id = tmt.base.FmfId.from_spec(
                        cast(tmt.base._RawFmfId, tmt.utils.yaml_to_dict(struct_field.get('fmf'))))
                    if fmf_id == test.fmf_id:
                        echo(style(
                            f"Existing test case '{testcase.identifier}' "
                            f"found for given fmf id.", fg='magenta'))
                        yield testcase
                except tmt.utils.StructuredFieldError:
                    pass
        except nitrate.NitrateError:
            pass


def convert_manual_to_nitrate(test_md: Path) -> SectionsReturnType:
    """
    Convert Markdown document to html sections.

    These sections can be exported to nitrate.
    Expects: Markdown document as a file.
    Returns: tuple of (step, expect, setup, cleanup) sections
    as html strings.
    """

    import tmt.base

    sections_headings: SectionsHeadingsType = {
        heading: []
        for heading_list in tmt.base.SECTIONS_HEADINGS.values()
        for heading in heading_list
        }

    html = tmt.utils.markdown_to_html(test_md)
    html_splitlines = html.splitlines()

    for key in sections_headings:
        result: HeadingsType = []
        i = 0
        while html_splitlines:
            try:
                if re.search("^" + key + "$", html_splitlines[i]):
                    html_content = ''
                    if key.startswith('<h1>Test'):
                        html_content = html_splitlines[i].\
                            replace('<h1>', '<b>').\
                            replace('</h1>', '</b>')
                    for j in range(i + 1, len(html_splitlines)):
                        if re.search("^<h[1-4]>(.+?)</h[1-4]>$",
                                     html_splitlines[j]):
                            result.append([i, html_content])
                            i = j - 1
                            break
                        html_content += html_splitlines[j] + "\n"
                        # Check end of the file
                        if j + 1 == len(html_splitlines):
                            result.append([i, html_content])
            except IndexError:
                sections_headings[key] = result
                break
            i += 1
            if i >= len(html_splitlines):
                sections_headings[key] = result
                break

    def concatenate_headings_content(headings: tuple[str, ...]) -> HeadingsType:
        content = []
        for v in headings:
            content += sections_headings[v]
        return content

    def enumerate_content(content: HeadingsType) -> HeadingsType:
        # for sorting convert the index to integer, but keep whole list as list of strings
        content.sort(key=lambda a: int(a[0]))
        for i, entry in enumerate(content):
            entry[1] = f"<p>Step {i + 1}.</p>" + str(entry[1])

        return content

    sorted_test = sorted(concatenate_headings_content((
        '<h1>Test</h1>',
        '<h1>Test .*</h1>')))

    sorted_step = sorted(enumerate_content(concatenate_headings_content((
        '<h2>Step</h2>',
        '<h2>Test Step</h2>'))) + sorted_test)
    step = ''.join([f"{v[1]}" for v in sorted_step])

    sorted_expect = sorted(enumerate_content(concatenate_headings_content((
        '<h2>Expect</h2>',
        '<h2>Result</h2>',
        '<h2>Expected Result</h2>'))) + sorted_test)
    expect = ''.join([f"{v[1]}" for v in sorted_expect])

    def check_section_exists(text: str) -> str:
        try:
            return str(sections_headings[text][0][1])
        except (IndexError, KeyError):
            return ''

    setup = check_section_exists('<h1>Setup</h1>')
    cleanup = check_section_exists('<h1>Cleanup</h1>')

    return step, expect, setup, cleanup


def enabled_somewhere(test: 'tmt.Test') -> bool:
    """ True if the test is enabled for some context (adjust rules) """
    # Already enabled, no need to dig deeper
    if test.enabled:
        return True
    # We need to find 'enabled' value before adjust happened
    # node.original_data are fmf data _before_ adjust was processed
    node = test.node
    enabled_not_set = True
    while enabled_not_set and node is not None:
        try:
            if node.original_data['enabled']:
                return True
            enabled_not_set = False
        except KeyError:
            pass
        # Not set in this node, check parent
        node = node.parent

    # Default value (True) of 'enabled' was used
    if enabled_not_set:
        return True

    # Some rule in adjust enables the test
    try:
        adjust_rules = test.node.original_data['adjust']
        # TODO: Should not be necessary once we normalize data
        if isinstance(adjust_rules, dict):
            adjust_rules = [adjust_rules]
        for rule in adjust_rules:
            try:
                if rule['enabled']:
                    return True
            except KeyError:
                pass
    except KeyError:
        pass
    # At this point nothing enables the test
    return False


def enabled_for_environment(test: 'tmt.base.Test', tcms_notes: str) -> bool:
    """ Check whether test is enabled for specified environment """
    field = StructuredField(tcms_notes)
    context_dict = {}
    try:
        for line in cast(str, field.get('environment')).split('\n'):
            try:
                dimension, values = line.split('=', maxsplit=2)
                context_dict[dimension.strip()] = [
                    value.strip() for value in re.split(",|and", values)]
            except ValueError:
                pass
    except tmt.utils.StructuredFieldError:
        pass

    if not context_dict:
        return True

    try:
        context = fmf.context.Context(**context_dict)
        test_node = test.node.copy()
        test_node.adjust(context, case_sensitive=False)
        return tmt.Test(node=test_node, logger=test._logger).enabled
    except BaseException as exception:
        log.debug(f"Failed to process adjust: {exception}")
        return True


def return_markdown_file() -> Optional[Path]:
    """ Return path to the markdown file """
    files = '\n'.join(os.listdir())
    reg_exp = r'.+\.md$'
    md_files = re.findall(reg_exp, files, re.MULTILINE)
    fail_message = ("in the current working directory.\n"
                    "Manual steps couldn't be exported")
    if len(md_files) == 1:
        return Path.cwd() / str(md_files[0])
    if not md_files:
        echo(style(f'Markdown file doesn\'t exist {fail_message}',
                   fg='yellow'))
        return None

    echo(style(f'{len(md_files)} Markdown files found {fail_message}',
               fg='yellow'))
    return None


def get_category(path: Path) -> str:
    """ Get category from Makefile """
    category = DEFAULT_NITRATE_CATEGORY
    try:
        category_search = re.search(
            r'echo\s+"Type:\s*(.*)"',
            (path / 'Makefile').read_text(encoding='utf-8'),
            re.MULTILINE)
        if category_search:
            category = category_search.group(1)
    # Default to 'Sanity' if Makefile or Type not found
    except (OSError, AttributeError):
        pass
    return category


def create_nitrate_case(summary: str, category: str) -> NitrateTestCase:
    """ Create new nitrate case """
    # Create the new test case
    assert nitrate
    category = nitrate.Category(name=category, product=DEFAULT_PRODUCT)
    testcase: NitrateTestCase = nitrate.TestCase(summary=summary, category=category)
    echo(style(f"Test case '{testcase.identifier}' created.", fg='blue'))
    return testcase


def add_to_nitrate_runs(
        nitrate_case: NitrateTestCase,
        general_plan: NitrateTestPlan,
        test: 'tmt.Test',
        dry_mode: bool) -> None:
    """
    Add nitrate test case to all active runs under given general plan

    Go down plan tree from general plan, add case and case run to
    all open runs. Try to apply adjust.
    """
    assert nitrate
    for child_plan in nitrate.TestPlan.search(parent=general_plan.id):
        for testrun in child_plan.testruns:
            if testrun.status == nitrate.RunStatus("FINISHED"):
                continue
            if not enabled_for_environment(test, tcms_notes=testrun.notes):
                continue
            # nitrate_case is None when --dry and --create are used together
            if not nitrate_case or child_plan not in nitrate_case.testplans:
                echo(style(f"Link to plan '{child_plan}'.", fg='magenta'))
                if not dry_mode:
                    nitrate_case.testplans.add(child_plan)
            if not nitrate_case or nitrate_case not in [
                    caserun.testcase for caserun in testrun]:
                echo(style(f"Link to run '{testrun}'.", fg='magenta'))
                if not dry_mode:
                    nitrate.CaseRun(testcase=nitrate_case, testrun=testrun)


def prepare_extra_summary(test: 'tmt.Test', append_summary: bool) -> str:
    """ extra-summary for export --create test """
    assert test.fmf_id.url is not None  # narrow type

    parsed_url = urllib.parse.urlparse(test.fmf_id.url)
    remote_dirname = re.sub('.git$', '', Path(parsed_url.path).name)
    if not remote_dirname:
        raise ConvertError("Unable to find git remote url.")
    generated = f"{remote_dirname} {test.name}"
    if test.summary and append_summary:
        generated += f" - {test.summary}"
    # FIXME: cast() - no issue, type-less "dispatcher" method
    return cast(str, test.node.get('extra-summary', generated))


# avoid multiple searching for general plans (it is expensive)
@cache
def find_general_plan(component: str) -> NitrateTestPlan:
    """ Return single General Test Plan or raise an error """
    assert nitrate
    # At first find by linked components
    found: list[NitrateTestPlan] = nitrate.TestPlan.search(
        type__name="General",
        is_active=True,
        component__name=f"{component}")
    # Attempt to find by name if no test plan found
    if not found:
        found = nitrate.TestPlan.search(
            type__name="General",
            is_active=True,
            name=f"{component} / General")
    # No general -> raise error
    if not found:
        raise nitrate.NitrateError(
            f"No general test plan found for '{component}'.")
    # Multiple general plans are fishy -> raise error
    if len(found) != 1:
        nitrate.NitrateError(
            "Multiple general test plans found for '{component}' component.")
    # Finally return the one and only General plan
    return found[0]


def export_to_nitrate(test: 'tmt.Test') -> None:
    """ Export fmf metadata to nitrate test cases """
    import tmt.base
    import_nitrate()
    assert nitrate
    assert gssapi

    # Check command line options
    create = test.opt('create')
    general = test.opt('general')
    link_runs = test.opt('link_runs')
    duplicate = test.opt('duplicate')
    link_bugzilla = test.opt('bugzilla')
    ignore_git_validation = test.opt('ignore_git_validation')
    dry_mode = test.is_dry_run
    append_summary = test.opt('append-summary')

    if link_runs:
        general = True

    # Check git is already correct
    valid, error_msg = tmt.utils.git.validate_git_status(test)
    if not valid:
        if ignore_git_validation:
            echo(style(f"Exporting regardless '{error_msg}'.", fg='red'))
        else:
            raise ConvertError(
                f"Can't export due '{error_msg}'.\n"
                "Use --ignore-git-validation on your own risk to export regardless.")

    # Check nitrate test case
    try:
        nitrate_id = test.node.get('extra-nitrate')[3:]
        nitrate_case: NitrateTestCase = nitrate.TestCase(int(nitrate_id))
        nitrate_case.summary  # noqa: B018 - Make sure we connect to the server now
        echo(style(f"Test case '{nitrate_case.identifier}' found.", fg='blue'))
    except TypeError:
        # Create a new nitrate test case
        if create:
            nitrate_case = None
            # Check for existing Nitrate tests with the same fmf id
            if not duplicate:
                testcases = _nitrate_find_fmf_testcases(test)
                with suppress(StopIteration):
                    nitrate_case = next(testcases)
            if not nitrate_case:
                # Summary for TCMS case
                extra_summary = prepare_extra_summary(test, append_summary)
                assert test.path is not None  # narrow type
                category = get_category(test.node.root / test.path.unrooted())
                if not dry_mode:
                    nitrate_case = create_nitrate_case(extra_summary, category)
                else:
                    echo(style(
                        f"Test case '{extra_summary}' created.", fg='blue'))
                test._metadata['extra-summary'] = extra_summary
            # Either newly created or duplicate with missing extra-nitrate
            if nitrate_case:
                echo(style("Append the nitrate test case id.", fg='green'))
                if not dry_mode:
                    with test.node as data:
                        data["extra-nitrate"] = nitrate_case.identifier
        else:
            raise ConvertError(f"Nitrate test case id not found for {test}"
                               " (You can use --create option to enforce"
                               " creating testcases)")
    except (nitrate.NitrateError, gssapi.raw.misc.GSSError) as error:
        raise ConvertError(error)

    # Check if URL is accessible, to be able to reach from nitrate
    tmt.utils.git.check_git_url(test.fmf_id.url, test._logger)

    # Summary
    try:
        summary = (test._metadata.get('extra-summary')
                   or test._metadata.get('extra-task')
                   or prepare_extra_summary(test, append_summary))
    except ConvertError:
        summary = test.name
    if not dry_mode:
        nitrate_case.summary = summary
    echo(style('summary: ', fg='green') + summary)

    # Script
    if test.node.get('extra-task'):
        if not dry_mode:
            nitrate_case.script = test.node.get('extra-task')
        echo(style('script: ', fg='green') + test.node.get('extra-task'))

    # Components and General plan
    # First remove any components that are already there
    if not dry_mode:
        nitrate_case.components.clear()
    # Only these general plans should stay
    expected_general_plans = set()
    # Then add fmf ones
    if test.component:
        echo(style('components: ', fg='green') + ' '.join(test.component))
        for component in test.component:
            try:
                nitrate_component = nitrate.Component(
                    name=component, product=DEFAULT_PRODUCT.id)
                if not dry_mode:
                    nitrate_case.components.add(nitrate_component)
            except nitrate.xmlrpc_driver.NitrateError as error:
                log.debug(error)
                echo(style(
                    f"Failed to add component '{component}'.", fg='red'))
            if general:
                try:
                    general_plan = find_general_plan(component)
                    expected_general_plans.add(general_plan)
                    echo(style(
                        f"Linked to general plan '{general_plan}'.",
                        fg='magenta'))
                    if not dry_mode:
                        nitrate_case.testplans.add(general_plan)
                    if link_runs:
                        add_to_nitrate_runs(
                            nitrate_case, general_plan, test, dry_mode)
                except nitrate.NitrateError as error:
                    log.debug(error)
                    echo(style(
                        f"Failed to find general test plan for '{component}'.",
                        fg='red'))
    # Remove unexpected general plans
    if general and nitrate_case:
        # Remove also all general plans linked to testcase
        for nitrate_plan in list(nitrate_case.testplans):
            if (nitrate_plan.type.name == "General"
                    and nitrate_plan not in expected_general_plans):
                echo(style(
                    f"Removed general plan '{nitrate_plan}'.", fg='red'))
                if not dry_mode:
                    nitrate_case.testplans.remove(nitrate_plan)

    # Tags
    # Convert 'tier' attribute into a Tier tag
    if test.tier is not None:
        test.tag.append(f"Tier{test.tier}")
    # Add special fmf-export tag
    test.tag.append('fmf-export')
    if not dry_mode:
        nitrate_case.tags.clear()
        nitrate_case.tags.add([nitrate.Tag(tag) for tag in test.tag])
    echo(style('tags: ', fg='green') + ' '.join(set(test.tag)))

    # Default tester
    if test.contact:
        try:
            # Need to pick one value, so picking the first contact
            email_address = email.utils.parseaddr(test.contact[0])[1]
            nitrate_user = nitrate.User(email_address)
            nitrate_user._fetch()  # To check that user exists
            if not dry_mode:
                nitrate_case.tester = nitrate_user
            echo(style('default tester: ', fg='green') + email_address)
        except nitrate.NitrateError as error:
            log.debug(error)
            raise ConvertError(f"Nitrate issue: {error}")

    # Duration
    if not dry_mode:
        nitrate_case.time = test.duration
    echo(style('estimated time: ', fg='green') + test.duration)

    # Manual
    if not dry_mode:
        nitrate_case.automated = not test.manual
    echo(style('automated: ', fg='green') + ['auto', 'manual'][test.manual])

    # Status
    current_status = nitrate_case.status if nitrate_case else nitrate.CaseStatus('CONFIRMED')
    # Enable enabled tests
    if enabled_somewhere(test):
        if not dry_mode:
            nitrate_case.status = nitrate.CaseStatus('CONFIRMED')
        echo(style('status: ', fg='green') + 'CONFIRMED')
    # Disable disabled tests which are CONFIRMED
    elif current_status == nitrate.CaseStatus('CONFIRMED'):
        if not dry_mode:
            nitrate_case.status = nitrate.CaseStatus('DISABLED')
        echo(style('status: ', fg='green') + 'DISABLED')
    # Keep disabled tests in their states
    else:
        echo(style('status: ', fg='green') + str(current_status))

    # Environment
    if test.environment:
        environment = ' '.join(tmt.utils.shell_variables(test.environment))
        if not dry_mode:
            nitrate_case.arguments = environment
        echo(style('arguments: ', fg='green') + environment)
    else:
        # FIXME unable clear to set empty arguments
        # (possibly error in xmlrpc, BZ#1805687)
        if not dry_mode:
            nitrate_case.arguments = ' '
        echo(style('arguments: ', fg='green') + "' '")

    # Structured Field
    struct_field = StructuredField(
        nitrate_case.notes if nitrate_case else '')
    echo(style('Structured Field: ', fg='green'))

    # Mapping of structured field sections to fmf case attributes
    section_to_attr = {
        'description': test.summary,
        'purpose-file': test.description,
        'hardware': test.node.get('extra-hardware'),
        'pepa': test.node.get('extra-pepa'),
        }
    for section, attribute in section_to_attr.items():
        if attribute is None:
            with suppress(tmt.utils.StructuredFieldError):
                struct_field.remove(section)
        else:
            struct_field.set(section, attribute)
            echo(style(section + ': ', fg='green') + attribute.strip())

    # fmf identifier
    fmf_id = tmt.utils.dict_to_yaml(test.fmf_id.to_minimal_spec())
    struct_field.set('fmf', fmf_id)
    echo(style('fmf id:\n', fg='green') + fmf_id.strip())

    # Warning
    if WARNING not in struct_field.header():
        struct_field.header(WARNING + struct_field.header())
        echo(style(
            'Add migration warning to the test case notes.', fg='green'))

    # ID
    uuid = tmt.identifier.add_uuid_if_not_defined(test.node, dry_mode, test._logger)
    if not uuid:
        uuid = test.node.get(tmt.identifier.ID_KEY)
    struct_field.set(tmt.identifier.ID_KEY, uuid)
    echo(style(f"Append the ID {uuid}.", fg='green'))

    # Saving case.notes with edited StructField
    if not dry_mode:
        nitrate_case.notes = struct_field.save()

    # Export manual test instructions from *.md file to nitrate as html
    md_path = return_markdown_file()
    if md_path and md_path.exists():
        step, expect, setup, cleanup = convert_manual_to_nitrate(md_path)
        if not dry_mode:
            nitrate.User()._server.TestCase.store_text(
                nitrate_case.id, step, expect, setup, cleanup)
        echo(style("manual steps:", fg='green') + f" found in {md_path}")

    # List of bugs test verifies
    verifies_bug_ids = []
    if test.link:
        for link in test.link.get('verifies'):
            if isinstance(link.target, tmt.base.FmfId):
                log.debug(f"Will not look for bugzila URL in fmf id '{link.target}'.")
                continue

            try:
                bug_id_search = re.search(tmt.export.RE_BUGZILLA_URL, link.target)
                if not bug_id_search:
                    log.debug(f"Did not find bugzila URL in '{link.target}'.")
                    continue
                bug_id = int(bug_id_search.group(1))
                verifies_bug_ids.append(bug_id)
            except Exception as err:
                log.debug(err)

    # Add bugs to the Nitrate case
    if verifies_bug_ids:
        echo(style('Verifies bugs: ', fg='green') +
             ', '.join([f"BZ#{b}" for b in verifies_bug_ids]))
    for bug_id in verifies_bug_ids:
        if not dry_mode:
            nitrate_case.bugs.add(nitrate.Bug(bug=int(bug_id)))

    # Update nitrate test case
    if not dry_mode:
        nitrate_case.update()
        echo(style(f"Test case '{nitrate_case.identifier}' successfully exported to nitrate.",
                   fg='magenta'))

    # Optionally link Bugzilla to Nitrate case
    if link_bugzilla and verifies_bug_ids and not dry_mode:
        tmt.export.bz_set_coverage(verifies_bug_ids, nitrate_case.id, NITRATE_TRACKER_ID)


@tmt.base.Test.provides_export('nitrate')
class NitrateExporter(tmt.export.ExportPlugin):
    @classmethod
    def export_test_collection(cls,
                               tests: list[tmt.base.Test],
                               keys: Optional[list[str]] = None,
                               **kwargs: Any) -> str:
        for test in tests:
            export_to_nitrate(test)

        return ''
