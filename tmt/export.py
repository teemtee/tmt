# coding: utf-8

""" Export metadata into nitrate """


import email
import os
import re
from functools import lru_cache

import fmf
from click import echo, style

import tmt.utils
from tmt.utils import ConvertError, markdown_to_html

log = fmf.utils.Logging('tmt').logger

WARNING = """
Test case has been migrated to git. Any changes made here might be overwritten.
See: https://tmt.readthedocs.io/en/latest/questions.html#nitrate-migration
""".lstrip()


def import_nitrate():
    """ Conditionally import the nitrate module """
    # Need to import nitrate only when really needed. Otherwise we get
    # traceback when nitrate not installed or config file not available.
    # And we want to keep the core tmt package with minimal dependencies.
    try:
        global nitrate, DEFAULT_PRODUCT, gssapi
        import gssapi
        import nitrate
        DEFAULT_PRODUCT = nitrate.Product(name='RHEL Tests')
        return nitrate
    except ImportError:
        raise ConvertError(
            "Install tmt-test-convert to export tests to nitrate.")
    except nitrate.NitrateError as error:
        raise ConvertError(error)


def _nitrate_find_fmf_testcases(test):
    """
    Find all Nitrate test cases with the same fmf identifier

    All component general plans are explored for possible duplicates.
    """
    for component in test.component:
        try:
            for testcase in find_general_plan(component).testcases:
                struct_field = tmt.utils.StructuredField(testcase.notes)
                try:
                    fmf_id = tmt.utils.yaml_to_dict(struct_field.get('fmf'))
                    if fmf_id == test.fmf_id:
                        echo(style(
                            f"Existing test case '{testcase.identifier}' "
                            f"found for given fmf id.", fg='magenta'))
                        yield testcase
                except tmt.utils.StructuredFieldError:
                    pass
        except nitrate.NitrateError:
            pass


def convert_manual_to_nitrate(test_md):
    """
    Convert Markdown document to html sections.

    These sections can be exported to nitrate.
    Expects: Markdown document as a file.
    Returns: tuple of (step, expect, setup, cleanup) sections
    as html strings.
    """

    sections_headings = {
        '<h1>Setup</h1>': [],
        '<h1>Test</h1>': [],
        '<h1>Test .*</h1>': [],
        '<h2>Step</h2>': [],
        '<h2>Test Step</h2>': [],
        '<h2>Expect</h2>': [],
        '<h2>Result</h2>': [],
        '<h2>Expected Result</h2>': [],
        '<h1>Cleanup</h1>': []}

    html = markdown_to_html(test_md)
    html_splitlines = html.splitlines()

    for key in sections_headings.keys():
        result = []
        i = 0
        while html_splitlines:
            try:
                if re.search("^" + key + "$", html_splitlines[i]):
                    html_content = str()
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

    def concatenate_headings_content(headings):
        content = list()
        for v in headings:
            content += sections_headings[v]
        return content

    def enumerate_content(content):
        content.sort()
        for c in range(len(content)):
            content[c][1] = f"<p>Step {c + 1}.</p>" + content[c][1]
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

    def check_section_exists(text):
        try:
            return sections_headings[text][0][1]
        except (IndexError, KeyError):
            return ''

    setup = check_section_exists('<h1>Setup</h1>')
    cleanup = check_section_exists('<h1>Cleanup</h1>')

    return step, expect, setup, cleanup


def export_to_nitrate(test):
    """ Export fmf metadata to nitrate test cases """
    import_nitrate()
    new_test_created = False

    # Check command line options
    create = test.opt('create')
    general = test.opt('general')
    duplicate = test.opt('duplicate')

    # Check nitrate test case
    try:
        nitrate_id = test.node.get('extra-nitrate')[3:]
        nitrate_case = nitrate.TestCase(int(nitrate_id))
        nitrate_case.summary  # Make sure we connect to the server now
        echo(style(f"Test case '{nitrate_case.identifier}' found.", fg='blue'))
    except TypeError:
        # Create a new nitrate test case
        if create:
            nitrate_case = None
            # Check for existing Nitrate tests with the same fmf id
            if not duplicate:
                testcases = _nitrate_find_fmf_testcases(test)
                try:
                    # Select the first found testcase if any
                    nitrate_case = next(testcases)
                except StopIteration:
                    pass
            if not nitrate_case:
                nitrate_case = create_nitrate_case(test)
            new_test_created = True
            # Newly created tmt tests have special format summary
            test._metadata['extra-summary'] = nitrate_case.summary
        else:
            raise ConvertError(f"Nitrate test case id not found for {test}"
                               " (You can use --create option to enforce"
                               " creating testcases)")
    except (nitrate.NitrateError, gssapi.raw.misc.GSSError) as error:
        raise ConvertError(error)

    # Summary
    summary = (test._metadata.get('extra-summary')
               or test._metadata.get('extra-task')
               or test.summary
               or test.name)
    if summary:
        nitrate_case.summary = summary
        echo(style('summary: ', fg='green') + summary)
    else:
        raise ConvertError("Nitrate case summary could not be determined.")

    # Script
    if test.node.get('extra-task'):
        nitrate_case.script = test.node.get('extra-task')
        echo(style('script: ', fg='green') + test.node.get('extra-task'))

    # Components
    # First remove any components that are already there
    nitrate_case.components.clear()
    if general:
        # Remove also all general plans linked to testcase
        for nitrate_plan in [plan for plan in nitrate_case.testplans]:
            if nitrate_plan.type.name == "General":
                nitrate_case.testplans.remove(nitrate_plan)
    # Then add fmf ones
    if test.component:
        echo(style('components: ', fg='green') + ' '.join(test.component))
        for component in test.component:
            try:
                nitrate_case.components.add(nitrate.Component(
                    name=component, product=DEFAULT_PRODUCT.id))
            except nitrate.xmlrpc_driver.NitrateError as error:
                log.debug(error)
                echo(style(
                    f"Failed to add component '{component}'.", fg='red'))
            if general:
                try:
                    general_plan = find_general_plan(component)
                    nitrate_case.testplans.add(general_plan)
                except nitrate.NitrateError as error:
                    log.debug(error)
                    echo(style(
                        f"Failed to link general test plan for '{component}'.",
                        fg='red'))

    # Tags
    nitrate_case.tags.clear()
    # Convert 'tier' attribute into a Tier tag
    if test.tier is not None:
        test.tag.append(f"Tier{test.tier}")
    # Add special fmf-export tag
    test.tag.append('fmf-export')
    nitrate_case.tags.add([nitrate.Tag(tag) for tag in test.tag])
    echo(style('tags: ', fg='green') + ' '.join(set(test.tag)))

    # Default tester
    if test.contact:
        # Need to pick one value, so picking the first contact
        email_address = email.utils.parseaddr(test.contact[0])[1]
        # TODO handle nitrate user not existing and other possible exceptions
        nitrate_case.tester = nitrate.User(email_address)
        echo(style('default tester: ', fg='green') + email_address)

    # Duration
    nitrate_case.time = test.duration
    echo(style('estimated time: ', fg='green') + test.duration)

    # Manual
    nitrate_case.automated = not test.manual
    echo(style('automated: ', fg='green') + ['auto', 'manual'][test.manual])

    # Status
    current_status = nitrate_case.status
    # Enable enabled tests
    if test.enabled:
        nitrate_case.status = nitrate.CaseStatus('CONFIRMED')
        echo(style('status: ', fg='green') + 'CONFIRMED')
    # Disable disabled tests which are CONFIRMED
    elif current_status == nitrate.CaseStatus('CONFIRMED'):
        nitrate_case.status = nitrate.CaseStatus('DISABLED')
        echo(style('status: ', fg='green') + 'DISABLED')
    # Keep disabled tests in their states
    else:
        echo(style('status: ', fg='green') + str(current_status))

    # Environment
    if test.environment:
        environment = ' '.join(tmt.utils.shell_variables(test.environment))
        nitrate_case.arguments = environment
        echo(style('arguments: ', fg='green') + environment)
    else:
        # FIXME unable clear to set empty arguments
        # (possibly error in xmlrpc, BZ#1805687)
        nitrate_case.arguments = ' '
        echo(style('arguments: ', fg='green') + "' '")

    # Structured Field
    struct_field = tmt.utils.StructuredField(nitrate_case.notes)
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
            try:
                struct_field.remove(section)
            except tmt.utils.StructuredFieldError:
                pass
        else:
            struct_field.set(section, attribute)
            echo(style(section + ': ', fg='green') + attribute.strip())

    # fmf identifer
    fmf_id = tmt.utils.dict_to_yaml(test.fmf_id)
    struct_field.set('fmf', fmf_id)
    echo(style('fmf id:\n', fg='green') + fmf_id.strip())

    # Warning
    if WARNING not in struct_field.header():
        struct_field.header(WARNING + struct_field.header())
        echo(style(
            'Add migration warning to the test case notes.', fg='green'))

    # Saving case.notes with edited StructField
    nitrate_case.notes = struct_field.save()

    # Export manual test instructions from test.md to nitrate as html
    md_path = os.getcwd() + '/test.md'
    if os.path.exists(md_path):
        step, expect, setup, cleanup = convert_manual_to_nitrate(md_path)
        nitrate.User()._server.TestCase.store_text(
            nitrate_case.id, step, expect, setup, cleanup)
        echo(style(f"manual steps:", fg='green') + f" found in {md_path}")

    # Append id of newly created nitrate case to its file
    if new_test_created:
        echo(style(f"Append the nitrate test case id.", fg='green'))
        try:
            with test.node as data:
                data["extra-nitrate"] = nitrate_case.identifier
        except AttributeError:
            # FIXME: Remove this deprecated code after fmf support
            # for storing modified data is released long enough
            file_path = test.node.sources[-1]
            try:
                with open(file_path, encoding='utf-8', mode='a+') as file:
                    file.write(f"extra-nitrate: {nitrate_case.identifier}\n")
            except IOError:
                raise ConvertError("Unable to open '{0}'.".format(file_path))

    # Update nitrate test case
    nitrate_case.update()
    echo(style("Test case '{0}' successfully exported to nitrate.".format(
        nitrate_case.identifier), fg='magenta'))


def create_nitrate_case(test):
    """ Create new nitrate case """
    import_nitrate()

    # Get category from Makefile
    try:
        with open('Makefile', encoding='utf-8') as makefile_file:
            makefile = makefile_file.read()
        category = re.search(
            r'echo\s+"Type:\s*(.*)"', makefile, re.M).group(1)
    # Default to 'Sanity' if Makefile or Type not found
    except (IOError, AttributeError):
        category = 'Sanity'

    # Create the new test case
    remote_dirname = re.sub('.git$', '', os.path.basename(test.fmf_id['url']))
    if not remote_dirname:
        raise ConvertError("Unable to find git remote url.")
    summary = test.node.get('extra-summary', (remote_dirname or "")
                            + (test.name or "") + ' - ' + (test.summary or ""))
    category = nitrate.Category(name=category, product=DEFAULT_PRODUCT)
    testcase = nitrate.TestCase(summary=summary, category=category)
    echo(style(f"Test case '{testcase.identifier}' created.", fg='blue'))
    return testcase


# avoid multiple searching for general plans (it is expensive)
@lru_cache(maxsize=None)
def find_general_plan(component):
    """ Return single General Test Plan or raise an error """
    # At first find by linked components
    found = nitrate.TestPlan.search(
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
