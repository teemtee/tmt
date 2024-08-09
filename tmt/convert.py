""" Convert metadata into the new format """

import copy
import os
import re
import shlex
import subprocess
from contextlib import suppress
from typing import TYPE_CHECKING, Any, Optional, Union
from uuid import UUID, uuid4

import fmf.utils
from click import echo, style

import tmt.base
import tmt.export
import tmt.identifier
import tmt.log
import tmt.utils
from tmt.utils import ConvertError, GeneralError, Path, format_value

log = fmf.utils.Logging('tmt').logger

# It is not possible to use TypedDict here, because all keys are unknown
NitrateDataType = dict[str, Any]

if TYPE_CHECKING:
    from nitrate import TestCase


# Test case relevancy regular expressions
RELEVANCY_LEGACY_HEADER = r"relevancy:\s*$(.*)"
RELEVANCY_COMMENT = r"^([^#]*?)\s*#\s*(.+)$"
RELEVANCY_RULE = r"^([^:]+)\s*:\s*(.+)$"
RELEVANCY_EXPRESSION = (
    r"^\s*(.*?)\s*(!?contains|!?defined|[=<>!]+)\s*(.*?)\s*$")
GENERAL_PLAN = r"(\S+?)\s*/\s*General"

# Bug url prefixes
BUGZILLA_URL = 'https://bugzilla.redhat.com/show_bug.cgi?id='
JIRA_URL = 'https://issues.redhat.com/browse/'

# Bug system constants
SYSTEM_BUGZILLA = 1
SYSTEM_JIRA = 2
SYSTEM_OTHER = 42


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#  Convert
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

def read_manual(
        plan_id: int,
        case_id: int,
        disabled: bool,
        with_script: bool,
        logger: tmt.log.Logger) -> None:
    """ Reads metadata of manual test cases from Nitrate """
    import tmt.export.nitrate
    nitrate = tmt.export.nitrate.import_nitrate()
    # Turns off nitrate caching
    nitrate.set_cache_level(0)

    old_cwd = Path.cwd()

    try:
        tree = fmf.Tree(str(old_cwd))
    except fmf.utils.RootError:
        raise ConvertError("Initialize metadata tree using 'tmt init'.")

    try:
        if plan_id:
            all_cases = nitrate.TestPlan(plan_id).testcases
            case_ids = [case.id for case in all_cases if not case.automated]
        else:
            case_ids = [case_id]
    except ValueError:
        raise ConvertError('Test plan/case identifier must be an integer.')

    # Create directory to store manual tests in
    new_cwd = Path(tree.root) / 'Manual'
    new_cwd.mkdir(exist_ok=True)
    os.chdir(new_cwd)

    for cid in case_ids:
        testcase = nitrate.TestCase(cid)
        if testcase.status.name != 'CONFIRMED' and not disabled:
            log.debug(f'{testcase.identifier} skipped (testcase is not CONFIRMED).')
            continue
        if testcase.script is not None and not with_script:
            log.debug(f'{testcase.identifier} skipped (script is not empty).')
            continue

        # Filename sanitization
        dir_name = testcase.summary.replace(' ', '_')
        dir_name = dir_name.replace('/', '_')
        directory = Path(dir_name)
        directory.mkdir(exist_ok=True)

        os.chdir(directory)
        echo(f"Importing the '{directory}' test case.")

        # Test case data
        md_content = read_manual_data(testcase)

        # Test case metadata
        data = read_nitrate_case(testcase=testcase, logger=logger)
        data['manual'] = True
        data['test'] = 'test.md'

        write_markdown(Path.cwd() / 'test.md', md_content)
        write(Path.cwd() / 'main.fmf', data)
        os.chdir(new_cwd)

    os.chdir(old_cwd)


def read_manual_data(testcase: 'TestCase') -> dict[str, str]:
    """ Read test data from manual fields """
    md_content = {}
    md_content['setup'] = html_to_markdown(testcase.setup)
    md_content['action'] = html_to_markdown(testcase.action)
    md_content['expected'] = html_to_markdown(testcase.effect)
    md_content['cleanup'] = html_to_markdown(testcase.breakdown)
    return md_content


def html_to_markdown(html: str) -> str:
    """ Convert html to markdown """
    try:
        import html2text
        md_handler = html2text.HTML2Text()
    except ImportError:
        raise ConvertError("Install tmt+test-convert to import tests.")

    if html is None:
        markdown: str = ""
    else:
        markdown = md_handler.handle(html).strip()
    return markdown


def write_markdown(path: Path, content: dict[str, str]) -> None:
    """ Write gathered metadata in the markdown format """
    to_print = ""
    if content['setup']:
        to_print += "# Setup\n" + content['setup'] + '\n\n'
    if content['action'] or content['expected']:
        to_print += "# Test\n\n"
        if content['action']:
            to_print += "## Step\n" + content['action'] + '\n\n'
        if content['expected']:
            to_print += "## Expect\n" + content['expected'] + '\n\n'
    if content['cleanup']:
        to_print += "# Cleanup\n" + content['cleanup'] + '\n'

    try:
        with open(path, 'w', encoding='utf-8') as md_file:
            md_file.write(to_print)
            echo(style(
                f"Test case successfully stored into '{path}'.", fg='magenta'))
    except OSError:
        raise ConvertError(f"Unable to write '{path}'.")


def add_link(target: str, data: NitrateDataType,
             system: int = SYSTEM_BUGZILLA, type_: str = 'relates') -> None:
    """ Add relevant link into data under the 'link' key """
    new_link = {}
    if system == SYSTEM_BUGZILLA:
        new_link[type_] = f"{BUGZILLA_URL}{target}"
    elif system == SYSTEM_JIRA:
        new_link[type_] = f"{JIRA_URL}{target}"
    elif system == SYSTEM_OTHER:
        new_link[type_] = target

    try:
        # Make sure there are no duplicates
        if new_link in data['link']:
            return
        data['link'].append(new_link)
    except KeyError:
        data['link'] = [new_link]
    echo(style(f'{type_}: ', fg='green') + new_link[type_])


def read_datafile(
        path: Path,
        filename: str,
        datafile: str,
        types: list[str],
        testinfo: Optional[str] = None
        ) -> tuple[str, NitrateDataType]:
    """
    Read data values from supplied Makefile or metadata file.
    Returns task name and a dictionary of the collected values.
    """

    data: NitrateDataType = {}
    makefile_regex_test = r'^run:.*\n\t(.*)$'
    if filename == 'Makefile':
        regex_task = r'Name:[ \t]*(.*)$'
        regex_summary = r'^Description:[ \t]*(.*)$'
        regex_test = makefile_regex_test
        regex_contact = r'^Owner:[ \t]*(.*)$'
        regex_duration = r'^TestTime:[ \t]*(\d+.*)$'
        regex_recommend = r'^Requires:[ \t]*(.*)$'
        regex_require = r'^RhtsRequires:[ \t]*(.*)$'
        rec_separator = None
    else:
        regex_task = r'name=[ \t]*(.*)$'
        regex_summary = r'description=[ \t]*(.*)$'
        regex_test = r'entry_point=[ \t]*(.*)$'
        regex_contact = r'owner=[ \t]*(.*)$'
        regex_duration = r'max_time=[ \t]*(\d+.*)$'
        regex_require = r'dependencies=[ \t]*(.*)$'
        regex_recommend = r'softDependencies=[ \t]*(.*)$'
        rec_separator = ';'

    # Join those lines having '\\\n' for further matching test script
    newline_stub = '_XXX_NEWLINE_0x734'
    datafile_test = datafile
    if '\\\n' in datafile:
        datafile_test = re.sub(r'\\\n', newline_stub, datafile)

    if testinfo is None:
        testinfo = datafile

    # Beaker task name
    search_result = re.search(regex_task, testinfo, re.MULTILINE)
    if search_result is None:
        raise ConvertError("Unable to parse 'Name' from testinfo.desc.")
    beaker_task = search_result.group(1).strip()
    echo(style('task: ', fg='green') + beaker_task)
    data['extra-task'] = beaker_task
    data['extra-summary'] = beaker_task

    # Summary
    search_result = re.search(regex_summary, testinfo, re.MULTILINE)
    if search_result is not None:
        data['summary'] = search_result.group(1).strip()
        echo(style('summary: ', fg='green') + data['summary'])

    # Test script
    search_result = re.search(regex_test, datafile_test, re.MULTILINE)
    if search_result is None:
        if filename == 'metadata':
            # entry_point property is optional. When absent 'make run' is used.
            data['test'] = 'make run'
        else:
            raise ConvertError("Makefile is missing the 'run' target.")
    else:
        data['test'] = search_result.group(1).strip()
        # Restore '\\\n' as it was replaced before matching
        if '\\\n' in datafile:
            data['test'] = re.sub(newline_stub, '\\\n', data['test'])
        echo(style('test: ', fg='green') + data['test'])

    # Detect framework
    try:
        test_path: Optional[Path] = None
        if data["test"].split()[0] != 'make':
            script_paths = [s for s in shlex.split(data['test']) if s.endswith('.sh')]
            if script_paths:
                test_path = path / script_paths[0]
        else:
            # As 'make' command was specified for test, ensure Makefile present.
            makefile_path = path / 'Makefile'
            try:
                with open(makefile_path, encoding='utf-8') as makefile_file:
                    makefile = makefile_file.read()
                    search_result = \
                        re.search(makefile_regex_test, makefile, re.MULTILINE)
            except OSError:
                raise ConvertError("Makefile is missing.")
            # Retrieve the path to the test file from the Makefile
            if search_result is not None:
                test_path = path / search_result.group(1).split()[-1]
        # Read the test file and determine the framework used.
        if test_path:
            with open(test_path, encoding="utf-8") as test_file:
                if re.search("beakerlib", test_file.read(), re.MULTILINE):
                    data["framework"] = "beakerlib"
                else:
                    data["framework"] = "shell"
        else:
            data["framework"] = "shell"
        echo(style("framework: ", fg="green") + data["framework"])
    except OSError:
        raise ConvertError(f"Unable to open '{test_path}'.")

    # Contact
    search_result = re.search(regex_contact, testinfo, re.MULTILINE)
    if search_result is not None:
        data['contact'] = search_result.group(1).strip()
        echo(style('contact: ', fg='green') + data['contact'])

    if filename == 'Makefile':
        # Component
        search_result = re.search(r'^RunFor:[ \t]*(.*)$', testinfo, re.MULTILINE)
        if search_result is not None:
            data['component'] = search_result.group(1).split()
            echo(style('component: ', fg='green') +
                 ' '.join(data['component']))

    # Duration
    search_result = re.search(regex_duration, testinfo, re.MULTILINE)
    if search_result is not None:
        data['duration'] = search_result.group(1).strip()
        echo(style('duration: ', fg='green') + data['duration'])

    if filename == 'Makefile':
        # Environment
        variables = re.findall(r'^Environment:[ \t]*(.*)$', testinfo, re.MULTILINE)
        if variables:
            data['environment'] = {}
            for variable in variables:
                key, value = variable.split('=', maxsplit=1)
                data['environment'][key] = value
            echo(style('environment:', fg='green'))
            echo(format_value(data['environment']))

    def sanitize_name(name: str) -> str:
        """ Raise if package name starts with '-' (negative require) """
        if name.startswith('-'):
            # Beaker supports excluding packages but tmt does not
            # https://github.com/teemtee/tmt/issues/1165#issuecomment-1122293224
            raise ConvertError(
                "Excluding packages is not supported by tmt require/recommend. "
                "Plan can take care of such situation in Prepare step, "
                "but cannot be created automatically. "
                f"(Found '{name}' during conversion).")
        return name

    # RhtsRequires or repoRequires (optional) goes to require
    requires = re.findall(regex_require, testinfo, re.MULTILINE)
    if requires:
        data['require'] = [
            sanitize_name(require.strip()) for line in requires
            for require in line.split(rec_separator)]
        echo(style('require: ', fg='green') + ' '.join(data['require']))

    # Requires or softDependencies (optional) goes to recommend
    recommends = re.findall(regex_recommend, testinfo, re.MULTILINE)
    if recommends:
        data['recommend'] = [
            sanitize_name(recommend.strip()) for line in recommends
            for recommend in line.split(rec_separator)]
        echo(
            style('recommend: ', fg='green') + ' '.join(data['recommend']))

    if filename == 'Makefile':
        # Convert Type into tags
        search_result = re.search(r'^Type:[ \t]*(.*)$', testinfo, re.MULTILINE)
        if search_result is not None:
            makefile_type = search_result.group(1).strip()
            if 'all' in [type_.lower() for type_ in types]:
                tags = makefile_type.split()
            else:
                tags = [type_ for type_ in types
                        if type_.lower() in makefile_type.lower().split()]
            if tags:
                echo(style("tag: ", fg="green") + " ".join(tags))
                data["tag"] = tags
        # Add relevant bugs to the 'link' attribute
        for bug_line in re.findall(r'^Bug:\s*([0-9\s]+)', testinfo, re.MULTILINE):
            for bug in re.findall(r'(\d+)', bug_line):
                add_link(bug, data, SYSTEM_BUGZILLA)

    return beaker_task, data


ReadOutputType = tuple[NitrateDataType, list[NitrateDataType]]


def read(
        path: Path,
        makefile: bool,
        restraint: bool,
        nitrate: bool,
        polarion: bool,
        polarion_case_id: list[str],
        link_polarion: bool,
        purpose: bool,
        disabled: bool,
        types: list[str],
        general: bool,
        dry_run: bool,
        logger: tmt.log.Logger
        ) -> ReadOutputType:
    """
    Read old metadata from various sources

    Returns tuple (common_data, individual_data) where 'common_data' are
    metadata which belong to main.fmf and 'individual_data' contains
    data for individual testcases (if multiple nitrate testcases found).
    """

    echo(f"Checking the '{path}' directory.")

    # Make sure there is a metadata tree initialized
    try:
        tree = fmf.Tree(str(path))
    except fmf.utils.RootError:
        raise ConvertError("Initialize metadata tree using 'tmt init'.")

    # Ascertain if datafile is of type Makefile or metadata
    makefile_file = None
    restraint_file = None
    filename = None

    filenames = [f.name for f in path.iterdir() if f.is_file()]

    # Ascertain which file to use based on cmd arg.
    # If both are false and there is no Polarion import raise an assertion.
    # If both are true then default to using
    # the restraint metadata file.
    # Raise an assertion if the file is not found.
    if not makefile and not restraint and not polarion:
        raise ConvertError(
            "Please specify either a Makefile or a Restraint file or a Polarion case ID.")
    if makefile and restraint:
        if 'metadata' in filenames:
            filename = 'metadata'
            restraint_file = True
            echo(style('Restraint file ', fg='blue'), nl=False)
        elif 'Makefile' in filenames:
            filename = 'Makefile'
            makefile_file = True
            echo(style('Makefile ', fg='blue'), nl=False)
        else:
            raise ConvertError("Unable to find any metadata file.")
    elif makefile:
        if 'Makefile' not in filenames:
            raise ConvertError("Unable to find Makefile")
        filename = 'Makefile'
        makefile_file = True
        echo(style('Makefile ', fg='blue'), nl=False)
    elif restraint:
        if 'metadata' not in filenames:
            raise ConvertError("Unable to find restraint metadata file")
        filename = 'metadata'
        restraint_file = True
        echo(style('Restraint ', fg='blue'), nl=False)

    if filename is None and not polarion:
        raise GeneralError('Filename is not defined and there is no import from Polarion')
    # Open the datafile
    if restraint_file or makefile_file:
        assert filename is not None  # type check
        datafile_path = path / filename
        try:
            with open(datafile_path, encoding='utf-8') as datafile_file:
                datafile = datafile_file.read()
        except OSError:
            raise ConvertError(f"Unable to open '{datafile_path}'.")
        echo(f"found in '{datafile_path}'.")

    # If testinfo.desc exists read it to preserve content and remove it
    testinfo_path = path / 'testinfo.desc'
    if testinfo_path.is_file():
        try:
            with open(testinfo_path, encoding='utf-8') as testinfo_file:
                old_testinfo = testinfo_file.read()
            testinfo_path.unlink()
        except OSError:
            raise ConvertError(
                f"Unable to open '{testinfo_path}'.")
    else:
        old_testinfo = None

    # Make Makefile 'makeable' without extra dependencies
    # (replace targets, make include optional and remove rhts-lint)
    if makefile_file:
        datafile = datafile.replace('$(METADATA)', 'testinfo.desc')
        datafile = re.sub(
            r'^include /usr/share/rhts/lib/rhts-make.include',
            '-include /usr/share/rhts/lib/rhts-make.include',
            datafile, flags=re.MULTILINE)
        datafile = re.sub('.*rhts-lint.*', '', datafile)
        # Create testinfo.desc file with resolved variables
        try:
            subprocess.run(
                ["make", "testinfo.desc", "-C", path, "-f", "-"],
                input=datafile, check=True, encoding='utf-8',
                stdout=subprocess.DEVNULL)
        except FileNotFoundError:
            raise ConvertError(
                f"Install tmt+test-convert to convert metadata from {filename}.")
        except subprocess.CalledProcessError:
            raise ConvertError(
                "Failed to convert metadata using 'make testinfo.desc'.")

        # Read testinfo.desc
        try:
            with open(testinfo_path, encoding='utf-8') as testinfo_file:
                testinfo = testinfo_file.read()
        except OSError:
            raise ConvertError(f"Unable to open '{testinfo_path}'.")

    # restraint
    if restraint_file:
        assert filename is not None  # type check
        beaker_task, data = \
            read_datafile(path, filename, datafile, types)

    # Makefile (extract summary, test, duration and requires)
    elif makefile:
        assert filename is not None  # type check
        beaker_task, data = \
            read_datafile(path, filename, datafile, types, testinfo)

        # Warn if makefile has extra lines in run target
        def target_content_run() -> list[str]:
            """ Extract lines from the run content """
            newline_stub = '_XXX_NEWLINE_0x734'
            datafile_test = datafile
            if '\\\n' in datafile:
                datafile_test = re.sub(r'\\\n', newline_stub, datafile)
            regexp = r'^run:.*\n\t(.*)$'
            search_result = re.search(regexp, datafile_test, re.MULTILINE)
            if search_result is None:
                # Target not found in the Makefile
                return []
            target = search_result.group(1)
            if '\\\n' in datafile:
                target = re.sub(newline_stub, '\\\n', target)
                return [target]
            return [line.strip('\t') for line in target.splitlines()]

        # Warn if makefile has extra lines in build target
        def target_content_build() -> list[str]:
            """ Extract lines from the build content """
            regexp = r'^build:.*\n((?:\t[^\n]*\n?)*)'
            search_result = re.search(regexp, datafile, re.MULTILINE)
            if search_result is None:
                # Target not found in the Makefile
                return []
            target = search_result.group(1)
            return [line.strip('\t') for line in target.splitlines()]

        run_target_list = target_content_run()
        run_target_list.remove(data["test"])
        if run_target_list:
            echo(style(
                "warn: Extra lines detected in the 'run' target:",
                fg="yellow"))
            for line in run_target_list:
                echo(f"    {line}")

        build_target_list = target_content_build()
        if len(build_target_list) > 1:
            echo(style(
                "warn: Multiple lines detected in the 'build' target:",
                fg="yellow"))
            for line in build_target_list:
                echo(f"    {line}")

        # Restore the original testinfo.desc content (if existed)
        if old_testinfo:
            try:
                with open(testinfo_path, 'w', encoding='utf-8') as testinfo_file:
                    testinfo_file.write(old_testinfo)
            except OSError:
                raise ConvertError(
                    f"Unable to write '{testinfo_path}'.")
        # Remove created testinfo.desc otherwise
        else:
            testinfo_path.unlink()
    else:
        data = {}
        beaker_task = ''

    # Purpose (extract everything after the header as a description)
    if purpose:
        echo(style('Purpose ', fg='blue'), nl=False)
        purpose_path = path / 'PURPOSE'
        try:
            with open(purpose_path, encoding='utf-8') as purpose_file:
                content = purpose_file.read()
            echo(f"found in '{purpose_path}'.")
            for header in ['PURPOSE', 'Description', 'Author']:
                content = re.sub(f'^{header}.*\n', '', content)
            data['description'] = content.lstrip('\n')
            echo(style('description:', fg='green'))
            echo(data['description'].rstrip('\n'))
        except OSError:
            echo("not found.")

    # Nitrate (extract contact, environment and relevancy)
    if nitrate and beaker_task:
        common_data, individual_data = read_nitrate(
            beaker_task, data, disabled, general, dry_run, logger)
    else:
        common_data = data
        individual_data = []

    # Polarion (extract summary, assignee, id, component, tags, links)
    if polarion:
        read_polarion(
            common_data, individual_data, polarion_case_id, link_polarion, filenames, dry_run)

    # Remove keys which are inherited from parent
    parent_path = path.parent
    parent_name = str(Path('/') / parent_path.relative_to(tree.root))
    parent = tree.find(parent_name)
    if parent:
        for test in [common_data, *individual_data]:
            for key in list(test):
                if parent.get(key) == test[key]:
                    test.pop(key)

    log.debug(f'Common metadata:\n{format_value(common_data)}')
    log.debug(f'Individual metadata:\n{format_value(individual_data)}')
    return common_data, individual_data


def filter_common_data(
        common_data: NitrateDataType,
        individual_data: list[NitrateDataType]) -> None:
    """ Filter common data out from individual data """
    common_candidates = copy.copy(individual_data[0])
    histogram = {}
    for key in individual_data[0]:
        histogram[key] = 1
    if len(individual_data) > 1:
        for testcase in individual_data[1:]:
            for key, value in testcase.items():
                if key in common_candidates and value != common_candidates[key]:
                    common_candidates.pop(key)
                if key in histogram:
                    histogram[key] += 1

    for key in histogram:
        if key in common_candidates and histogram[key] < len(individual_data):
            common_candidates.pop(key)

    # Add common data to main.fmf
    for key, value in common_candidates.items():
        common_data[key] = value

    # If there is only single testcase found there is no need to continue
    if len(individual_data) == 1:
        individual_data.pop()
    if not individual_data:
        return

    # Remove common data from individual fmfs
    for common_key in common_candidates:
        for testcase in individual_data:
            if common_key in testcase:
                testcase.pop(common_key)


def read_nitrate(
        beaker_task: str,
        common_data: NitrateDataType,
        disabled: bool,
        general: bool,
        dry_run: bool,
        logger: tmt.log.Logger
        ) -> ReadOutputType:
    """ Read old metadata from nitrate test cases """

    # Need to import nitrate only when really needed. Otherwise we get
    # traceback when nitrate is not installed or config file not available.
    try:
        import gssapi
        import nitrate
    except ImportError:
        raise ConvertError('Install tmt+test-convert to import metadata.')

    # Check test case
    echo(style('Nitrate ', fg='blue'), nl=False)
    if beaker_task is None:
        raise ConvertError('No test name detected for nitrate search')

    # Find all testcases
    try:
        if disabled:
            testcases = list(nitrate.TestCase.search(script=beaker_task))
        # Find testcases that do not have 'DISABLED' status
        else:
            testcases = list(nitrate.TestCase.search(
                script=beaker_task, case_status__in=[1, 2, 4]))
    except (nitrate.NitrateError,
            nitrate.xmlrpc_driver.NitrateXmlrpcError,
            gssapi.raw.misc.GSSError) as error:
        raise ConvertError(str(error))
    if not testcases:
        echo("No {}testcase found for '{}'.".format(
            '' if disabled else 'non-disabled ', beaker_task))
        return common_data, []
    if len(testcases) > 1:
        echo(f"Multiple test cases found for '{beaker_task}'.")

    # Process individual test cases
    individual_data = []
    md_content = {}
    for testcase in testcases:
        # Testcase data must be fetched due to
        # https://github.com/psss/python-nitrate/issues/24
        testcase._fetch()
        data = read_nitrate_case(
            testcase=testcase,
            makefile_data=common_data,
            general=general,
            logger=logger)
        individual_data.append(data)
        # Check testcase for manual data
        md_content_tmp = read_manual_data(testcase)
        if any(md_content_tmp.values()):
            md_content = md_content_tmp

    # Write md file if there is something to write
    # or try to remove if there isn't.
    md_path = Path.cwd() / 'test.md'
    if md_content:
        if dry_run:
            echo(style(f"Test case would be stored into '{md_path}'.", fg='magenta'))
        else:
            write_markdown(md_path, md_content)
    else:
        try:
            md_path.unlink()
            echo(style(f"Test case file '{md_path}' "
                       "successfully removed.", fg='magenta'))
        except FileNotFoundError:
            pass
        except OSError:
            raise ConvertError(
                f"Unable to remove '{md_path}'.")

    # Merge environment from Makefile and Nitrate
    if 'environment' in common_data:
        for case in individual_data:
            if 'environment' in case:
                case_environment = case['environment']
                case['environment'] = common_data['environment'].copy()
                case['environment'].update(case_environment)

    # Merge description from PURPOSE with header/footer from Nitrate notes
    for testcase in individual_data:
        if 'description' in common_data:
            testcase['description'] = common_data['description'] + \
                testcase['description']

    if 'description' in common_data:
        common_data.pop('description')

    filter_common_data(common_data, individual_data)
    return common_data, individual_data


def read_tier(tag: str, data: NitrateDataType) -> None:
    """
    Extract tier level from tag

    Check for the tier attribute, if there are multiple TierX tags, pick
    the one with the lowest index.
    """
    tier_match = re.match(r'^Tier ?(?P<num>\d+)$', tag, re.IGNORECASE)
    if tier_match:
        num = tier_match.group('num')
        if 'tier' in data:
            if int(num) < int(data['tier']):
                log.warning('Multiple Tier tags found, using the one with a lower index.')
                data['tier'] = num
        else:
            data['tier'] = num
        echo(style('tier: ', fg='green') + str(data['tier']))


def read_polarion(
        common_data: NitrateDataType,
        individual_data: list[NitrateDataType],
        polarion_case_id: list[str],
        link_polarion: bool,
        filenames: list[str],
        dry_run: bool) -> None:
    """ Read data from Polarion """
    if not polarion_case_id:
        read_polarion_case(common_data, None, link_polarion, dry_run)
    elif len(polarion_case_id) == 1:
        read_polarion_case(common_data, polarion_case_id[0], link_polarion, dry_run)
    else:
        if not individual_data:
            for case in polarion_case_id:
                current_data: NitrateDataType = {}
                read_polarion_case(current_data, case, link_polarion, dry_run)
                individual_data.append(current_data)
        else:
            for case in polarion_case_id:
                read_polarion_case(individual_data, case, link_polarion, dry_run)
        filter_common_data(common_data, individual_data)

    # Check test script existence and add it if not already imported by other means
    if not common_data.get('test'):
        test_file = next((file for file in filenames if file.endswith('.sh')), '')
        if test_file:
            common_data['test'] = f'./{test_file}'
            echo(style('test: ', fg='green') + common_data['test'])

    # Fix badly added id to common data for import from one Polarion case
    # while having multiple Nitrate cases
    # Also keep original file name for the common data
    if individual_data and (common_data.get(tmt.identifier.ID_KEY) or common_data.get('filename')):
        common_data.pop('filename', None)
        common_data.pop(tmt.identifier.ID_KEY, None)
        echo(style(
            'You are trying to match one Polarion case to multiple Nitrate cases, '
            'please run export and sync these test cases', fg='red'))

    # Remove filename for a single test case to keep default name
    elif not individual_data and ':' not in polarion_case_id[0]:
        common_data.pop('filename', None)


def read_polarion_case(
        data: Union[NitrateDataType, list[NitrateDataType]],
        polarion_case_id: Optional[str],
        link_polarion: bool,
        dry_run: bool) -> None:
    """ Read data of specific case from Polarion """
    import tmt.export.polarion
    file_name: Optional[str] = None

    # Find Polarion case
    echo(style('Polarion ', fg='blue'), nl=False)
    if polarion_case_id:  # If we have Polarion ID we can ignore other data
        if ':' in polarion_case_id:
            polarion_case_id, file_name = polarion_case_id.split(':', 1)
        polarion_case = tmt.export.polarion.get_polarion_case(
            {}, polarion_case_id=polarion_case_id)
    else:
        # If Polarion case ID is not provided only common data is edited
        # data shouldn't be a list in that case
        if isinstance(data, list):
            raise ConvertError(
                'Common data ended up being a list which is wrong, this is likely a bug.')
        polarion_case = tmt.export.polarion.get_polarion_case(
            data, polarion_case_id=polarion_case_id)
    if not polarion_case:
        raise ConvertError('Failed to find test case in Polarion.')

    # Find correct nitrate case for this Polarion case or create a new one
    if isinstance(data, list):
        for testcase in data:
            if (
                    polarion_case.tcmscaseid and
                    polarion_case.tcmscaseid in testcase.get('extra-nitrate', '') or
                    testcase.get('extra-task') and
                    testcase.get('extra-task') in polarion_case.description):
                current_data = testcase
                break
        else:
            current_data = {}
            data.append(current_data)
    else:
        current_data = data

    # Update summary
    if not current_data.get('summary') or current_data['summary'] != polarion_case.title:
        current_data['summary'] = str(polarion_case.title)
        echo(style('summary: ', fg='green') + current_data['summary'])

    # Update description
    if polarion_case.description:
        description = str(polarion_case.description).replace('<br/>', '\n')
        if 'Environment variables' in description:
            description, envvars = description.split('Environment variables:', maxsplit=1)
            if not current_data.get('environment'):
                current_data['environment'] = {}
            for envvar in envvars.splitlines():
                envvar = envvar.strip()
                if not envvar:
                    continue  # skip empty lines
                key, value = envvar.split('=', maxsplit=1)
                current_data['environment'][key] = value
            echo(style('environment variables:', fg='green'))
            echo(format_value(current_data['environment']))
        current_data['description'] = description
        echo(style('description: ', fg='green') + current_data['description'])

    # Update status
    status = polarion_case.status == 'approved'
    if not current_data.get('enabled') or current_data['enabled'] != status:
        current_data['enabled'] = status
        echo(style('enabled: ', fg='green') + str(current_data['enabled']))

    # Update assignee
    if polarion_case.assignee:
        current_data['contact'] = str(polarion_case.assignee[0].name).replace(
            '(', ' <').replace(')', '@redhat.com>')
        echo(style('contact: ', fg='green') + current_data['contact'])

    # Set tmt id if available in Polarion, otherwise generate
    try:
        UUID(polarion_case.tmtid)
        uuid = str(polarion_case.tmtid)
    except (AttributeError, TypeError, ValueError):
        try:
            UUID(polarion_case.test_case_id)
            uuid = str(polarion_case.test_case_id)
        except (TypeError, ValueError):
            uuid = str(uuid4())
            if not dry_run:
                polarion_case.tmtid = uuid
                polarion_case.update()
                # Check if it was really uploaded
                polarion_case.tmtid = ''
                polarion_case.reload()
                if not polarion_case.tmtid:
                    echo(style(
                        f"Can't add ID because {polarion_case.project_id} project "
                        "doesn't have the 'tmtid' field defined.",
                        fg='yellow'))
    current_data[tmt.identifier.ID_KEY] = uuid
    echo(style('ID: ', fg='green') + uuid)

    # Update component
    if polarion_case.casecomponent:
        current_data['component'] = []
        if isinstance(polarion_case.casecomponent, str):
            current_data['component'].append(str(polarion_case.casecomponent))
        else:
            for component in polarion_case.casecomponent:
                current_data['component'].append(str(component))
        echo(style('component: ', fg='green') + ' '.join(current_data['component']))

    # Update tags
    if polarion_case.tags:
        if not current_data.get('tag'):
            current_data['tag'] = []
        # Space is the default separator, but let's try to autodetect couple different options
        # as Polarion tag field is free text so it can have anything
        separator = ' '
        if ',' in polarion_case.tags:
            separator = ','
        elif ';' in polarion_case.tags:
            separator = ';'
        for tag in polarion_case.tags.split(separator):
            current_data['tag'].append(tag)
            read_tier(tag, current_data)
        current_data['tag'] = sorted(set(current_data['tag']))
        echo(style('tag: ', fg='green') + ' '.join(current_data['tag']))

    # Add Polarion links for Requirements and the case
    if link_polarion:
        server_url = str(polarion_case._session._server.url)
        if not server_url.endswith('/'):
            server_url += '/'
        for link in polarion_case.linked_work_items:
            if link.role == 'verifies':
                add_link(
                    f'{server_url}#/project/{link.project_id}/'
                    f'workitem?id={link.work_item_id!s}',
                    current_data, system=SYSTEM_OTHER, type_=str(link.role))
        add_link(
            f'{server_url}#/project/{polarion_case.project_id}/workitem?id='
            f'{polarion_case.work_item_id!s}',
            current_data, system=SYSTEM_OTHER, type_='implements')
        if not file_name:
            file_name = str(polarion_case.work_item_id)

    # Set test/file name
    if not file_name:
        file_name = current_data['summary'].replace(' ', '_')
    current_data['filename'] = f'{file_name}.fmf'


RelevancyType = Union[str, list[str]]


def extract_relevancy(
        notes: str,
        field: tmt.utils.StructuredField) -> Optional[RelevancyType]:
    """ Get relevancy from testcase, respecting sf priority """
    try:
        if "relevancy" in field:
            return field.get("relevancy")
    except tmt.utils.StructuredFieldError:
        return None
    # Fallback to the original relevancy syntax
    # The relevancy definition begins with the header
    matched = re.search(RELEVANCY_LEGACY_HEADER, notes, re.IGNORECASE + re.MULTILINE + re.DOTALL)
    if not matched:
        return None
    relevancy = matched.groups()[0]
    # Remove possible additional text after an empty line
    matched = re.search(r"(.*?)\n\s*\n.*", relevancy, re.DOTALL)
    if matched:
        relevancy = matched.groups()[0]
    return relevancy.strip()


def read_nitrate_case(
        *,
        testcase: 'TestCase',
        makefile_data: Optional[NitrateDataType] = None,
        general: bool = False,
        logger: tmt.log.Logger
        ) -> NitrateDataType:
    """ Read old metadata from nitrate test case """
    import tmt.export.nitrate

    data: NitrateDataType = {'tag': []}
    echo(f"test case found '{testcase.identifier}'.")
    # Test identifier
    data['extra-nitrate'] = testcase.identifier
    # Beaker task name (taken from summary)
    if testcase.summary:
        data['extra-summary'] = testcase.summary
        echo(style('extra-summary: ', fg='green') + data['extra-summary'])
    # Contact
    if testcase.tester:
        # Full 'Name Surname <example@email.com>' form
        if testcase.tester.name is not None:
            data['contact'] = f'{testcase.tester.name} <{testcase.tester.email}>'
        elif makefile_data is None or 'contact' not in makefile_data:
            # Otherwise use just the email address
            data['contact'] = testcase.tester.email
        # Use contact from Makefile if it's there and email matches
        elif re.search(testcase.tester.email, makefile_data['contact']):
            data['contact'] = makefile_data['contact']
        else:
            # Otherwise use just the email address
            data['contact'] = testcase.tester.email
        echo(style('contact: ', fg='green') + data['contact'])
    # Environment
    if testcase.arguments:
        data['environment'] = tmt.utils.Environment.from_sequence(testcase.arguments, logger)
        if not data['environment']:
            data.pop('environment')
        else:
            echo(style('environment:', fg='green'))
            echo(format_value(data['environment']))
    # Possible multihost tag (detected in Makefile)
    if makefile_data:
        data['tag'].extend(makefile_data.get('tag', []))
    # Tags
    if testcase.tags:
        tags = []
        for tag in testcase.tags:
            if tag.name == 'fmf-export':
                continue
            tags.append(tag.name)
            read_tier(tag.name, data)
        # Include possible multihost tag (avoid duplicates)
        data['tag'] = sorted(set(tags + data['tag']))
        echo(style('tag: ', fg='green') + str(data['tag']))
    # Detect components either from general plans
    if general:
        data['component'] = []
        for nitrate_plan in testcase.testplans:
            if nitrate_plan.type.name == "General":
                match = re.search(GENERAL_PLAN, nitrate_plan.name)
                if match:
                    component = match.group(1)
                    if component not in data['component']:
                        echo(
                            f"Adding component '{component}' "
                            f"from the linked general plan.")
                        data['component'].append(component)
    else:
        # Or from test case components
        data['component'] = [comp.name for comp in testcase.components]
    echo(style('component: ', fg='green') + ' '.join(data['component']))
    # Status
    data['enabled'] = testcase.status.name == "CONFIRMED"
    echo(style('enabled: ', fg='green') + str(data['enabled']))
    # Set manual attribute to manual tests only
    if not testcase.automated:
        data['manual'] = True
    # Relevancy
    field = tmt.utils.StructuredField(testcase.notes)
    relevancy = extract_relevancy(testcase.notes, field)
    if relevancy:
        data['adjust'] = relevancy_to_adjust(relevancy, logger)
        echo(style('adjust:', fg='green'))
        echo(tmt.utils.dict_to_yaml(data['adjust']).strip())

    # Extend bugs detected from Makefile with those linked in Nitrate
    try:
        if makefile_data is not None and 'link' in makefile_data:
            data['link'] = makefile_data['link'].copy()
    except (KeyError, TypeError):
        pass
    for bug in testcase.bugs:
        add_link(bug.bug, data, bug.system)

    # Header and footer from notes (do not import the warning back)
    data['description'] = re.sub(
        tmt.export.nitrate.WARNING, '', field.header() + field.footer())

    # Extras: [pepa] and [hardware]
    try:
        extra_pepa = field.get('pepa')
        if extra_pepa:
            data['extra-pepa'] = extra_pepa
            echo(style('extra-pepa:', fg='green'))
            echo(data['extra-pepa'].rstrip('\n'))
    except tmt.utils.StructuredFieldError:
        pass
    try:
        extra_hardware = field.get('hardware')
        if extra_hardware:
            data['extra-hardware'] = extra_hardware
            echo(style('extra-hardware:', fg='green'))
            echo(data['extra-hardware'].rstrip('\n'))
    except tmt.utils.StructuredFieldError:
        pass

    return data


def adjust_runtest(path: Path) -> None:
    """ Adjust runtest.sh content and permission """

    # Nothing to do if there is no runtest.sh
    if not path.exists():
        return

    # Remove sourcing of rhts-environment.sh and update beakerlib path
    rhts_line = '. /usr/bin/rhts-environment.sh'
    old_beakerlib_path1 = '. /usr/lib/beakerlib/beakerlib.sh'
    old_beakerlib_path2 = '. /usr/share/rhts-library/rhtslib.sh'
    new_beakerlib_path = '. /usr/share/beakerlib/beakerlib.sh || exit 1\n'
    try:
        with open(path, 'r+') as runtest:
            lines = runtest.readlines()
            runtest.seek(0)
            for line in lines:
                if rhts_line in line:
                    echo(style(
                        "Removing sourcing of 'rhts-environment.sh' "
                        "from 'runtest.sh'.", fg='magenta'))
                elif (old_beakerlib_path1 in line
                        or old_beakerlib_path2 in line):
                    runtest.write(new_beakerlib_path)
                    echo(style(
                        "Replacing old beakerlib path with new one "
                        "in 'runtest.sh'.", fg='magenta'))
                else:
                    runtest.write(line)
            runtest.truncate()
    except OSError:
        raise ConvertError(f"Unable to read/write '{path}'.")

    # Make sure the script has correct execute permissions
    try:
        path.chmod(0o755)
    except OSError:
        raise tmt.convert.ConvertError(
            f"Could not make '{path}' executable.")


def write(path: Path, data: NitrateDataType, quiet: bool = False) -> None:
    """ Write gathered metadata in the fmf format """
    # Put keys into a reasonable order
    extra_keys = [
        'adjust', 'extra-nitrate',
        'extra-summary', 'extra-task',
        'extra-hardware', 'extra-pepa']
    sorted_data = {}
    for key in tmt.base.Test._keys() + extra_keys:
        with suppress(KeyError):
            sorted_data[key] = data[key]

    # Store metadata into a fmf file
    try:
        with open(path, 'w', encoding='utf-8') as fmf_file:
            fmf_file.write(tmt.utils.dict_to_yaml(sorted_data))
    except OSError:
        raise ConvertError(f"Unable to write '{path}'")
    if not quiet:
        echo(style(
            f"Metadata successfully stored into '{path}'.", fg='magenta'))


def relevancy_to_adjust(
        relevancy: RelevancyType,
        logger: tmt.log.Logger) -> list[NitrateDataType]:
    """
    Convert the old test case relevancy into adjust rules

    Expects a string or list of strings with relevancy rules.
    Returns a list of dictionaries with adjust rules.
    """
    rules = []
    rule = {}
    if isinstance(relevancy, list):
        relevancy = '\n'.join(str(line) for line in relevancy)

    for line in re.split(r'\s*\n\s*', relevancy.strip()):
        # Extract possible comments
        search_result = re.search(RELEVANCY_COMMENT, line)
        if search_result is not None:
            line, rule['because'] = search_result.groups()

        # Nothing to do with empty lines
        if not line:
            continue

        # Split rule
        search_result = re.search(RELEVANCY_RULE, line)
        if search_result is None:
            raise tmt.utils.ConvertError(
                f"Invalid test case relevancy rule '{line}'.")
        condition, decision = search_result.groups()

        # Handle the decision
        if decision.lower() == 'false':
            rule['enabled'] = False
        else:
            try:
                rule['environment'] = tmt.utils.Environment.from_sequence(decision, logger)
            except tmt.utils.GeneralError:
                raise tmt.utils.ConvertError(
                    f"Invalid test case relevancy decision '{decision}'.")

        # Adjust condition syntax
        expressions = []
        for expression in re.split(r'\s*&&?\s*', condition):
            search_result = re.search(RELEVANCY_EXPRESSION, expression)
            if search_result is None:
                raise tmt.utils.ConvertError(
                    f"Invalid test case relevancy expression '{expression}'.")
            left, operator, right = search_result.groups()
            # Always use double == for equality comparison
            if operator == '=':
                operator = '=='
            # Basic operators
            if operator in ['==', '!=', '<', '<=', '>', '>=']:
                # Use the special comparison for product and distro
                # when the definition specifies a minor version
                if left in ['distro', 'product'] and '.' in right:
                    operator = '~' + ('=' if operator == '==' else operator)
            # Special operators
            else:
                try:
                    operator = {
                        'contains': '==',
                        '!contains': '!=',
                        'defined': 'is defined',
                        '!defined': 'is not defined',
                        }[operator]
                except KeyError:
                    raise tmt.utils.ConvertError(
                        f"Invalid test case relevancy operator '{operator}'.")
            # Special handling for the '!=' operator with comma-separated
            # values (in relevancy this was treated as 'no value equals')
            values = re.split(r'\s*,\s*', right)
            if operator == '!=' and len(values) > 1:
                for value in values:
                    expressions.append(f"{left} != {value}")
                continue
            # Join 'left operator right' with spaces
            expressions.append(
                ' '.join([item for item in [left, operator, right] if item]))

        # Finish the rule definition
        rule['when'] = ' and '.join(expressions)
        rule['continue'] = False
        rules.append(rule)
        rule = {}

    return rules
