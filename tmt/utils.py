
""" Test Metadata Utilities """

from click import style, echo, wrap_text

from collections import OrderedDict
import unicodedata
import subprocess
import fmf.utils
import pprint
import shlex
import select
import shutil
import yaml
import re
import io
import os

log = fmf.utils.Logging('tmt').logger

# Default workdir root and max
WORKDIR_ROOT = '/var/tmp/tmt'
WORKDIR_MAX = 1000

# Maximum number of lines of stdout/stderr to show upon errors
OUTPUT_LINES = 100
# Default output width
OUTPUT_WIDTH = 79

# Hierarchy indent
INDENT = 4

# Default name and order for step plugins
DEFAULT_NAME = 'default'
DEFAULT_PLUGIN_ORDER = 50
DEFAULT_PLUGIN_ORDER_REQUIRES = 70

# Config directory
CONFIG_PATH = '~/.config/tmt'


class Config(object):
    """ User configuration """

    def __init__(self):
        """ Initialize config directory path """
        self.path = os.path.expanduser(CONFIG_PATH)
        if not os.path.exists(self.path):
            try:
                os.makedirs(self.path)
            except OSError as error:
                raise GeneralError(
                    f"Failed to create config '{self.path}'.\n{error}")

    def last_run(self, run_id=None):
        """ Get and set last run id """
        symlink = os.path.join(self.path, 'last-run')
        if run_id:
            try:
                os.remove(symlink)
            except OSError:
                pass
            try:
                os.symlink(run_id, symlink)
            except OSError as error:
                raise GeneralError(
                    f"Unable to save last run '{self.path}'.\n{error}")
            return run_id
        if os.path.islink(symlink):
            return os.path.realpath(symlink)
        return None


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#  Common
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

class Common(object):
    """
    Common shared stuff

    Takes care of command line context and workdir handling.
    Provides logging functions info(), verbose() and debug().
    Implements read() and write() for comfortable file access.
    Provides the run() method for easy command execution.
    """

    # Command line context and workdir
    _context = None
    _workdir = None

    def __init__(self, parent=None, name=None, workdir=None, context=None):
        """
        Initialize name and relation with the parent object

        Prepare the workdir for provided id / directory path
        or generate a new workdir name if workdir=True given.
        Store command line context for future use if provided.
        """
        # Use lowercase class name as the default name
        self.name = name or self.__class__.__name__.lower()
        self.parent = parent

        # Initialize the workdir if requested
        if workdir is True:
            self._workdir_init()
        elif workdir is not None:
            self._workdir_init(workdir)

        # Store command line context
        if context:
            self._context = context


    def __str__(self):
        """ Name is the default string representation """
        return self.name

    @classmethod
    def _save_context(cls, context):
        """ Save provided command line context for future use """
        cls._context = context

    @classmethod
    def _opt(cls, option, default=None):
        """ Get an option from the command line context (class version) """
        if cls._context is None:
            return None
        return cls._context.params.get(option, default)

    def opt(self, option, default=None):
        """
        Get an option from the command line context

        Checks also parent options. For flags (boolean values) parent's
        True wins over child's False (e.g. run --verbose enables verbose
        mode for all included plans and steps).
        """
        # Check local option
        local = default
        if self._context is not None:
            local = self._context.params.get(option, default)
        # Check parent option
        parent = None
        if self.parent:
            parent = self.parent.opt(option)
        # Special handling for special flags (parent's yes always wins)
        if option in ['verbose', 'debug', 'quiet', 'force', 'dry']:
            winner = parent if parent else local
            # Convert tuple of booleans into debug/verbose level (int)
            if option in ['verbose', 'debug']:
                if isinstance(winner, tuple):
                    winner = len(winner)
                if winner is None:
                    winner = 0
            return winner
        return parent if parent is not None else local

    def _level(self):
        """ Hierarchy level """
        if self.parent is None:
            return -1
        else:
            return self.parent._level() + 1

    def _indent(self, key, value=None, color=None, shift=0):
        """ Indent message according to the object hierarchy """
        level = self._level() + shift
        indent = ' ' * INDENT * level
        deeper = ' ' * INDENT * (level + 1)
        # Colorize
        if color is not None:
            key = style(key, fg=color)
        # Handle key only
        if value is None:
            message = key
        # Handle key + value
        else:
            # Multiline content indented deeper
            if isinstance(value, str):
                lines = value.splitlines()
                if len(lines) > 1:
                    value = ''.join([f"\n{deeper}{line}" for line in lines])
            message = f'{key}: {value}'
        return indent + message

    def _log(self, message):
        """ Append provided message to the current log """
        if self.workdir is None:
            return
        with open(os.path.join(self.workdir, 'log.txt'), 'a') as log:
            log.write(message + '\n')

    def info(self, key, value=None, color=None, shift=0):
        """ Show a message unless in quiet mode """
        self._log(self._indent(key, value, color=None, shift=shift))
        if not self.opt('quiet'):
            echo(self._indent(key, value, color, shift))

    def verbose(self, key, value=None, color=None, shift=0, level=1):
        """ Show message if in requested verbose mode level """
        self._log(self._indent(key, value, color=None, shift=shift))
        if self.opt('verbose') >= level:
            echo(self._indent(key, value, color, shift))

    def debug(self, key, value=None, color=None, shift=1, level=1):
        """ Show message if in requested debug mode level """
        self._log(self._indent(key, value, color=None, shift=shift))
        if self.opt('debug') >= level:
            echo(self._indent(key, value, color, shift))

    def _run(self, command, cwd, shell, env):
        """ Run command, capture the output """
        # Prepare the environment
        if env:
            if not isinstance(env, dict):
                raise tmt.utils.GeneralError(f"Invalid environment '{env}'.")
            # Do not modify current process environment
            environment = os.environ.copy()
            environment.update(env)
        else:
            environment = None

        # Create the process
        process = subprocess.Popen(
            command, cwd=cwd, shell=shell, env=environment,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        descriptors = [process.stdout.fileno(), process.stderr.fileno()]
        stdout = ''
        stderr = ''

        # Capture the output
        while process.poll() is None:
            # Check which file descriptors are ready for read
            selected = select.select(descriptors, [], [])
            for descriptor in selected[0]:
                # Handle stdout
                if descriptor == process.stdout.fileno():
                    line = process.stdout.readline().decode('utf-8')
                    stdout += line
                    if line != '':
                        self.debug('out', line.rstrip('\n'), 'yellow', level=3)
                # Handle stderr
                if descriptor == process.stderr.fileno():
                    line = process.stderr.readline().decode('utf-8')
                    stderr += line
                    if line != '':
                        self.debug('err', line.rstrip('\n'), 'yellow', level=3)

        # Check for possible additional output
        for line in process.stdout.readlines():
            line = line.decode('utf-8')
            stdout += line
            self.debug('out', line.rstrip('\n'), 'yellow', level=3)
        for line in process.stderr.readlines():
            line = line.decode('utf-8')
            stderr += line
            self.debug('err', line.rstrip('\n'), 'yellow', level=3)

        # Handle the exit code, return output
        if process.returncode != 0:
            if isinstance(command, (list, tuple)):
                command = ' '.join(command)
            raise RunError(
                message=f"Command returned '{process.returncode}'.",
                command=command, stdout=stdout, stderr=stderr)
        return stdout, stderr

    def run(
            self, command, message=None,
            cwd=None, dry=False, shell=True, env=None):
        """
        Run command, give message, handle errors

        Command is run in the workdir be default.
        In dry mode commands are not executed unless dry=True.
        Environment is updated with variables from the 'env' dictionary.
        Returns (stdout, stderr) tuple.
        """
        # Use a generic message if none given, prepare error message
        if not message:
            if isinstance(command, (list, tuple)):
                line = ' '.join(command)
            else:
                line = command
            message = f"Run command '{line}'."
        self.debug(message, level=2)
        message = "Failed to " + message[0].lower() + message[1:]

        # Nothing more to do in dry mode (unless requested)
        if self.opt('dry') and not dry:
            return None, None

        # Prepare command, run it, handle the exit code
        try:
            return self._run(
                command, cwd=cwd or self.workdir, shell=shell, env=env)
        except RunError as error:
            self.debug(error.message, level=3)
            raise RunError(message, error.command, error.stdout, error.stderr)

    def read(self, path):
        """ Read a file from the workdir """
        if self.workdir:
            path = os.path.join(self.workdir, path)
        self.debug(f"Read file '{path}'.", level=2)
        try:
            with open(path) as data:
                return data.read()
        except OSError as error:
            raise FileError(f"Failed to read '{path}'.\n{error}")

    def write(self, path, data):
        """ Write a file to the workdir """
        if self.workdir:
            path = os.path.join(self.workdir, path)
        self.debug(f"Write file '{path}'.", level=2)
        # Dry mode
        if self.opt('dry'):
            return
        try:
            with open(path, 'w') as target:
                return target.write(data)
        except OSError as error:
            raise FileError(f"Failed to write '{path}'.\n{error}")

    def _workdir_init(self, id_=None):
        """
        Initialize the work directory

        Workdir under WORKDIR_ROOT is used/created if 'id' is provided.
        If 'id' is a path, that directory is used instead. Otherwise a
        new workdir is created under the WORKDIR_ROOT directory.
        """
        # Prepare the workdir name from given id or path
        if isinstance(id_, str):
            # Use provided directory if full path given
            if '/' in id_:
                workdir = id_
            # Construct directory name under workdir root
            else:
                workdir = os.path.join(WORKDIR_ROOT, id_)
        # Generate a unique workdir name
        elif id_ is None:
            for id_ in range(1, WORKDIR_MAX + 1):
                directory = 'run-{}'.format(str(id_).rjust(3, '0'))
                workdir = os.path.join(WORKDIR_ROOT, directory)
                if not os.path.exists(workdir):
                    break
            if id_ == WORKDIR_MAX:
                raise GeneralError(
                    f"Workdir full. Cleanup the '{WORKDIR_ROOT}' directory.")
        # Weird workdir id
        else:
            raise GeneralError(
                f"Invalid workdir '{id_}', expected a string or None.")

        # Create the workdir
        create_directory(workdir, 'workdir', quiet=True)
        self._workdir = workdir

    def _workdir_name(self):
        """ Construct work directory name from parent workdir """
        # Need the parent workdir
        if self.parent is None or self.parent.workdir is None:
            return None
        # Join parent name with self
        return os.path.join(self.parent.workdir, self.name.lstrip('/'))

    def _workdir_cleanup(self):
        """ Clean up the work directory """
        directory = self._workdir_name()
        if os.path.isdir(directory):
            self.debug(f"Clean up workdir '{directory}'.", level=2)
            shutil.rmtree(directory)
        self._workdir = None

    @property
    def workdir(self):
        """ Get the workdir, create if does not exist """
        if self._workdir is None:
            self._workdir = self._workdir_name()
            # Workdir not enabled, even parent does not have one
            if self._workdir is None:
                return None
            # Create a child workdir under the parent workdir
            create_directory(self._workdir, 'workdir', quiet=True)
        return self._workdir

# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#  Exceptions
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

class GeneralError(Exception):
    """ General error """

class FileError(GeneralError):
    """ File operation error """

class RunError(GeneralError):
    """ Command execution error """
    def __init__(self, message, command, stdout, stderr):
        self.message = message
        self.command = command
        self.stdout = stdout
        self.stderr = stderr

class SpecificationError(GeneralError):
    """ Metadata specification error """

class ConvertError(GeneralError):
    """ Metadata conversion error """

class StructuredFieldError(GeneralError):
    """ StructuredField parsing error """

# Step exceptions

class DiscoverError(GeneralError):
    """ Discover step error """

class ProvisionError(GeneralError):
    """ Provision step error """

class PrepareError(GeneralError):
    """ Prepare step error """

class ExecuteError(GeneralError):
    """ Execute step error """

class ReportError(GeneralError):
    """ Report step error """

class FinishError(GeneralError):
    """ Finish step error """

# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#  Utilities
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

def quote(string):
    """ Surround a string with double quotes """
    return f'"{string}"'


def ascii(text):
    """ Transliterate special unicode characters into pure ascii """
    try:
        if not isinstance(text, unicode):
            text = unicode(text)
    except NameError:
        if not isinstance(text, str):
            text = str(text)
    return unicodedata.normalize('NFKD', text).encode('ascii','ignore')


def listify(data, split=False, keys=None):
    """
    Ensure that variable is a list, convert if necessary

    For dictionaries check all items or only those with provided keys.
    Also split strings on white-space/comma if split=True.
    """
    separator = re.compile(r'[\s,]+')
    if isinstance(data, tuple):
        data = list(data)
    if isinstance(data, list):
        return fmf.utils.split(data, separator) if split else data
    if isinstance(data, str):
        return fmf.utils.split(data, separator) if split else [data]
    if isinstance(data, dict):
        for key in keys or data:
            if key in data:
                data[key] = listify(data[key], split=split)
        return data
    return [data]


def shell_to_dict(variables):
    """
    Convert shell-like variables into a dictionary

    Accepts single string or list of strings. Allowed forms are:
    'X=1'
    'X=1 Y=2 Z=3'
    ['X=1', 'Y=2', 'Z=3']
    ['X=1 Y=2 Z=3', 'A=1 B=2 C=3']
    'TXT="Some text with spaces in it"'
    """
    if not isinstance(variables, (list, tuple)):
        variables = [variables]
    result = dict()
    for variable in variables:
        if variable is None:
            continue
        for var in shlex.split(variable):
            matched = re.match("([^=]+)=(.*)", var)
            if not matched:
                raise GeneralError("Invalid variable specification '{var}'.")
            name, value = matched.groups()
            result[name] = value
    return result


def dict_to_yaml(data, width=None, sort=False):
    """ Convert dictionary into yaml """
    output = io.StringIO()
    yaml.safe_dump(
        data, output, sort_keys=sort,
        encoding='utf-8', allow_unicode=True,
        width=width, indent=4, default_flow_style=False)
    return output.getvalue()

# FIXME: Temporary workaround for rhel-8 to disable key sorting
# https://stackoverflow.com/questions/31605131/
# https://github.com/psss/tmt/issues/207
try:
    output = dict_to_yaml(dict(one=1, two=2, three=3))
except TypeError:
    representer = lambda self, data: self.represent_mapping(
        'tag:yaml.org,2002:map', data.items())
    yaml.add_representer(dict, representer, Dumper=yaml.SafeDumper)
    def dict_to_yaml(data, width=None, sort=False):
        """ Convert dictionary into yaml (ignore sort) """
        output = io.StringIO()
        yaml.safe_dump(
            data, output, encoding='utf-8', allow_unicode=True,
            width=width, indent=4, default_flow_style=False)
        return output.getvalue()


def yaml_to_dict(data):
    """ Convert yaml into dictionary """
    return yaml.safe_load(data)


def shell_variables(data):
    """
    Prepare variables to be consumed by shell

    Convert dictionary or list/tuple of key=value pairs to list of
    key=value pairs where value is quoted with shlex.quote().
    """

    # Convert from list/tuple
    if isinstance(data, list) or isinstance(data, tuple):
        converted_data = []
        for item in data:
            splitted_item = item.split('=')
            key = splitted_item[0]
            value = shlex.quote('='.join(splitted_item[1:]))
            converted_data.append(f'{key}={value}')
        return converted_data

    # Convert from dictionary
    return [f"{key}={shlex.quote(str(value))}" for key, value in data.items()]


def verdict(decision, comment=None, good='pass', bad='fail', problem='warn'):
    """
    Return verdict in green or red based on the decision

    0 or False ... good (green)
    1 or True .... bad (red)
    otherwise .... problem (yellow)
    """

    if decision == 0:
        text = style(bad, fg='red')
    elif decision == 1:
        text = style(good, fg='green')
    else:
        text = style(problem, fg='yellow')
    if comment:
        return text + ' ' + comment
    else:
        return text


def format(
        key, value=None,
        indent=12, width=72, wrap='auto',
        key_color='green', value_color='black'):
    """
    Nicely format and indent a key-value pair

    The following values for 'wrap' are supported:

        True .... always reformat text and wrap long lines
        False ... preserve text, no new line changes
        auto .... wrap only if text contains a long line
    """
    indent_string = (indent + 1) * ' '
    # Key
    output = '{} '.format(str(key).rjust(indent, ' '))
    if key_color is not None:
        output = style(output, fg=key_color)
    # Bool
    if isinstance(value, bool):
        output += ('yes' if value else 'no')
    # List
    elif isinstance(value, list):
        listed_text = fmf.utils.listed(value)
        has_spaces = any([item.find(' ') > -1 for item in value])
        # Use listed output only for short lists without spaces
        if len(listed_text) < width - indent and not has_spaces:
            output += listed_text
        # Otherwise just place each item on a new line
        else:
            output += ('\n' + indent_string).join(value)
    # Dictionary
    elif isinstance(value, dict):
        # Place each key value pair on a separate line
        output += ('\n' + indent_string).join(
            f'{item[0]}: {item[1]}' for item in value.items())
    # Text
    elif isinstance(value, str):
        # In 'auto' mode enable wrapping when long lines present
        if wrap == 'auto':
            wrap = any(
                [len(line) + indent - 7 > width
                for line in value.split('\n')])
        if wrap:
            output += (wrap_text(
                value, width=width,
                preserve_paragraphs=True,
                initial_indent=indent_string,
                subsequent_indent=indent_string).lstrip())
        else:
            output += (('\n' + indent_string).join(
                value.rstrip().split('\n')))
    else:
        output += str(value)
    return output


def create_directory(path, name, quiet=False):
    """ Create a new directory, handle errors """
    say = log.debug if quiet else echo
    if os.path.isdir(path):
        say("Directory '{}' already exists.".format(path))
        return
    try:
        os.makedirs(path, exist_ok=True)
        say("Directory '{}' created.".format(path))
    except OSError as error:
        raise FileError("Failed to create {} '{}' ({})".format(
            name, path, error))


def create_file(path, content, name, force=False, mode=0o664, quiet=False):
    """ Create a new file, handle errors """
    say = log.debug if quiet else echo
    action = 'created'
    if os.path.exists(path):
        if force:
            action = 'overwritten'
        else:
            raise FileError("File '{}' already exists.".format(path))
    try:
        with open(path, 'w') as file_:
            file_.write(content)
        say("{} '{}' {}.".format(name.capitalize(), path, action))
        os.chmod(path, mode)
    except OSError as error:
        raise FileError("Failed to create {} '{}' ({})".format(
            name, path, error))


def public_git_url(url):
    """
    Convert a git url into a public format

    Return url in the format which can be accessed without
    authentication. For now just cover the most common services.
    """

    # GitHub, GitLab
    # old: git@github.com:psss/tmt.git
    # new: https://github.com/psss/tmt.git
    matched = re.match('git@(.*):(.*)', url)
    if matched:
        host, project = matched.groups()
        return f'https://{host}/{project}'

    # RHEL packages
    # old: ssh://psplicha@pkgs.devel.redhat.com/tests/bash
    # old: ssh://pkgs.devel.redhat.com/tests/bash
    # new: git://pkgs.devel.redhat.com/tests/bash
    matched = re.match(r'ssh://(\w+@)?(pkgs\.devel\.redhat\.com)/(.*)', url)
    if matched:
        _, host, project = matched.groups()
        return f'git://{host}/{project}'

    # Fedora packages, Pagure
    # old: ssh://psss@pkgs.fedoraproject.org/tests/shell
    # new: https://pkgs.fedoraproject.org/tests/shell
    matched = re.match(r'ssh://(\w+@)?([^/]*)/(.*)', url)
    if matched:
        _, host, project = matched.groups()
        return f'https://{host}/{project}'

    # Otherwise return unmodified
    return url


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#  StructuredField
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

class StructuredField(object):
    """
    Handling multiple text data in a single text field

    The StructuredField allows you to easily store and extract several
    sections of text data to/from a single text field. The sections are
    separated by section names in square brackets and can be hosted in
    other text as well.

    The section names have to be provided on a separate line and there
    must be no leading/trailing white space before/after the brackets.
    The StructuredField supports two versions of the format:

    Version 0: Simple, concise, useful when neither the surrounding text
    or the section data can contain lines which could resemble section
    names. Here's an example of a simple StructuredField::

        Note written by human.

        [section-one]
        Section one content.

        [section-two]
        Section two content.

        [section-three]
        Section three content.

        [end]

        Another note written by human.

    Version 1: Includes unique header to prevent collisions with the
    surrounding text and escapes any section-like lines in the content::

        Note written by human.

        [structured-field-start]
        This is StructuredField version 1. Please, edit with care.

        [section-one]
        Section one content.

        [section-two]
        Section two content.
        [structured-field-escape][something-resembling-section-name]

        [section-three]
        Section three content.

        [structured-field-end]

        Another note written by human.

    Note that an additional empty line is added at the end of each
    section to improve the readability. This line is not considered
    to be part of the section content.

    Besides handling the whole section content it's also possible to
    store several key-value pairs in a single section, similarly as in
    the ini config format::

        [section]
        key1 = value1
        key2 = value2
        key3 = value3

    Provide the key name as the optional argument 'item' when accessing
    these single-line items. Note that the section cannot contain both
    plain text data and key-value pairs.

    Example::

        field = qe.StructuredField()
        field.set("project", "Project Name")
        field.set("details", "somebody", "owner")
        field.set("details", "2013-05-27", "started")
        field.set("description", "This is a description.\\n"
                "It spans across multiple lines.\\n")
        print field.save()

            [structured-field-start]
            This is StructuredField version 1. Please, edit with care.

            [project]
            Project Name

            [details]
            owner = somebody
            started = 2013-05-27

            [description]
            This is a description.
            It spans across multiple lines.

            [structured-field-end]

        field.version(0)
        print field.save()

            [project]
            Project Name

            [details]
            owner = somebody
            started = 2013-05-27

            [description]
            This is a description.
            It spans across multiple lines.

            [end]

    Multiple values for the same key are supported as well. Enable this
    feature with 'multi=True' when initializing the structured field.
    If multiple values are present their list will be returned instead
    of a single string. Similarly use list for setting multiple values::

        field = qe.StructuredField(multi=True)
        requirements = ['hypervisor=', 'labcontroller=lab.example.com']
        field.set("hardware", requirements, "hostrequire")
        print field.save()

            [structured-field-start]
            This is StructuredField version 1. Please, edit with care.

            [hardware]
            hostrequire = hypervisor=
            hostrequire = labcontroller=lab.example.com

            [structured-field-end]

        print field.get("hardware", "hostrequire")

            ['hypervisor=', 'labcontroller=lab.example.com']
    """

    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    #  StructuredField Special
    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    def __init__(self, text=None, version=1, multi=False):
        """ Initialize the structured field """
        self.version(version)
        self._header = ""
        self._footer = ""
        self._sections = {}
        self._order = []
        self._multi = multi
        if text is not None:
            self.load(text)

    def __iter__(self):
        """ By default iterate through all available sections """
        for section in self._order:
            yield section

    def __nonzero__(self):
        """ True when any section is defined """
        return len(self._order) > 0

    __bool__ = __nonzero__

    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    #  StructuredField Private
    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    def _load_version_zero(self, text):
        """ Load version 0 format """
        # Attempt to split the text according to the section tag
        section = re.compile(r"\n?^\[([^\]]+)\]\n", re.MULTILINE)
        parts = section.split(text)
        # If just one part ---> no sections present, just plain text
        if len(parts) == 1:
            self._header = parts[0]
            return
        # Pick header & footer, make sure [end] tag is present
        self._header = parts[0]
        self._footer = re.sub("^\n", "", parts[-1])
        if parts[-2] != "end":
            raise StructuredFieldError("No [end] section tag found")
        # Convert to dictionary and save the order
        keys = parts[1:-2:2]
        values = parts[2:-2:2]
        for key, value in zip(keys, values):
            self.set(key, value)

    def _load(self, text):
        """ Load version 1+ format """
        # The text must exactly match the format
        format = re.compile(
                r"(.*)^\[structured-field-start\][ \t]*\n"
                r"(.*)\n\[structured-field-end\][ \t]*\n(.*)",
                re.DOTALL + re.MULTILINE)
        # No match ---> plain text or broken structured field
        matched = format.search(text)
        if not matched:
            if "[structured-field" in text:
                raise StructuredFieldError("StructuredField parse error")
            self._header = text
            log.debug("StructuredField not found, treating as a plain text")
            return
        # Save header & footer (remove trailing new lines)
        self._header = re.sub("\n\n$", "\n", matched.groups()[0])
        if self._header:
            log.debug(u"Parsed header:\n{0}".format(self._header))
        self._footer = re.sub("^\n", "", matched.groups()[2])
        if self._footer:
            log.debug(u"Parsed footer:\n{0}".format(self._footer))
        # Split the content on the section names
        section = re.compile(r"\n\[([^\]]+)\][ \t]*\n", re.MULTILINE)
        parts = section.split(matched.groups()[1])
        # Detect the version
        try:
            self.version(int(re.search(
                r"version (\d+)", parts[0]).groups()[0]))
            log.debug("Detected StructuredField version {0}".format(
                    self.version()))
        except AttributeError:
            log.error(parts[0])
            raise StructuredFieldError(
                    "Unable to detect StructuredField version")
        # Convert to dictionary, remove escapes and save the order
        keys = parts[1::2]
        escape = re.compile(r"^\[structured-field-escape\]", re.MULTILINE)
        values = [escape.sub("", value) for value in parts[2::2]]
        for key, value in zip(keys, values):
            self.set(key, value)
        log.debug(u"Parsed sections:\n{0}".format(
            pprint.pformat(self._sections)))

    def _save_version_zero(self):
        """ Save version 0 format """
        result = []
        if self._header:
            result.append(self._header)
        for section, content in self.iterate():
            result.append(u"[{0}]\n{1}".format(section, content))
        if self:
            result.append(u"[end]\n")
        if self._footer:
            result.append(self._footer)
        return "\n".join(result)

    def _save(self):
        """ Save version 1+ format """
        result = []
        # Regular expression for escaping section-like lines
        escape = re.compile(r"^(\[.+\])$", re.MULTILINE)
        # Header
        if self._header:
            result.append(self._header)
        # Sections
        if self:
            result.append(
                    u"[structured-field-start]\n"
                    u"This is StructuredField version {0}. "
                    u"Please, edit with care.\n".format(self._version))
            for section, content in self.iterate():
                result.append(u"[{0}]\n{1}".format(section,
                        escape.sub("[structured-field-escape]\\1", content)))
            result.append(u"[structured-field-end]\n")
        # Footer
        if self._footer:
            result.append(self._footer)
        return "\n".join(result)

    def _read_section(self, content):
        """ Parse config section and return ordered dictionary """
        dictionary = OrderedDict()
        for line in content.split("\n"):
            # Remove comments and skip empty lines
            line = re.sub("#.*", "", line)
            if re.match(r"^\s*$", line):
                continue
            # Parse key and value
            matched = re.search("([^=]+)=(.*)", line)
            if not matched:
                raise StructuredFieldError(
                    "Invalid key/value line: {0}".format(line))
            key = matched.groups()[0].strip()
            value = matched.groups()[1].strip()
            # Handle multiple values if enabled
            if key in dictionary and self._multi:
                if isinstance(dictionary[key], list):
                    dictionary[key].append(value)
                else:
                    dictionary[key] = [dictionary[key], value]
            else:
                dictionary[key] = value
        return dictionary

    def _write_section(self, dictionary):
        """ Convert dictionary into a config section format """
        section = ""
        for key in dictionary:
            if isinstance(dictionary[key], list):
                for value in dictionary[key]:
                    section += "{0} = {1}\n".format(key, value)
            else:
                section += "{0} = {1}\n".format(key, dictionary[key])
        return section

    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    #  StructuredField Methods
    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    def iterate(self):
        """ Return (section, content) tuples for all sections """
        for section in self:
            yield section, self._sections[section]

    def version(self, version=None):
        """ Get or set the StructuredField version """
        if version is not None:
            if version in [0, 1]:
                self._version = version
            else:
                raise StructuredFieldError(
                        "Bad StructuredField version: {0}".format(version))
        return self._version

    def load(self, text, version=None):
        """ Load the StructuredField from a string """
        if version is not None:
            self.version(version)
        # Make sure we got a text, convert to unicode if necessary
        try:
            if not isinstance(text, basestring):
                raise StructuredFieldError(
                        "Invalid StructuredField, expecting string or unicode")
            if not isinstance(text, unicode):
                text = text.decode("utf8")
        except NameError:
            if not isinstance(text, str):
                raise StructuredFieldError(
                        "Invalid StructuredField, expecting string")
        # Remove possible carriage returns
        text = re.sub("\r\n", "\n", text)
        # Make sure the text has a new line at the end
        if text and text[-1] != "\n":
            text += "\n"
        log.debug(u"Parsing StructuredField\n{0}".format(text))
        # Parse respective format version
        if self._version == 0:
            self._load_version_zero(text)
        else:
            self._load(text)

    def save(self):
        """ Convert the StructuredField into a string """
        if self.version() == 0:
            return self._save_version_zero()
        else:
            return self._save()

    def header(self, content=None):
        """ Get or set the header content """
        if content is not None:
            self._header = content
        return self._header

    def footer(self, content=None):
        """ Get or set the footer content """
        if content is not None:
            self._footer = content
        return self._footer

    def sections(self):
        """ Get the list of available sections """
        return self._order

    def get(self, section, item=None):
        """ Return content of given section or section item """
        try:
            content = self._sections[section]
        except KeyError:
            raise StructuredFieldError(
                    "Section [{0}] not found".format(ascii(section)))
        # Return the whole section content
        if item is None:
            return content
        # Return only selected item from the section
        try:
            return self._read_section(content)[item]
        except KeyError:
            raise StructuredFieldError(
                    "Unable to read '{0}' from section '{1}'".format(
                    ascii(item), ascii(section)))

    def set(self, section, content, item=None):
        """ Update content of given section or section item """
        # Convert to string if necessary, keep lists untouched
        if not isinstance(content, list):
            try:
                if not isinstance(content, basestring):
                    content = unicode(content)
                elif not isinstance(content, unicode):
                    content = content.decode("utf8")
            except:
                if not isinstance(content, str):
                    content = str(content)
        # Set the whole section content
        if item is None:
            # Add new line if missing
            if content and content[-1] != "\n":
                content += "\n"
            self._sections[section] = content
        # Set only selected item from the section
        else:
            try:
                current = self._sections[section]
            except KeyError:
                current = ""
            dictionary = self._read_section(current)
            dictionary[item] = content
            self._sections[section] = self._write_section(dictionary)
        # Remember the order when adding a new section
        if section not in self._order:
            self._order.append(section)

    def remove(self, section, item=None):
        """ Remove given section or section item """
        # Remove the whole section
        if item is None:
            try:
                del self._sections[section]
                del self._order[self._order.index(section)]
            except KeyError:
                raise StructuredFieldError(
                        "Section [{0}] not found".format(ascii(section)))
        # Remove only selected item from the section
        else:
            try:
                dictionary = self._read_section(self._sections[section])
                del(dictionary[item])
            except KeyError:
                raise StructuredFieldError(
                        "Unable to remove '{0}' from section '{1}'".format(
                        ascii(item), ascii(section)))
            self._sections[section] = self._write_section(dictionary)
