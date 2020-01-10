# coding: utf-8

""" Convert metadata into the new format """

from io import open
from click import echo, style
from tmt.utils import ConvertError, StructuredFieldError

import fmf.utils
import tmt.utils
import pprint
import copy
import yaml
import re
import os

log = fmf.utils.Logging('tmt').logger

# Import nitrate conditionally (reading from nitrate can be skipped)
try:
    from nitrate import TestCase
except ImportError:
    TestCase = None

# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#  YAML
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

# Special hack to store multiline text with the '|' style
# See https://stackoverflow.com/questions/45004464/
# Python 2 version
try:
    yaml.SafeDumper.orig_represent_unicode = yaml.SafeDumper.represent_unicode
    def repr_unicode(dumper, data):
        if '\n' in data:
            return dumper.represent_scalar(
                u'tag:yaml.org,2002:str', data, style='|')
        return dumper.orig_represent_unicode(data)
    yaml.add_representer(unicode, repr_unicode, Dumper=yaml.SafeDumper)
# Python 3 version
except AttributeError:
    yaml.SafeDumper.orig_represent_str = yaml.SafeDumper.represent_str
    def repr_str(dumper, data):
        if '\n' in data:
            return dumper.represent_scalar(
                u'tag:yaml.org,2002:str', data, style='|')
        return dumper.orig_represent_str(data)
    yaml.add_representer(str, repr_str, Dumper=yaml.SafeDumper)

# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#  Convert
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

def read(path, makefile, nitrate, purpose):
    """ Read old metadata from various sources """
    echo(style("Checking the '{0}' directory.".format(path), fg='red'))

    data = dict()

    # Makefile (extract summary, component and duration)
    if makefile:
        echo(style('Makefile ', fg='blue'), nl=False)
        makefile_path = os.path.join(path, 'Makefile')
        try:
            with open(makefile_path, encoding='utf-8') as makefile:
                content = makefile.read()
        except IOError:
            raise ConvertError("Unable to open '{0}'.".format(makefile_path))
        echo("found in '{0}'.".format(makefile_path))
        # Test
        test = re.search('export TEST=(.*)\n', content).group(1)
        echo(style('test: ', fg='green') + test)
        # Summary
        data['summary'] = re.search(
            r'echo "Description:\s*(.*)"', content).group(1)
        echo(style('description: ', fg='green') + data['summary'])
        # Component
        data['component'] = re.search(
            r'echo "RunFor:\s*(.*)"', content).group(1)
        echo(style('component: ', fg='green') + data['component'])
        # Duration
        data['duration'] = re.search(
            r'echo "TestTime:\s*(.*)"', content).group(1)
        echo(style('duration: ', fg='green') + data['duration'])

    # Purpose (extract everything after the header as a description)
    if purpose:
        echo(style('Purpose ', fg='blue'), nl=False)
        purpose_path = os.path.join(path, 'PURPOSE')
        try:
            with open(purpose_path, encoding='utf-8') as purpose:
                content = purpose.read()
        except IOError:
            raise ConvertError("Unable to open '{0}'.".format(purpose_path))
        echo("found in '{0}'.".format(purpose_path))
        for header in ['PURPOSE', 'Description', 'Author']:
            content = re.sub('^{0}.*\n'.format(header), '', content)
        data['description'] = content.lstrip('\n')
        echo(style('description:', fg='green'))
        echo(data['description'].rstrip('\n'))

    # Nitrate (extract contact, environment and relevancy)
    if nitrate:
        echo(style('Nitrate ', fg='blue'), nl=False)
        if test is None:
            raise ConvertError('No test name detected for nitrate search')
        if TestCase is None:
            raise ConvertError('Need nitrate module to import metadata')
        testcases = list(TestCase.search(script=test))
        if not testcases:
            raise ConvertError("No testcase found for '{0}'.".format(test))
        elif len(testcases) > 1:
            log.warn("Multiple test cases found for '{0}'.".format(
                test))

        testcase_data = list()

        for testcase in testcases:
            single_case_data = dict()
            echo("test case found '{0}'.".format(testcase.identifier))
            # Test identifier
            single_case_data['tcms id'] = testcase.identifier
            # Test name
            if testcase.summary:
                single_case_data['testname'] = '{}'.format(
                    testcase.summary)
                echo(style('test name: ', fg='green') + single_case_data['testname'])
            # Contact
            if testcase.tester:
                single_case_data['contact'] = '{} <{}>'.format(
                    testcase.tester.name, testcase.tester.email)
                echo(style('contact: ', fg='green') + single_case_data['contact'])
            # Environment
            if testcase.arguments:
                single_case_data['environment'] = tmt.utils.variables_to_dictionary(
                    testcase.arguments)
                echo(style('environment:', fg='green'))
                echo(pprint.pformat(single_case_data['environment']))
            # Relevancy
            field = tmt.utils.StructuredField(testcase.notes)
            single_case_data['relevancy'] = field.get('relevancy')
            echo(style('relevancy:', fg='green'))
            echo(single_case_data['relevancy'].rstrip('\n'))
            testcase_data.append(single_case_data)

        common_candidates = dict()

        # Find common data from individual test cases
        for testcase in testcase_data:
            if testcase_data.index(testcase) == 0:
                common_candidates = copy.copy(testcase)
            else:
                for key, value in testcase.items():
                    if key in common_candidates:
                        if value != common_candidates[key]:
                            common_candidates.pop(key)

        # Add common data to main.fmf
        for key, value in common_candidates.items():
            data[key] = value

        # Remove common data from individual fmfs
        for common_key in list(common_candidates):
            for testcase in testcase_data:
                if common_key in testcase:
                    testcase.pop(common_key)

    log.debug('Gathered metadata:\n' + pprint.pformat(data))
    return data, testcase_data


def write(path, data):
    """ Write gathered metadata in the fmf format """
    # Make sure there is a metadata tree initialized
    try:
        tree = fmf.Tree(os.path.dirname(path))
    except fmf.utils.RootError:
        raise ConvertError("Initialize metadata tree using 'fmf init'.")
    # Store metadata into a fmf file
    try:
        with open(path, 'w', encoding='utf-8') as fmf_file:
            yaml.safe_dump(
                    data, fmf_file,
                    encoding='utf-8', allow_unicode=True,
                    indent=4, default_flow_style=False)
    except IOError:
        raise ConvertError("Unable to write '{0}'".format(path))
    echo(style(
        "Metadata successfully stored into '{0}'.".format(path), fg='red'))
