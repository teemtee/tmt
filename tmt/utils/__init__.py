""" Test Metadata Utilities """

import contextlib
import copy
import dataclasses
import datetime
import enum
import functools
import importlib.resources
import inspect
import io
import json
import os
import pathlib
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import textwrap
import time
import traceback
import unicodedata
import urllib.parse
from collections import Counter, OrderedDict
from collections.abc import Iterable, Iterator, Sequence
from contextlib import suppress
from math import ceil
from re import Pattern
from threading import Thread
from types import ModuleType
from typing import (
    IO,
    TYPE_CHECKING,
    Any,
    Callable,
    Generic,
    Literal,
    Optional,
    TypeVar,
    Union,
    cast,
    overload,
    )

import click
import docutils.frontend
import docutils.nodes
import docutils.parsers.rst
import docutils.utils
import fmf
import fmf.utils
import jsonschema
import requests
import requests.adapters
import urllib3
import urllib3.exceptions
import urllib3.util.retry
from click import echo, style, wrap_text
from ruamel.yaml import YAML, scalarstring
from ruamel.yaml.comments import CommentedMap
from ruamel.yaml.parser import ParserError
from ruamel.yaml.representer import Representer

import tmt.log
from tmt._compat.pathlib import Path
from tmt.log import LoggableValue, Logger

if TYPE_CHECKING:
    from _typeshed import DataclassInstance

    import tmt.base
    import tmt.cli
    import tmt.options
    import tmt.steps
    from tmt._compat.typing import Self, TypeAlias


def configure_optional_constant(default: Optional[int], envvar: str) -> Optional[int]:
    """
    Deduce the actual value of a global constant which may be left unset.

    :param default: the default value of the constant.
    :param envvar: name of the optional environment variable which would
        override the default value.
    :returns: value extracted from the environment variable, or the
        given default value if the variable did not exist.
    """

    if envvar not in os.environ:
        return default

    try:
        return int(os.environ[envvar])

    except ValueError as exc:
        raise tmt.utils.GeneralError(
            f"Could not parse '{envvar}={os.environ[envvar]}' as integer.") from exc


def configure_constant(default: int, envvar: str) -> int:
    """
    Deduce the actual value of global constant.

    :param default: the default value of the constant.
    :param envvar: name of the optional environment variable which would
        override the default value.
    :returns: value extracted from the environment variable, or the
        given default value if the variable did not exist.
    """

    try:
        return int(os.environ.get(envvar, default))

    except ValueError as exc:
        raise tmt.utils.GeneralError(
            f"Could not parse '{envvar}={os.environ[envvar]}' as integer.") from exc


log = fmf.utils.Logging('tmt').logger


# Default workdir root and max
WORKDIR_ROOT = Path('/var/tmp/tmt')  # noqa: S108 insecure usage of temporary dir
WORKDIR_MAX = 1000

# Maximum number of lines of stdout/stderr to show upon errors
OUTPUT_LINES = 100

#: How wide should the output be at maximum.
#: This is the default value tmt would use unless told otherwise.
DEFAULT_OUTPUT_WIDTH: int = 79

#: How wide should the output be at maximum.
#: This is the effective value, combining the default and optional envvar,
#: ``TMT_OUTPUT_WIDTH``.
OUTPUT_WIDTH: int = configure_constant(DEFAULT_OUTPUT_WIDTH, 'TMT_OUTPUT_WIDTH')

# Hierarchy indent
INDENT = 4

# Default name and order for step plugins
DEFAULT_NAME = 'default'
DEFAULT_PLUGIN_ORDER = 50
DEFAULT_PLUGIN_ORDER_MULTIHOST = 10
DEFAULT_PLUGIN_ORDER_REQUIRES = 70
DEFAULT_PLUGIN_ORDER_RECOMMENDS = 75

# Config directory
CONFIG_DIR = Path('~/.config/tmt')

# Special process return codes


class ProcessExitCodes(enum.IntEnum):
    #: Successful run.
    SUCCESS = 0
    #: Unsuccessful run.
    FAILURE = 1

    #: tmt pidfile lock operation failed.
    TEST_PIDFILE_LOCK_FAILED = 122
    #: tmt pidfile unlock operation failed.
    TEST_PIDFILE_UNLOCK_FAILED = 123

    #: Command was terminated because of a timeout.
    TIMEOUT = 124

    #: Permission denied (or) unable to execute.
    PERMISSION_DENIED = 126
    #: Command not found, or PATH error.
    NOT_FOUND = 127

    # (128 + N) where N is a signal send to the process
    #: Terminated by either ``Ctrl+C`` combo or ``SIGINT`` signal.
    SIGINT = 130
    #: Terminated by a ``SIGTERM`` signal.
    SIGTERM = 143

    @classmethod
    def is_pidfile(cls, exit_code: Optional[int]) -> bool:
        return exit_code in (ProcessExitCodes.TEST_PIDFILE_LOCK_FAILED,
                             ProcessExitCodes.TEST_PIDFILE_UNLOCK_FAILED)

    @classmethod
    def format(cls, exit_code: int) -> Optional[str]:
        """ Format a given exit code for nicer logging """

        member = cls._value2member_map_.get(exit_code)

        if member is None:
            return 'unrecognized'

        if member.name.startswith('SIG'):
            return member.name

        return member.name.lower().replace('_', ' ')


# Default select.select(timeout) in seconds
DEFAULT_SELECT_TIMEOUT = 5

# Default shell and options to be set for all shell scripts
DEFAULT_SHELL = "/bin/bash"
SHELL_OPTIONS = 'set -eo pipefail'

# Defaults for HTTP/HTTPS retries and timeouts (see `retry_session()`).
DEFAULT_RETRY_SESSION_RETRIES: int = 3
DEFAULT_RETRY_SESSION_BACKOFF_FACTOR: float = 0.1

# Defaults for HTTP/HTTPS retries for getting environment file
# Retry with exponential backoff, maximum duration ~511 seconds
ENVFILE_RETRY_SESSION_RETRIES: int = 10
ENVFILE_RETRY_SESSION_BACKOFF_FACTOR: float = 1

# Default for wait()-related options
DEFAULT_WAIT_TICK: float = 30.0
DEFAULT_WAIT_TICK_INCREASE: float = 1.0

# Defaults for GIT attempts and interval
DEFAULT_GIT_CLONE_TIMEOUT: Optional[int] = None
GIT_CLONE_TIMEOUT: Optional[int] = configure_optional_constant(
    DEFAULT_GIT_CLONE_TIMEOUT, 'TMT_GIT_CLONE_TIMEOUT')

DEFAULT_GIT_CLONE_ATTEMPTS: int = 3
GIT_CLONE_ATTEMPTS: int = configure_constant(DEFAULT_GIT_CLONE_ATTEMPTS, 'TMT_GIT_CLONE_ATTEMPTS')

DEFAULT_GIT_CLONE_INTERVAL: int = 10
GIT_CLONE_INTERVAL: int = configure_constant(DEFAULT_GIT_CLONE_INTERVAL, 'TMT_GIT_CLONE_INTERVAL')

# A stand-in variable for generic use.
T = TypeVar('T')


def effective_workdir_root() -> Path:
    """
    Find out what the actual workdir root is.

    If ``TMT_WORKDIR_ROOT`` variable is set, it is used as the workdir root.
    Otherwise, the default of :py:data:`WORKDIR_ROOT` is used.
    """

    if 'TMT_WORKDIR_ROOT' in os.environ:
        return Path(os.environ['TMT_WORKDIR_ROOT'])

    return WORKDIR_ROOT


class FmfContext(dict[str, list[str]]):
    """
    Represents an fmf context.

    See https://tmt.readthedocs.io/en/latest/spec/context.html
    and https://fmf.readthedocs.io/en/latest/context.html.
    """

    def __init__(self, data: Optional[dict[str, list[str]]] = None) -> None:
        super().__init__(data or {})

    @classmethod
    def _normalize_command_line(cls, spec: list[str], logger: tmt.log.Logger) -> 'FmfContext':
        """
        Normalize command line fmf context specification.

        .. code-block:: ini

            -c distro=fedora-33 -> {'distro': ['fedora']}
            -c arch=x86_64,ppc64 -> {'arch': ['x86_64', 'ppc64']}
        """

        return FmfContext({
            key: value.split(',')
            for key, value in Environment.from_sequence(spec, logger).items()})

    @classmethod
    def _normalize_fmf(
            cls,
            spec: dict[str, Union[str, list[str]]],
            logger: tmt.log.Logger) -> 'FmfContext':
        """
        Normalize fmf context specification from fmf node.

        .. code-block:: yaml

            context:
              distro: fedora-33
              arch:
                - x86_64
                - ppc64
        """

        normalized: FmfContext = FmfContext()

        for dimension, values in spec.items():
            if isinstance(values, list):
                normalized[str(dimension)] = [str(v) for v in values]
            else:
                normalized[str(dimension)] = [str(values)]

        return normalized

    @classmethod
    def from_spec(cls, key_address: str, spec: Any, logger: tmt.log.Logger) -> 'FmfContext':
        """
        Convert from a specification file or from a CLI option.

        See https://tmt.readthedocs.io/en/stable/spec/context.html for details on context.
        """

        if spec is None:
            return FmfContext()

        if isinstance(spec, tuple):
            return cls._normalize_command_line(list(spec), logger)

        if isinstance(spec, list):
            return cls._normalize_command_line(spec, logger)

        if isinstance(spec, dict):
            return cls._normalize_fmf(spec, logger)

        raise NormalizationError(key_address, spec, 'a list of strings or a dictionary')

    def to_spec(self) -> dict[str, Any]:
        """ Convert to a form suitable for saving in a specification file """

        return dict(self)


#: A type of environment variable name.
EnvVarName: 'TypeAlias' = str

# This one is not an alias: a full-fledged class makes type linters
# enforce strict instantiation of objects rather than accepting
# strings where `EnvVarValue` is expected.


class EnvVarValue(str):
    """ A type of environment variable value """

    def __new__(cls, raw_value: Any) -> 'EnvVarValue':
        if isinstance(raw_value, str):
            return str.__new__(cls, raw_value)

        if isinstance(raw_value, Path):
            return str.__new__(cls, str(raw_value))

        raise GeneralError(
            f"Only strings and paths can be environment variables, '{type(raw_value)}' found.")


class Environment(dict[str, EnvVarValue]):
    """
    Represents a set of environment variables.

    See https://tmt.readthedocs.io/en/latest/spec/tests.html#environment,
    https://tmt.readthedocs.io/en/latest/spec/plans.html#environment and
    https://tmt.readthedocs.io/en/latest/spec/plans.html#environment-file.
    """

    def __init__(self, data: Optional[dict[EnvVarName, EnvVarValue]] = None) -> None:
        super().__init__(data or {})

    @classmethod
    def from_dotenv(cls, content: str) -> 'Environment':
        """
        Construct environment from a ``.env`` format.

        :param content: string containing variables defined in the "dotenv"
            format, https://hexdocs.pm/dotenvy/dotenv-file-format.html.
        """

        environment = Environment()

        try:
            for line in shlex.split(content, comments=True):
                key, value = line.split("=", maxsplit=1)

                environment[key] = EnvVarValue(value)

        except Exception as exc:
            raise GeneralError("Failed to extract variables from 'dotenv' format.") from exc

        return environment

    @classmethod
    def from_yaml(cls, content: str) -> 'Environment':
        """
        Construct environment from a YAML format.

        :param content: string containing variables defined in a YAML
            dictionary, i.e. ``key: value`` entries.
        """

        try:
            yaml = YAML(typ="safe").load(content)

        except Exception as exc:
            raise GeneralError('Failed to extract variables from YAML format.') from exc

        # Handle empty file as an empty environment
        if yaml is None:
            return Environment()

        if not isinstance(yaml, dict):
            raise GeneralError(
                'Failed to extract variables from YAML format, '
                'YAML defining variables must be a dictionary.')

        if any(isinstance(v, (dict, list)) for v in yaml.values()):
            raise GeneralError(
                'Failed to extract variables from YAML format, '
                'only primitive types are accepted as values.')

        return Environment({
            key: EnvVarValue(str(value))
            for key, value in yaml.items()
            })

    @classmethod
    def from_yaml_file(
            cls,
            filepath: Path,
            logger: tmt.log.Logger) -> 'Environment':
        """
        Construct environment from a YAML file.

        File is expected to contain variables in a YAML dictionary, i.e.
        ``key: value`` entries. Only primitive types - strings, numbers,
        booleans - are allowed as values.

        :param path: path to the file with variables.
        :param logger: used for logging.
        """

        try:
            content = filepath.read_text()

        except Exception as exc:
            raise GeneralError(f"Failed to extract variables from YAML file '{filepath}'.") \
                from exc

        return cls.from_yaml(content)

    @classmethod
    def from_sequence(
            cls,
            variables: Union[str, list[str]],
            logger: tmt.log.Logger) -> 'Environment':
        """
        Construct environment from a sequence of variables.

        Variables may be specified in two ways:

        * ``NAME=VALUE`` pairs, or
        * ``@foo.yaml`` signaling variables to be read from a file.

        If a "variable" starts with ``@``, it is treated as a path to
        a YAML file that contains key/value pairs which are then
        transparently loaded and added to the final environment.

        :param variables: string or a sequence of strings containing
            variables. The acceptable formats are:

            * ``'X=1'``
            * ``'X=1 Y=2 Z=3'``
            * ``['X=1', 'Y=2', 'Z=3']``
            * ``['X=1 Y=2 Z=3', 'A=1 B=2 C=3']``
            * ``'TXT="Some text with spaces in it"'``
            * ``@foo.yaml``
            * ``@../../bar.yaml``
        """

        if not isinstance(variables, (list, tuple)):
            variables = [variables]

        result = Environment()

        for variable in variables:
            if variable is None:
                continue
            for var in shlex.split(variable):
                if var.startswith('@'):
                    if not var[1:]:
                        raise GeneralError(
                            f"Invalid variable file specification '{var}'.")

                    filepath = Path(var[1:])

                    environment = cls.from_yaml_file(filepath, logger)

                    if not environment:
                        logger.warning(f"Empty environment file '{filepath}'.")

                    result.update(environment)

                else:
                    matched = re.match("([^=]+)=(.*)", var)
                    if not matched:
                        raise GeneralError(f"Invalid variable specification '{var}'.")
                    name, value = matched.groups()
                    result[name] = EnvVarValue(value)

        return result

    @classmethod
    def from_file(
            cls,
            *,
            filename: str,
            root: Optional[Path] = None,
            logger: tmt.log.Logger) -> 'Environment':
        """
        Construct environment from a file.

        YAML files - recognized by ``.yaml`` or ``.yml`` suffixes - or
        ``.env``-like files are supported.

        .. code-block:: bash
           :caption: dotenv file example

           A=B
           C=D

        .. code-block:: yaml
           :caption: YAML file example

           A: B
           C: D

        .. note::

            For loading environment variables from multiple files, see
            :py:meth:`Environment.from_files`.
        """

        root = root or Path.cwd()
        filename = filename.strip()
        environment_filepath: Optional[Path] = None

        # Fetch a remote file
        if filename.startswith("http"):
            # Create retry session for longer retries, see #1229
            session = retry_session.create(
                retries=ENVFILE_RETRY_SESSION_RETRIES,
                backoff_factor=ENVFILE_RETRY_SESSION_BACKOFF_FACTOR,
                allowed_methods=('GET',),
                status_forcelist=(
                    429,  # Too Many Requests
                    500,  # Internal Server Error
                    502,  # Bad Gateway
                    503,  # Service Unavailable
                    504   # Gateway Timeout
                    ),
                )
            try:
                response = session.get(filename)
                response.raise_for_status()
                content = response.text
            except requests.RequestException as error:
                raise GeneralError(f"Failed to extract variables from URL '{filename}'.") \
                    from error

        # Read a local file
        else:
            # Ensure we don't escape from the metadata tree root

            root = root.resolve()
            environment_filepath = root.joinpath(filename).resolve()

            if not environment_filepath.is_relative_to(root):
                raise GeneralError(
                    f"Failed to extract variables from file '{environment_filepath}' as it "
                    f"lies outside the metadata tree root '{root}'.")
            if not environment_filepath.is_file():
                raise GeneralError(f"File '{environment_filepath}' doesn't exist.")

            content = environment_filepath.read_text()

        # Parse yaml file
        if os.path.splitext(filename)[1].lower() in ('.yaml', '.yml'):
            environment = cls.from_yaml(content)

        else:
            environment = cls.from_dotenv(content)

        if not environment:
            logger.warning(f"Empty environment file '{filename}'.")

            return Environment()

        return environment

    @classmethod
    def from_files(
            cls,
            *,
            filenames: Iterable[str],
            root: Optional[Path] = None,
            logger: tmt.log.Logger) -> 'Environment':
        """
        Read environment variables from the given list of files.

        Files should be in YAML format (``.yaml`` or ``.yml`` suffixes), or in dotenv format.

        .. code-block:: bash
           :caption: dotenv file example

           A=B
           C=D

        .. code-block:: yaml
           :caption: YAML file example

           A: B
           C: D

        Path to each file should be relative to the metadata tree root.

        .. note::

            For loading environment variables from a single file, see
            :py:meth:`Environment.from_file`, which is a method called
            for each file, accumulating data from all input files.
        """

        root = root or Path.cwd()

        result = Environment()

        for filename in filenames:
            result.update(cls.from_file(filename=filename, root=root, logger=logger))

        return result

    @classmethod
    def from_inputs(
            cls,
            *,
            raw_fmf_environment: Any = None,
            raw_fmf_environment_files: Any = None,
            raw_cli_environment: Any = None,
            raw_cli_environment_files: Any = None,
            file_root: Optional[Path] = None,
            key_address: Optional[str] = None,
            logger: tmt.log.Logger) -> 'Environment':
        """
        Extract environment variables from various sources.

        Combines various raw sources into a set of environment variables. Calls
        necessary functions to process environment files, dictionaries and CLI
        inputs.

        All inputs are optional, and there is a clear order of preference, which is,
        from the most preferred:

        * ``--environment`` CLI option (``raw_cli_environment``)
        * ``--environment-file`` CLI option (``raw_cli_environment_files``)
        * ``environment`` fmf key (``raw_fmf_environment``)
        * ``environment-file`` fmf key (``raw_fmf_environment_files``)

        :param raw_fmf_environment: content of ``environment`` fmf key. ``None``
            and a dictionary are accepted.
        :param raw_fmf_environment_files: content of ``environment-file`` fmf key.
            ``None`` and a list of paths are accepted.
        :param raw_cli_environment: content of ``--environment`` CLI option.
            ``None``, a tuple or a list are accepted.
        :param raw_cli_environment_files: content of `--environment-file`` CLI
            option. ``None``, a tuple or a list are accepted.
        :raises NormalizationError: when an input is of a type which is not allowed
            for that particular source.
        """

        key_address_prefix = f'{key_address}:' if key_address else ''

        from_fmf_files = Environment()
        from_fmf_dict = Environment()
        from_cli_files = Environment()
        from_cli = Environment()

        if raw_fmf_environment_files is None:
            pass
        elif isinstance(raw_fmf_environment_files, list):
            from_fmf_files = cls.from_files(
                filenames=raw_fmf_environment_files,
                root=file_root,
                logger=logger)
        else:
            raise NormalizationError(
                f'{key_address_prefix}environment-file',
                raw_fmf_environment_files,
                'unset or a list of paths')

        if raw_fmf_environment is None:
            pass
        elif isinstance(raw_fmf_environment, dict):
            from_fmf_dict = Environment.from_dict(raw_fmf_environment)
        else:
            raise NormalizationError(
                f'{key_address_prefix}environment', raw_fmf_environment, 'unset or a dictionary')

        if raw_cli_environment_files is None:
            pass
        elif isinstance(raw_cli_environment_files, (list, tuple)):
            from_cli_files = Environment.from_files(
                filenames=raw_cli_environment_files,
                root=file_root,
                logger=logger)
        else:
            raise NormalizationError(
                'environment-file', raw_cli_environment_files, 'unset or a list of paths')

        if raw_cli_environment is None:
            pass
        elif isinstance(raw_cli_environment, (list, tuple)):
            from_cli = Environment.from_sequence(list(raw_cli_environment), logger)
        else:
            raise NormalizationError(
                'environment', raw_cli_environment, 'unset or a list of key/value pairs')

        # Combine all sources into one mapping, honor the order in which they override
        # other sources.
        return Environment({
            **from_fmf_files,
            **from_fmf_dict,
            **from_cli_files,
            **from_cli
            })

    @classmethod
    def from_dict(cls, data: Optional[dict[str, Any]] = None) -> 'Environment':
        """ Create environment variables from a dictionary """
        if not data:
            return Environment()

        return Environment({
            str(key): EnvVarValue(str(value))
            for key, value in data.items()
            })

    @classmethod
    def from_environ(cls) -> 'Environment':
        """ Extract environment variables from the live environment """

        return Environment({
            key: EnvVarValue(value) for key, value in os.environ.items()
            })

    @classmethod
    def from_fmf_context(cls, fmf_context: FmfContext) -> 'Environment':
        """ Create environment variables from an fmf context """

        return Environment({
            key: EnvVarValue(','.join(value))
            for key, value in fmf_context.items()
            })

    @classmethod
    def from_fmf_spec(cls, data: Optional[dict[str, Any]] = None) -> 'Environment':
        """ Create environment from an fmf specification """

        if not data:
            return Environment()

        return Environment({
            key: EnvVarValue(str(value)) for key, value in data.items()
            })

    def to_fmf_spec(self) -> dict[str, str]:
        """ Convert to an fmf specification """

        return {
            key: str(value) for key, value in self.items()
            }

    def to_popen(self) -> dict[str, str]:
        """ Convert to a form accepted by :py:class:`subprocess.Popen` """

        return self.to_environ()

    def to_environ(self) -> dict[str, str]:
        """ Convert to a form compatible with :py:attr:`os.environ` """

        return {
            key: str(value) for key, value in self.items()
            }

    def copy(self) -> 'Environment':
        return Environment(self)

    @classmethod
    def normalize(
            cls,
            key_address: str,
            value: Any,
            logger: tmt.log.Logger) -> 'Environment':
        """ Normalize value of ``environment`` key """

        # Note: this normalization callback is an exception, it does not
        # bother with CLI input. Environment handling is complex, and CLI
        # options have their special handling. The `environment` as an
        # fmf key does not really have a 1:1 CLI option, the corresponding
        # options are always "special".
        if value is None:
            return cls()

        if isinstance(value, dict):
            return cls({
                k: EnvVarValue(str(v)) for k, v in value.items()
                })

        raise NormalizationError(key_address, value, 'unset or a dictionary')

    @contextlib.contextmanager
    def as_environ(self) -> Iterator[None]:
        """
        A context manager replacing :py:attr:`os.environ` with this environment.

        When left, the original content of ``os.environ`` is restored.

        .. warning::

            This method is not thread safe! Beware of using it in code
            that runs in multiple threads, e.g. from
            provision/prepare/execute/finish phases.
        """

        environ_backup = os.environ.copy()
        os.environ.clear()
        os.environ.update(self)
        try:
            yield
        finally:
            os.environ.clear()
            os.environ.update(environ_backup)


# Workdir argument type, can be True, a string, a path or None
WorkdirArgumentType = Union[Literal[True], Path, None]

# Workdir type, can be None or a path
WorkdirType = Optional[Path]

# Option to skip to initialize work tree in plan
PLAN_SKIP_WORKTREE_INIT = 'plan_skip_worktree_init'

# List of schemas that need to be ignored in a plan
PLAN_SCHEMA_IGNORED_IDS: list[str] = [
    '/schemas/provision/hardware',
    '/schemas/provision/kickstart'
    ]


class Config:
    """ User configuration """

    def __init__(self) -> None:
        """ Initialize config directory path """
        raw_path = os.getenv('TMT_CONFIG_DIR', None)
        self.path = (Path(raw_path) if raw_path else CONFIG_DIR).expanduser()

        try:
            self.path.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise GeneralError(
                f"Failed to create config '{self.path}'.\n{error}")

    @property
    def _last_run_symlink(self) -> Path:
        return self.path / 'last-run'

    @property
    def last_run(self) -> Optional[Path]:
        """ Get the last run workdir path """
        return self._last_run_symlink.resolve() if self._last_run_symlink.is_symlink() else None

    @last_run.setter
    def last_run(self, workdir: Path) -> None:
        """ Set the last run to the given run workdir """

        with suppress(OSError):
            self._last_run_symlink.unlink()

        try:
            self._last_run_symlink.symlink_to(workdir)
        except FileExistsError:
            # Race when tmt runs in parallel
            log.warning(
                f"Unable to mark '{workdir}' as the last run, "
                "'tmt run --last' might not pick the right run directory.")
        except OSError as error:
            raise GeneralError(
                f"Unable to save last run '{self.path}'.\n{error}")

    @functools.cached_property
    def fmf_tree(self) -> fmf.Tree:
        """ Return the configuration tree """
        try:
            return fmf.Tree(self.path)
        except fmf.utils.RootError as error:
            raise MetadataError(f"Config tree not found in '{self.path}'.") from error


# TODO: `StreamLogger` is a dedicated thread following given stream, passing their content to
# tmt's logging methods. Thread is needed because of some amount of blocking involved in the
# process, but it has a side effect of `NO_COLOR` envvar being ignored. When tmt spots `NO_COLOR`
# envvar, it flips a `color` flag in its Click context. But since contexts are thread-local,
# thread powering `StreamLogger` is not aware of this change, and all Click methods it calls
# - namely `echo` and `style` in depths of logging code - would still apply colors depending on
# tty setup.
#
# Passing Click context from the main thread to `StreamLogger` instances to replace their context
# is one way to solve it, another might be logging being more explicit and transparent, e.g. with
# https://github.com/teemtee/tmt/issues/1565.
class StreamLogger(Thread):
    """
    Reading pipes of running process in threads.

    Code based on:
    https://github.com/packit/packit/blob/main/packit/utils/logging.py#L10
    """

    def __init__(
            self,
            log_header: str,
            *,
            stream: Optional[IO[bytes]] = None,
            logger: Optional[tmt.log.LoggingFunction] = None,
            click_context: Optional[click.Context] = None,
            stream_output: bool = True) -> None:
        super().__init__(daemon=True)

        self.stream = stream
        self.output: list[str] = []
        self.log_header = log_header
        self.logger = logger
        self.click_context = click_context
        self.stream_output = stream_output

    def run(self) -> None:
        if self.stream is None:
            return

        if self.logger is None:
            return

        if self.click_context is not None:
            click.globals.push_context(self.click_context)

        for _line in self.stream:
            line = _line.decode('utf-8', errors='replace')
            if self.stream_output and line != '':
                self.logger(
                    self.log_header,
                    line.rstrip('\n'),
                    'yellow',
                    level=3)
            self.output.append(line)

    def get_output(self) -> Optional[str]:
        return "".join(self.output)


class UnusedStreamLogger(StreamLogger):
    """
    Special variant of :py:class:`StreamLogger` that records no data.

    It is designed to make the implementation of merged streams easier in
    :py:meth:`Command.run`. Instance of this class is created to log ``stderr``
    when, in fact, ``stderr`` is merged into ``stdout``. This class returns
    values compatible with :py:class:`CommandOutput` notion of "no output".
    """

    def __init__(self, log_header: str) -> None:
        super().__init__(log_header)

    def run(self) -> None:
        pass

    def get_output(self) -> Optional[str]:
        return None


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#  Common
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

CommonDerivedType = TypeVar('CommonDerivedType', bound='Common')

#: A single element of command-line.
_CommandElement = str
#: A single element of raw command line in its ``list`` form.
RawCommandElement = Union[str, Path]
#: A raw command line form, a list of elements.
RawCommand = list[RawCommandElement]

#: Type of a callable to be called by :py:meth:`Command.run` after starting the
#: child process.
OnProcessStartCallback = Callable[
    ['Command', subprocess.Popen[bytes], tmt.log.Logger],
    None
    ]


@dataclasses.dataclass(frozen=True)
class CommandOutput:
    stdout: Optional[str]
    stderr: Optional[str]


class ShellScript:
    """ A shell script, a free-form blob of text understood by a shell. """

    def __init__(self, script: str) -> None:
        """
        A shell script, a free-form blob of text understood by a shell.

        :param script: the actual script to be encapsulated by ``ShellScript``
            wrapper.
        """

        self._script = textwrap.dedent(script)

    def __str__(self) -> str:
        return self._script

    def __add__(self, other: 'ShellScript') -> 'ShellScript':
        if not other:
            return self

        return ShellScript.from_scripts([self, other])

    def __and__(self, other: 'ShellScript') -> 'ShellScript':
        if not other:
            return self

        return ShellScript(f'{self} && {other}')

    def __or__(self, other: 'ShellScript') -> 'ShellScript':
        if not other:
            return self

        return ShellScript(f'{self} || {other}')

    def __bool__(self) -> bool:
        return bool(self._script)

    @classmethod
    def from_scripts(cls, scripts: list['ShellScript']) -> 'ShellScript':
        """
        Create a single script from many shorter ones.

        Scripts are merged into a single ``ShellScript`` instance, joined
        together with ``;`` character.

        :param scripts: scripts to merge into one.
        """

        return ShellScript('; '.join(script._script for script in scripts if bool(script)))

    def to_element(self) -> _CommandElement:
        """ Convert a shell script to a command element """

        return self._script

    def to_shell_command(self) -> 'Command':
        """
        Convert a shell script into a shell-driven command.

        Turns a shell script into a full-fledged command one might pass to the OS.
        Basically what would ``run(script, shell=True)`` do.
        """

        return Command(DEFAULT_SHELL, '-c', self.to_element())


class Command:
    """ A command with its arguments. """

    def __init__(self, *elements: RawCommandElement) -> None:
        self._command = [str(element) for element in elements]

    def __str__(self) -> str:
        return self.to_element()

    def __add__(self, other: Union['Command', RawCommand, list[str]]) -> 'Command':
        if isinstance(other, Command):
            return Command(*self._command, *other._command)

        return Command(*self._command, *other)

    def to_element(self) -> _CommandElement:
        """
        Convert a command to a shell command line element.

        Use when a command or just a list of command options should become a part
        of another command. Common examples of such "higher level" commands
        would be would be ``rsync -e`` or ``ansible-playbook --ssh-common-args``.
        """

        return ' '.join(shlex.quote(s) for s in self._command)

    def to_script(self) -> ShellScript:
        """
        Convert a command to a shell script.

        Use when a command is supposed to become a part of a shell script.
        """

        return ShellScript(' '.join(shlex.quote(s) for s in self._command))

    def to_popen(self) -> list[str]:
        """ Convert a command to form accepted by :py:mod:`subprocess.Popen` """

        return list(self._command)

    def run(
            self,
            *,
            cwd: Optional[Path],
            shell: bool = False,
            env: Optional[Environment] = None,
            dry: bool = False,
            join: bool = False,
            interactive: bool = False,
            timeout: Optional[int] = None,
            on_process_start: Optional[OnProcessStartCallback] = None,
            # Logging
            message: Optional[str] = None,
            friendly_command: Optional[str] = None,
            log: Optional[tmt.log.LoggingFunction] = None,
            silent: bool = False,
            stream_output: bool = True,
            caller: Optional['Common'] = None,
            logger: tmt.log.Logger) -> CommandOutput:
        """
        Run command, give message, handle errors.

        :param cwd: if set, command would be executed in the given directory,
            otherwise the current working directory is used.
        :param shell: if set, the command would be executed in a shell.
        :param env: environment variables to combine with the current environment
            before running the command.
        :param dry: if set, the command would not be actually executed.
        :param join: if set, stdout and stderr of the command would be merged into
            a single output text.
        :param interactive: if set, the command would be executed in an interactive
            manner, i.e. with stdout and stdout connected to terminal for live
            interaction with user.
        :param timeout: if set, command would be interrupted, if still running,
            after this many seconds.
        :param on_process_start: if set, this callable would be called after the
            command process started.
        :param message: if set, it would be logged for more friendly logging.
        :param friendly_command: if set, it would be logged instead of the
            command itself, to improve visibility of the command in logging output.
        :param log: a logging function to use for logging of command output. By
            default, ``logger.debug`` is used.
        :param silent: if set, logging of steps taken by this function would be
            reduced.
        :param stream_output: if set, command output would be streamed
            live into the log. When unset, the output would be logged
            only when the command fails.
        :param caller: optional "parent" of the command execution, used for better
            linked exceptions.
        :param logger: logger to use for logging.
        :returns: command output, bundled in a :py:class:`CommandOutput` tuple.
        """

        # A bit of logging - command, default message, error message for later...

        # First, if we were given a message, emit it.
        if message:
            logger.verbose(message, level=2)

        # For debugging, we want to save somewhere the actual command rather
        # than the provided "friendly". Emit the actual command to the debug
        # log, and the friendly one to the verbose/custom log
        logger.debug(f'Run command: {self!s}', level=2)

        # The friendly command version would be emitted only when we were not
        # asked to be quiet.
        if not silent and friendly_command:
            (log or logger.verbose)("cmd", friendly_command, color="yellow", level=2)

        # Nothing more to do in dry mode
        if dry:
            return CommandOutput(None, None)

        # Fail nicely if the working directory does not exist
        if cwd and not cwd.exists():
            raise GeneralError(f"The working directory '{cwd}' does not exist.")

        # For command output logging, use either the given logging callback, or
        # use the given logger & emit to debug log.
        output_logger = (log or logger.debug) if not silent else logger.debug

        # Prepare the environment: use the current process environment, but do
        # not modify it if caller wants something extra, make a copy.
        actual_env: Optional[Environment] = None

        # Do not modify current process environment
        if env is not None:
            actual_env = Environment.from_environ()
            actual_env.update(env)

        logger.debug('environment', actual_env, level=4)

        # Set special executable only when shell was requested
        executable = DEFAULT_SHELL if shell else None

        if interactive:
            def _spawn_process() -> subprocess.Popen[bytes]:
                return subprocess.Popen(
                    self.to_popen(),
                    cwd=cwd,
                    shell=shell,
                    env=actual_env.to_popen() if actual_env is not None else None,
                    # Disabling for now: When used together with the
                    # local provision this results into errors such as:
                    # 'cannot set terminal process group: Inappropriate
                    # ioctl for device' and 'no job control in this
                    # shell'. Let's investigate later why this happens.
                    # start_new_session=True,
                    stdin=None,
                    stdout=None,
                    stderr=None,
                    executable=executable)

        else:
            def _spawn_process() -> subprocess.Popen[bytes]:
                return subprocess.Popen(
                    self.to_popen(),
                    cwd=cwd,
                    shell=shell,
                    env=actual_env.to_popen() if actual_env is not None else None,
                    start_new_session=True,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT if join else subprocess.PIPE,
                    executable=executable)

        # Spawn the child process
        try:
            process = _spawn_process()

        except FileNotFoundError as exc:
            raise RunError(f"File '{exc.filename}' not found.", self, 127, caller=caller) from exc

        if on_process_start:
            on_process_start(self, process, logger)

        if not interactive:
            # Create and start stream loggers
            stdout_logger = StreamLogger(
                'out',
                stream=process.stdout,
                logger=output_logger,
                click_context=click.get_current_context(silent=True),
                stream_output=stream_output)

            if join:
                stderr_logger: StreamLogger = UnusedStreamLogger('err')

            else:
                stderr_logger = StreamLogger(
                    'err',
                    stream=process.stderr,
                    logger=output_logger,
                    click_context=click.get_current_context(silent=True),
                    stream_output=stream_output)

            stdout_logger.start()
            stderr_logger.start()

        # A bit of logging helpers for debugging duration behavior
        start_timestamp = time.monotonic()

        def _event_timestamp() -> str:
            return f'{time.monotonic() - start_timestamp:.4}'

        def log_event(msg: str) -> None:
            logger.debug(
                'Command event',
                f'{_event_timestamp()} {msg}',
                level=4,
                topic=tmt.log.Topic.COMMAND_EVENTS)

        log_event('waiting for process to finish')

        try:
            process.wait(timeout=timeout)

        except subprocess.TimeoutExpired:
            log_event(f'duration "{timeout}" exceeded')

            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            log_event('sent SIGKILL signal')

            process.wait()
            log_event('kill confirmed')

            process.returncode = ProcessExitCodes.TIMEOUT

        else:
            log_event('waiting for process completed')

        stdout: Optional[str]
        stderr: Optional[str]

        if interactive:
            log_event('stream readers not active')

            stdout, stderr = None, None

        else:
            log_event('waiting for stream readers')

            stdout_logger.join()
            log_event('stdout reader done')

            stderr_logger.join()
            log_event('stderr reader done')

            stdout, stderr = stdout_logger.get_output(), stderr_logger.get_output()

        logger.debug(
            f"Command returned '{process.returncode}' "
            f"({ProcessExitCodes.format(process.returncode)}).", level=3)

        # Handle the exit code, return output
        if process.returncode != ProcessExitCodes.SUCCESS:
            if not stream_output:
                if stdout is not None:
                    for line in stdout.splitlines():
                        output_logger('out', value=line, color='yellow', level=3)

                if stderr is not None:
                    for line in stderr.splitlines():
                        output_logger('err', value=line, color='yellow', level=3)

            raise RunError(
                f"Command '{friendly_command or str(self)}' returned {process.returncode}.",
                self,
                process.returncode,
                stdout=stdout,
                stderr=stderr,
                caller=caller)

        return CommandOutput(stdout, stderr)


_SANITIZE_NAME_PATTERN: Pattern[str] = re.compile(r'[^\w/-]+')
_SANITIZE_NAME_PATTERN_NO_SLASH: Pattern[str] = re.compile(r'[^\w-]+')


def sanitize_name(name: str, allow_slash: bool = True) -> str:
    """
    Create a safe variant of a name that does not contain special characters.

    Spaces and other special characters are removed to prevent problems with
    tools which do not expect them (e.g. in directory names).

    :param name: a name to sanitize.
    :param allow_slash: if set, even a slash character, ``/``, would be replaced.
    """

    pattern = _SANITIZE_NAME_PATTERN if allow_slash else _SANITIZE_NAME_PATTERN_NO_SLASH

    return pattern.sub('-', name).strip('-')


class _CommonBase:
    """
    A base class for **all** classes contributing to "common" tree of classes.

    All classes derived from :py:class:`Common` or mixin classes used to enhance
    classes derived from :py:class:`Common` need to have this class as one of
    its most distant ancestors. They should not descend directly from ``object``
    class, ``_CommonBase`` needs to be used instead.

    Our classes and mixins use keyword-only arguments, and with mixins in play,
    we do not have a trivial single-inheritance tree, therefore it's not simple
    to realize when a ``super().__init__`` belongs to ``object``. To deliver
    arguments to all classes, our ``__init__()`` methods must accept all
    parameters, even those they have no immediate use for, and propagate them
    via ``**kwargs``. Sooner or later, one of the classes would try to call
    ``object.__init__(**kwargs)``, but this particular ``__init__()`` accepts
    no keyword arguments, which would lead to an exception.

    ``_CommonBase`` sits at the root of the inheritance tree, and is responsible
    for calling ``object.__init__()`` *with no arguments*. Thanks to method
    resolution order, all "branches" of our tree of common classes should lead
    to ``_CommonBase``, making sure the call to ``object`` is correct. To behave
    correctly, ``_CommonBase`` needs to check which class is the next in the MRO
    sequence, and stop propagating arguments.
    """

    def __init__(self, **kwargs: Any) -> None:
        mro = type(self).__mro__
        # ignore[name-defined]: mypy does not recognize __class__, but it
        # exists and it's documented.
        # https://peps.python.org/pep-3135/
        # https://github.com/python/mypy/issues/4177
        parent = mro[mro.index(__class__) + 1]  # type: ignore[name-defined]

        if parent in (object, Generic):
            super().__init__()

        else:
            super().__init__(**kwargs)


class _CommonMeta(type):
    """
    A meta class for all :py:class:`Common` classes.

    Takes care of properly resetting :py:attr:`Common.cli_invocation` attribute
    that cannot be shared among classes.
    """

    def __init__(cls, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

        # TODO: repeat type annotation from `Common` - IIUIC, `cls` should be
        # the class being created, in our case that would be a subclass of
        # `Common`. For some reason, mypy is uncapable of detecting annotation
        # of this attribute in `Common`, and infers its type is `None` because
        # of the assignment below. That's incomplete, and leads to mypy warning
        # about assignments of `CliInvocation` instances to this attribute.
        # Repeating the annotation silences mypy, giving it better picture.
        cls.cli_invocation: Optional[tmt.cli.CliInvocation] = None


class Common(_CommonBase, metaclass=_CommonMeta):
    """
    Common shared stuff

    Takes care of command line context, options and workdir handling.
    Provides logging functions info(), verbose() and debug().
    Implements read() and write() for comfortable file access.
    Provides the run() method for easy command execution.
    """

    # When set to true, _opt will be ignored (default will be returned)
    ignore_class_options: bool = False
    _workdir: WorkdirType = None
    _clone_dirpath: Optional[Path] = None

    # TODO: must be declared outside of __init__(), because it must exist before
    # __init__() gets called to allow logging helpers work correctly when used
    # from mixins. But that's not very clean, is it? :( Maybe decoupling logging
    # from Common class would help, such a class would be able to initialize
    # itself without involving the rest of Common code. On the other hand,
    # Common owns workdir, for example, whose value affects logging too, so no
    # clear solution so far.
    #
    # Note: cannot use CommonDerivedType - it's a TypeVar filled in by the type
    # given to __init__() and therefore the type it's representing *now* is
    # unknown. but we know `parent` will be derived from `Common` class, so it's
    # mostly fine.
    parent: Optional['Common'] = None

    # Store actual name and safe name. When `name` changes, we need to update
    # `safe_name` accordingly. Direct access not encouraged, use `name` and
    # `safe_name` attributes.
    _name: str

    def inject_logger(self, logger: tmt.log.Logger) -> None:
        self._logger = logger

    def __init__(
            self,
            *,
            parent: Optional[CommonDerivedType] = None,
            name: Optional[str] = None,
            workdir: WorkdirArgumentType = None,
            relative_indent: int = 1,
            cli_invocation: Optional['tmt.cli.CliInvocation'] = None,
            logger: tmt.log.Logger,
            **kwargs: Any) -> None:
        """
        Initialize name and relation with the parent object

        Prepare the workdir for provided id / directory path
        or generate a new workdir name if workdir=True given.
        Store command line context and options for future use
        if context is provided.
        """

        super().__init__(
            parent=parent,
            name=name,
            workdir=workdir,
            relative_indent=relative_indent,
            logger=logger,
            **kwargs)

        # Use lowercase class name as the default name
        self.name = name or self.__class__.__name__.lower()
        self.parent = parent

        self.cli_invocation = cli_invocation

        self.inject_logger(logger)

        # Relative log indent level shift against the parent
        self._relative_indent = relative_indent

        # Initialize the workdir if requested
        self._workdir_load(workdir)

    @property
    def name(self) -> str:
        return self._name

    @name.setter
    def name(self, name: str) -> None:
        self._name = name

        # Reset safe name - when accessed next time, it'd be recomputed from
        # the name we just set.
        if 'safe_name' in self.__dict__:
            delattr(self, 'safe_name')

    @functools.cached_property
    def safe_name(self) -> str:
        """
        A safe variant of the name which does not contain special characters.

        Spaces and other special characters are removed to prevent problems with
        tools which do not expect them (e.g. in directory names).

        Unlike :py:meth:`pathless_safe_name`, this property preserves
        slashes, ``/``.
        """

        return sanitize_name(self.name)

    @functools.cached_property
    def pathless_safe_name(self) -> str:
        """
        A safe variant of the name which does not contain any special characters.

        Unlike :py:attr:`safe_name`, this property removes even slashes, ``/``.
        """

        return sanitize_name(self.name, allow_slash=False)

    def __str__(self) -> str:
        """ Name is the default string representation """
        return self.name

    #
    # Invokability via CLI
    #

    # CLI invocation of (sub)command represented by the class or instance.
    # When Click subcommand (or "group" command) runs, saves the Click context
    # in a class corresponding to the subcommand/group. For example, in command
    # like `tmt run report -h foo --bar=baz`, `report` subcommand would save
    # its context inside `tmt.steps.report.Report` class.
    #
    # The context can be also saved on the instance level, for more fine-grained
    # context tracking.
    #
    # The "later use" means the context is often used when looking for options
    # like --how or --dry, may affect step data from fmf or even spawn new phases.
    cli_invocation: Optional['tmt.cli.CliInvocation'] = None

    @classmethod
    def store_cli_invocation(
            cls,
            context: Optional['tmt.cli.Context'],
            options: Optional[dict[str, Any]] = None) -> 'tmt.cli.CliInvocation':
        """
        Record a CLI invocation and options it carries for later use.

        .. warning::

           The given context is saved into a class variable, therefore it will
           function as a "default" context for instances on which
           :py:meth:`store_cli_invocation` has not been called.

        :param context: CLI context representing the invocation.
        :param options: Optional dictionary with custom options.
            If provided, context is ignored.
        :raises GeneralError: when there was a previously saved invocation
            already. Multiple invocations are not allowed.
        """

        if cls.cli_invocation is not None:
            raise GeneralError(
                f"{cls.__name__} attempted to save a second CLI context: {cls.cli_invocation}")

        if options is not None:
            cls.cli_invocation = tmt.cli.CliInvocation.from_options(options)
        elif context is not None:
            cls.cli_invocation = tmt.cli.CliInvocation.from_context(context)
        else:
            raise GeneralError(
                "Either context or options have to be provided to store_cli_invocation().")

        return cls.cli_invocation

    @property
    def _purely_inherited_cli_invocation(self) -> Optional['tmt.cli.CliInvocation']:
        """
        CLI invocation attached to a parent of this instance.

        :returns: a class-level CLI invocation, the first one attached to
            parent class or its parent classes.
        """

        for klass in self.__class__.__mro__:
            if not issubclass(klass, Common):
                continue

            if klass.cli_invocation:
                return klass.cli_invocation

        return None

    @property
    def _inherited_cli_invocation(self) -> Optional['tmt.cli.CliInvocation']:
        """
        CLI invocation attached to this instance or its parents.

        :returns: instance-level CLI invocation, or, if there is none,
            current class and its parent classes are inspected for their
            class-level invocations.
        """

        if self.cli_invocation is not None:
            return self.cli_invocation

        return self._purely_inherited_cli_invocation

    @property
    def _cli_context_object(self) -> Optional['tmt.cli.ContextObject']:
        """
        A CLI context object attached to the CLI invocation.

        :returns: a CLI context object, or ``None`` if there is no
            CLI invocation attached to this instance or any of its
            parent classes.
        """

        invocation = self._inherited_cli_invocation

        if invocation is None:
            return None

        if invocation.context is None:
            return None

        return invocation.context.obj

    @property
    def _cli_options(self) -> dict[str, Any]:
        """
        CLI options attached to the CLI invocation.

        :returns: CLI options, or an empty dictionary if there is no
            CLI invocation attached to this instance or any of its
            parent classes.
        """

        invocation = self._inherited_cli_invocation

        if invocation is None:
            return {}

        return invocation.options

    @property
    def _cli_fmf_context(self) -> FmfContext:
        """
        An fmf context attached to the CLI invocation.

        :returns: an fmf context, or an empty fmf context if there
            is no CLI invocation attached to this instance or any of
            its parent classes.
        """

        if self._cli_context_object is None:
            return FmfContext()

        return self._cli_context_object.fmf_context

    @property
    def _fmf_context(self) -> FmfContext:
        """ An fmf context set for this object. """

        # By default, the only fmf context available is one provided via CLI.
        # But some derived classes can and will override this, because fmf
        # context can exist in fmf nodes, too.
        return self._cli_fmf_context

    @overload
    @classmethod
    def _opt(cls, option: str) -> Any:
        pass

    @overload
    @classmethod
    def _opt(cls, option: str, default: T) -> T:
        pass

    @classmethod
    def _opt(cls, option: str, default: Any = None) -> Any:
        """ Get an option from the command line context (class version) """
        if cls.ignore_class_options:
            return default

        if cls.cli_invocation is None:
            return default

        return cls.cli_invocation.options.get(option, default)

    def opt(self, option: str, default: Optional[Any] = None) -> Any:
        """
        Get an option from the command line options

        Checks also parent options. For flags (boolean values) parent's
        True wins over child's False (e.g. run --quiet enables quiet
        mode for all included plans and steps).

        For options that can be used multiple times, the child overrides
        the parent if it was defined (e.g. run -av provision -vvv runs
        all steps except for provision in mildly verbose mode, provision
        is run with the most verbosity).

        Environment variables override command line options.
        """
        # Translate dashes to underscores to match click's conversion
        option = option.replace('-', '_')

        # Get local option
        local = self._inherited_cli_invocation.options.get(
            option, default) if self._inherited_cli_invocation else None

        # Check parent option
        parent = None
        if self.parent:
            parent = self.parent.opt(option)
        return parent if parent is not None else local

    @property
    def debug_level(self) -> int:
        """ The current debug level applied to this object """

        return self._logger.debug_level

    @debug_level.setter
    def debug_level(self, level: int) -> None:
        """ Update the debug level attached to this object """
        self._logger.debug_level = level

    @property
    def verbosity_level(self) -> int:
        """ The current verbosity level applied to this object """

        return self._logger.verbosity_level

    @verbosity_level.setter
    def verbosity_level(self, level: int) -> None:
        """ Update the verbosity level attached to this object """
        self._logger.verbosity_level = level

    @property
    def quietness(self) -> bool:
        """ The current quietness level applied to this object """

        return self._logger.quiet

    # TODO: interestingly, the option has its own default, right? So why do we
    # need a default of our own? Because sometimes commands have not been
    # invoked, and there's no CLI invocation to ask for the default value.
    # Maybe we should add some kind of "default invocation"...
    def _get_cli_flag(self, key: str, option: str, default: bool) -> bool:
        """
        Find the eventual value of a CLI-provided flag option.

        :param key: in the tree of :py:class:`Common` instance, the
            flag is represented by this attribute.
        :param option: a CLI option name of the flag.
        :param default: default value if the option has not been specified.
        """

        if self.parent:
            parent = cast(bool, getattr(self.parent, key))

            if parent:
                return parent

        invocation = self._inherited_cli_invocation

        if invocation and option in invocation.options:
            return cast(bool, invocation.options[option])

        invocation = self._purely_inherited_cli_invocation

        if invocation and option in invocation.options:
            return cast(bool, invocation.options[option])

        return default

    @property
    def is_dry_run(self) -> bool:
        """ Whether the current run is a dry-run """

        return self._get_cli_flag('is_dry_run', 'dry', False)

    @property
    def is_forced_run(self) -> bool:
        """ Whether the current run is allowed to overwrite files and data """

        return self._get_cli_flag('is_forced_run', 'force', False)

    @property
    def should_run_again(self) -> bool:
        """ Whether selected step or the whole run should be run again """

        return self._get_cli_flag('should_run_again', 'again', False)

    @property
    def is_feeling_safe(self) -> bool:
        """ Whether the current run is allowed to run unsafe actions """

        return self._get_cli_flag('is_feeling_safe', 'feeling_safe', False)

    def _level(self) -> int:
        """ Hierarchy level """
        if self.parent is None:
            return -1
        return self.parent._level() + self._relative_indent

    def _indent(
            self,
            key: str,
            value: Optional[str] = None,
            color: Optional[str] = None,
            shift: int = 0) -> str:
        """ Indent message according to the object hierarchy """

        return tmt.log.indent(
            key,
            value=value,
            color=color,
            level=self._level() + shift)

    def print(
            self,
            text: str,
            color: Optional[str] = None,
            shift: int = 0) -> None:
        """
        Print out an output.

        This method is supposed to be used for emitting a command output. Not
        to be mistaken with logging - errors, warnings, general command progress,
        and so on.

        ``print()`` emits even when ``--quiet`` is used, as the option suppresses
        **logging** but not the actual command output.
        """

        self._logger.print(text, color=color, shift=shift)

    def info(
            self,
            key: str,
            value: Optional[LoggableValue] = None,
            color: Optional[str] = None,
            shift: int = 0) -> None:
        """ Show a message unless in quiet mode """
        self._logger.info(key, value=value, color=color, shift=shift)

    def verbose(
            self,
            key: str,
            value: Optional[LoggableValue] = None,
            color: Optional[str] = None,
            shift: int = 0,
            level: int = 1,
            topic: Optional[tmt.log.Topic] = None) -> None:
        """
        Show message if in requested verbose mode level

        In quiet mode verbose messages are not displayed.
        """
        self._logger.verbose(key, value=value, color=color, shift=shift, level=level, topic=topic)

    def debug(
            self,
            key: str,
            value: Optional[LoggableValue] = None,
            color: Optional[str] = None,
            shift: int = 0,
            level: int = 1,
            topic: Optional[tmt.log.Topic] = None) -> None:
        """
        Show message if in requested debug mode level

        In quiet mode debug messages are not displayed.
        """
        self._logger.debug(key, value=value, color=color, shift=shift, level=level, topic=topic)

    def warn(self, message: str, shift: int = 0) -> None:
        """ Show a yellow warning message on info level, send to stderr """
        self._logger.warning(message, shift=shift)

    def fail(self, message: str, shift: int = 0) -> None:
        """ Show a red failure message on info level, send to stderr """
        self._logger.fail(message, shift=shift)

    def _command_verbose_logger(
            self,
            key: str,
            value: Optional[str] = None,
            color: Optional[str] = None,
            shift: int = 1,
            level: int = 3,
            topic: Optional[tmt.log.Topic] = None) -> None:
        """
        Reports the executed command in verbose mode.

        This is a tailored verbose() function used for command logging where
        default parameters are adjusted (to preserve the function type).
        """
        self.verbose(key=key, value=value, color=color, shift=shift, level=level, topic=topic)

    def run(self,
            command: Command,
            friendly_command: Optional[str] = None,
            silent: bool = False,
            message: Optional[str] = None,
            cwd: Optional[Path] = None,
            ignore_dry: bool = False,
            shell: bool = False,
            env: Optional[Environment] = None,
            interactive: bool = False,
            join: bool = False,
            log: Optional[tmt.log.LoggingFunction] = None,
            timeout: Optional[int] = None,
            on_process_start: Optional[OnProcessStartCallback] = None) -> CommandOutput:
        """
        Run command, give message, handle errors

        Command is run in the workdir be default.
        In dry mode commands are not executed unless ignore_dry=True.
        Environment is updated with variables from the 'env' dictionary.

        Output is logged using self.debug() or custom 'log' function.
        A user friendly command string 'friendly_command' will be shown,
        if provided, at the beginning of the command output.

        Returns named tuple CommandOutput.
        """

        dryrun_actual = self.is_dry_run

        if ignore_dry:
            dryrun_actual = False

        return command.run(
            friendly_command=friendly_command,
            silent=silent,
            message=message,
            cwd=cwd or self.workdir,
            dry=dryrun_actual,
            shell=shell,
            env=env,
            interactive=interactive,
            on_process_start=on_process_start,
            join=join,
            log=log,
            timeout=timeout,
            caller=self,
            logger=self._logger
            )

    def read(self, path: Path, level: int = 2) -> str:
        """ Read a file from the workdir """
        if self.workdir:
            path = self.workdir / path
        self.debug(f"Read file '{path}'.", level=level)
        try:
            with open(path, encoding='utf-8', errors='replace') as data:
                return data.read()
        except OSError as error:
            raise FileError(f"Failed to read '{path}'.\n{error}")

    def write(
            self,
            path: Path,
            data: str,
            mode: str = 'w',
            level: int = 2) -> None:
        """ Write a file to the workdir """
        if self.workdir:
            path = self.workdir / path
        action = 'Append to' if mode == 'a' else 'Write'
        self.debug(f"{action} file '{path}'.", level=level)
        # Dry mode
        if self.is_dry_run:
            return
        try:
            with open(path, mode, encoding='utf-8', errors='replace') as file:
                file.write(data)
        except OSError as error:
            raise FileError(f"Failed to write '{path}'.\n{error}")

    def _workdir_init(self, id_: WorkdirArgumentType = None) -> None:
        """
        Initialize the work directory

        The workdir root is acquired by calling :py:func:`effective_workdir_root`.

        If 'id' is a path, that directory is used instead. Otherwise a
        new workdir is created under the workdir root directory.
        """

        workdir_root = effective_workdir_root()

        # Prepare the workdir name from given id or path
        if isinstance(id_, Path):
            # Use provided directory if full path given
            workdir = id_ if '/' in str(id_) else workdir_root / id_
            # Resolve any relative paths
            workdir = workdir.resolve()
        # Weird workdir id
        elif id_ is not None:
            raise GeneralError(
                f"Invalid workdir '{id_}', expected a path or None.")

        def _check_or_create_workdir_root_with_perms() -> None:
            """ If created workdir_root has to be 1777 for multi-user"""
            if not workdir_root.is_dir():
                try:
                    workdir_root.mkdir(exist_ok=True, parents=True)
                    workdir_root.chmod(0o1777)
                except OSError as error:
                    raise FileError(f"Failed to prepare workdir '{workdir_root}': {error}")

        if id_ is None:
            # Prepare workdir_root first
            _check_or_create_workdir_root_with_perms()

            # Generated unique id or fail, has to be atomic call
            for id_bit in range(1, WORKDIR_MAX + 1):
                directory = f"run-{str(id_bit).rjust(3, '0')}"
                workdir = workdir_root / directory
                try:
                    # Call is atomic, no race possible
                    workdir.mkdir(parents=True)
                    break
                except FileExistsError:
                    pass
            else:
                raise GeneralError(
                    f"Workdir full. Cleanup the '{workdir_root}' directory.")
        else:
            # Cleanup possible old workdir if called with --scratch
            if self.opt('scratch'):
                self._workdir_cleanup(workdir)

            if workdir.is_relative_to(workdir_root):
                _check_or_create_workdir_root_with_perms()

            # Create the workdir
            create_directory(
                path=workdir,
                name='workdir',
                quiet=True,
                logger=self._logger)

        # TODO: chicken and egg problem: when `Common` is instantiated, the workdir
        # path might be already known, but it's often not created yet. Therefore
        # a logfile handler cannot be attached to the given logger.
        # This is a problem, as we modify a given logger, and we may modify the
        # incorrect logger, and we may modify 3rd party app logger. The solution
        # to our little logging problem would probably be related to refactoring
        # of workdir creation some day in the future.
        self._logger.add_logfile_handler(workdir / tmt.log.LOG_FILENAME)
        self._workdir = workdir

    def _workdir_name(self) -> Optional[Path]:
        """ Construct work directory name from parent workdir """
        # Need the parent workdir
        if self.parent is None or self.parent.workdir is None:
            return None
        # Join parent name with self
        return self.parent.workdir / self.safe_name.lstrip("/")

    def _workdir_load(self, workdir: WorkdirArgumentType) -> None:
        """
        Create the given workdir if it is not None

        If workdir=True, the directory name is automatically generated.
        """
        if workdir is True:
            self._workdir_init()
        elif workdir is not None:
            self._workdir_init(workdir)

    def _workdir_cleanup(self, path: Optional[Path] = None) -> None:
        """ Clean up the work directory """
        directory = path or self._workdir_name()
        if directory is not None and directory.is_dir():
            self.debug(f"Clean up workdir '{directory}'.", level=2)
            shutil.rmtree(directory)
        self._workdir = None

    @property
    def workdir(self) -> Optional[Path]:
        """ Get the workdir, create if does not exist """
        if self._workdir is None:
            self._workdir = self._workdir_name()
            # Workdir not enabled, even parent does not have one
            if self._workdir is None:
                return None
            # Create a child workdir under the parent workdir
            create_directory(
                path=self._workdir,
                name='workdir',
                quiet=True,
                logger=self._logger)

        return self._workdir

    @property
    def clone_dirpath(self) -> Path:
        """
        Path for cloning into

        Used internally for picking specific libraries (or anything
        else) from cloned repos for filtering purposes, it is removed at
        the end of relevant step.
        """
        if not self._clone_dirpath:
            self._clone_dirpath = Path(tempfile.TemporaryDirectory(dir=self.workdir).name)

        return self._clone_dirpath


class _MultiInvokableCommonMeta(_CommonMeta):
    """
    A meta class for all :py:class:`Common` classes.

    Takes care of properly resetting :py:attr:`Common.cli_invocation` attribute
    that cannot be shared among classes.
    """

    def __init__(cls, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

        cls.cli_invocations: list[tmt.cli.CliInvocation] = []


class MultiInvokableCommon(Common, metaclass=_MultiInvokableCommonMeta):
    cli_invocations: list['tmt.cli.CliInvocation']

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

    @classmethod
    def store_cli_invocation(
            cls,
            context: Optional['tmt.cli.Context'],
            options: Optional[dict[str, Any]] = None) -> 'tmt.cli.CliInvocation':
        """
        Save a CLI context and options it carries for later use.

        .. warning::

           The given context is saved into a class variable, therefore it will
           function as a "default" context for instances on which
           :py:meth:`_save_cli_context_to_instance` has not been called.

        .. warning::

           The given context will overwrite any previously saved context.

        :param context: CLI context to save.
        :param options: Optional dictionary with custom options.
            If provided, context is ignored.
        """

        if options is not None:
            invocation = tmt.cli.CliInvocation.from_options(options)
        elif context is not None:
            invocation = tmt.cli.CliInvocation.from_context(context)
        else:
            raise GeneralError(
                "Either context or options have to be provided to store_cli_invocation().")

        cls.cli_invocations.append(invocation)

        cls.cli_invocation = invocation

        return invocation


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#  Exceptions
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~


class GeneralError(Exception):
    """ General error """

    def __init__(
            self,
            message: str,
            causes: Optional[list[Exception]] = None,
            *args: Any,
            **kwargs: Any) -> None:
        """
        General error.

        :param message: error message.
        :param causes: optional list of exceptions that caused this one. Since
            ``raise ... from ...`` allows only for a single cause, and some of
            our workflows may raise exceptions triggered by more than one
            exception, we need a mechanism for storing them. Our reporting will
            honor this field, and report causes the same way as ``__cause__``.
        """

        super().__init__(message, *args, **kwargs)

        self.message = message
        self.causes = causes or []


class GitUrlError(GeneralError):
    """ Remote git url is not reachable """


class FileError(GeneralError):
    """ File operation error """


class RunError(GeneralError):
    """ Command execution error """

    def __init__(
            self,
            message: str,
            command: Command,
            returncode: int,
            stdout: Optional[str] = None,
            stderr: Optional[str] = None,
            caller: Optional[Common] = None,
            *args: Any,
            **kwargs: Any) -> None:
        super().__init__(message, *args, **kwargs)
        self.command = command
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        # Store instance of caller to get additional details
        # in post processing (e.g. verbose level)
        self.caller = caller
        # Since logger may get swapped, to better reflect context (guests start
        # with logger inherited from `provision` but may run under `prepare` or
        # `finish`), save a logger for later.
        self.logger = caller._logger if isinstance(caller, Common) else None


class MetadataError(GeneralError):
    """ General metadata error """


class SpecificationError(MetadataError):
    """ Metadata specification error """

    def __init__(
            self,
            message: str,
            validation_errors: Optional[list[tuple[jsonschema.ValidationError, str]]] = None,
            *args: Any,
            **kwargs: Any) -> None:
        super().__init__(message, *args, **kwargs)
        self.validation_errors = validation_errors


class NormalizationError(SpecificationError):
    """ Raised when a key normalization fails """

    def __init__(
            self,
            key_address: str,
            raw_value: Any,
            expected_type: str,
            *args: Any,
            **kwargs: Any) -> None:
        """
        Raised when a key normalization fails.

        A subclass of :py:class:`SpecificationError`, but describing errors
        that appear in a very specific point of key loading in a unified manner.

        :param key_address: the key in question, preferably with detailed location,
            e.g. ``/plans/foo:discover[0].tests``.
        :param raw_value: input value, the one that failed the normalization.
        :param expected_type: string description of expected, allowed types, as
            a hint in the error message.
        """

        super().__init__(
            f"Field '{key_address}' must be {expected_type}, '{type(raw_value).__name__}' found.",
            *args,
            **kwargs)

        self.key_address = key_address
        self.raw_value = raw_value
        self.expected_type = expected_type


class ConvertError(MetadataError):
    """ Metadata conversion error """


class StructuredFieldError(GeneralError):
    """ StructuredField parsing error """


class WaitingIncompleteError(GeneralError):
    """ Waiting incomplete """

    def __init__(self) -> None:
        super().__init__('Waiting incomplete')


class WaitingTimedOutError(GeneralError):
    """ Waiting ran out of time """

    def __init__(
            self,
            check: 'WaitCheckType[T]',
            timeout: datetime.timedelta,
            check_success: bool = False) -> None:
        if check_success:
            super().__init__(
                f"Waiting for condition '{check.__name__}' succeeded but took too much time "
                f"after waiting {timeout}."
                )

        else:
            super().__init__(
                f"Waiting for condition '{check.__name__}' timed out "
                f"after waiting {timeout}."
                )

        self.check = check
        self.timeout = timeout
        self.check_success = check_success


class RetryError(GeneralError):
    """ Retries unsuccessful """

    def __init__(self, label: str, causes: list[Exception]) -> None:
        super().__init__(f"Retries of '{label}' unsuccessful.", causes)


class BackwardIncompatibleDataError(GeneralError):
    """ A backward incompatible data cannot be processed """


# Step exceptions


class DiscoverError(GeneralError):
    """ Discover step error """


class ProvisionError(GeneralError):
    """ Provision step error """


class PrepareError(GeneralError):
    """ Prepare step error """


class ExecuteError(GeneralError):
    """ Execute step error """


class RebootTimeoutError(ExecuteError):
    """ Reboot failed due to a timeout """


class ReportError(GeneralError):
    """ Report step error """


class FinishError(GeneralError):
    """ Finish step error """


def render_run_exception_streams(
        stdout: Optional[str],
        stderr: Optional[str],
        verbose: int = 0) -> Iterator[str]:
    """ Render run exception output streams for printing """

    for name, output in (('stdout', stdout), ('stderr', stderr)):
        if not output:
            continue
        output_lines = output.strip().split('\n')
        # Show all lines in verbose mode, limit to maximum otherwise
        if verbose > 0:
            line_summary = f"{len(output_lines)}"
        else:
            line_summary = f"{min(len(output_lines), OUTPUT_LINES)}/{len(output_lines)}"
            output_lines = output_lines[-OUTPUT_LINES:]

        yield f'{name} ({line_summary} lines)'
        yield OUTPUT_WIDTH * '~'
        yield from output_lines
        yield OUTPUT_WIDTH * '~'
        yield ''


def render_run_exception(exception: RunError) -> Iterator[str]:
    """ Render detailed output upon command execution errors for printing """

    # Check verbosity level used during raising exception,
    if exception.logger:
        verbose = exception.logger.verbosity_level
    elif isinstance(exception.caller, Common):
        verbose = exception.caller.verbosity_level
    else:
        verbose = 0

    yield from render_run_exception_streams(exception.stdout, exception.stderr, verbose=verbose)


def render_exception_stack(exception: BaseException) -> Iterator[str]:
    """ Render traceback of the given exception """

    exception_traceback = traceback.TracebackException(
        type(exception),
        exception,
        exception.__traceback__,
        capture_locals=True)

    # N806: allow upper-case names to make them look like formatting
    # tags in strings below.
    R = functools.partial(click.style, fg='red')  # noqa: N806
    Y = functools.partial(click.style, fg='yellow')  # noqa: N806
    B = functools.partial(click.style, fg='blue')  # noqa: N806

    yield R('Traceback (most recent call last):')
    yield ''

    for frame in exception_traceback.stack:
        yield f'File {Y(frame.filename)}, line {Y(str(frame.lineno))}, in {Y(frame.name)}'
        yield f'  {B(frame.line)}'

        if os.getenv('TMT_SHOW_TRACEBACK', '0').lower() == 'full' and frame.locals:
            yield ''

            for k, v in frame.locals.items():
                yield f'  {B(k)} = {Y(v)}'

            yield ''


def render_exception(exception: BaseException) -> Iterator[str]:
    """ Render the exception and its causes for printing """

    def _indent(iterable: Iterable[str]) -> Iterator[str]:
        for item in iterable:
            if not item:
                yield item

            else:
                for line in item.splitlines():
                    yield f'{INDENT * " "}{line}'

    yield click.style(str(exception), fg='red')

    if isinstance(exception, RunError):
        yield ''
        yield from render_run_exception(exception)

    if os.getenv('TMT_SHOW_TRACEBACK', '0') != '0':
        yield ''
        yield from _indent(render_exception_stack(exception))

    # Follow the chain and render all causes
    def _render_cause(number: int, cause: BaseException) -> Iterator[str]:
        yield ''
        yield f'Cause number {number}:'
        yield ''
        yield from _indent(render_exception(cause))

    def _render_causes(causes: list[BaseException]) -> Iterator[str]:
        yield ''
        yield f'The exception was caused by {len(causes)} earlier exceptions'

        for number, cause in enumerate(causes, start=1):
            yield from _render_cause(number, cause)

    causes: list[BaseException] = []

    if isinstance(exception, GeneralError) and exception.causes:
        causes += exception.causes

    if exception.__cause__:
        causes += [exception.__cause__]

    if causes:
        yield from _render_causes(causes)


def show_exception(exception: BaseException) -> None:
    """ Display the exception and its causes """

    from tmt.cli import EXCEPTION_LOGGER

    EXCEPTION_LOGGER.print('', file=sys.stderr)
    EXCEPTION_LOGGER.print('\n'.join(render_exception(exception)), file=sys.stderr)


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#  Utilities
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~


def uniq(values: list[T]) -> list[T]:
    """ Return a list of all unique items from ``values`` """
    return list(set(values))


def duplicates(values: Iterable[Optional[T]]) -> Iterator[T]:
    """ Iterate over all duplicate values in ``values`` """
    seen = Counter(values)
    for value, count in seen.items():
        if value is None or count == 1:
            continue
        yield value


def flatten(lists: Iterable[list[T]], unique: bool = False) -> list[T]:
    """
    "Flatten" a list of lists into a single-level list.

    :param lists: an iterable of lists to flatten.
    :param unique: if set, duplicate items would be removed, leaving only
        a single instance in the final list.
    :returns: list of items from all given lists.
    """

    flattened: list[T] = [item for sublist in lists for item in sublist]

    return uniq(flattened) if unique else flattened


def quote(string: str) -> str:
    """ Surround a string with double quotes """
    return f'"{string}"'


def pure_ascii(text: Any) -> bytes:
    """ Transliterate special unicode characters into pure ascii """
    if not isinstance(text, str):
        text = str(text)
    return unicodedata.normalize('NFKD', text).encode('ascii', 'ignore')


def get_full_metadata(fmf_tree_path: Path, node_path: str) -> Any:
    """
    Get full metadata for a node in any fmf tree

    Go through fmf tree nodes using given relative node path
    and return full data as dictionary.
    """
    try:
        return fmf.Tree(fmf_tree_path).find(node_path).data
    except AttributeError:
        raise MetadataError(f"'{node_path}' not found in the '{fmf_tree_path}' Tree.")


def filter_paths(directory: Path, searching: list[str], files_only: bool = False) -> list[Path]:
    """
    Filter files for specific paths we are searching for inside a directory

    Returns list of matching paths.
    """
    all_paths = list(directory.rglob('*'))  # get all filepaths for given dir recursively
    alldirs = [str(d) for d in all_paths if d.is_dir()]
    allfiles = [str(file) for file in all_paths if not file.is_dir()]
    found_paths: list[str] = []

    for search_string in searching:
        if search_string == '/':
            return all_paths
        regex = re.compile(search_string)

        if not files_only:
            # Search in directories first to reduce amount of copying later
            matches = list(filter(regex.search, alldirs))
            if matches:
                found_paths += matches
                continue

        # Search through all files
        found_paths += list(filter(regex.search, allfiles))
    return [Path(path) for path in set(found_paths)]  # return all matching unique paths as Path's


def dict_to_yaml(
        data: Union[dict[str, Any], list[Any], 'tmt.base._RawFmfId'],
        width: Optional[int] = None,
        sort: bool = False,
        start: bool = False) -> str:
    """ Convert dictionary into yaml """
    output = io.StringIO()
    yaml = YAML()
    yaml.indent(mapping=4, sequence=4, offset=2)
    yaml.default_flow_style = False
    yaml.allow_unicode = True
    yaml.encoding = 'utf-8'
    # ignore[assignment]: ruamel bug workaround, see stackoverflow.com/questions/58083562,
    # sourceforge.net/p/ruamel-yaml/tickets/322/
    #
    # Yeah, but sometimes the ignore is not needed, at least mypy in a Github
    # check tells us it's unused... When disabled, the local pre-commit fails.
    # It seems we cannot win until ruamel.yaml gets its things fixed, therefore,
    # giving up, and using `cast()` to enforce matching types to silence mypy,
    # being fully aware the enforce types are wrong.
    yaml.width = cast(None, width)  # # type: ignore[assignment]
    yaml.explicit_start = cast(None, start)  # # type: ignore[assignment]

    # For simpler dumping of well-known classes
    def _represent_path(representer: Representer, data: Path) -> Any:
        return representer.represent_scalar('tag:yaml.org,2002:str', str(data))

    yaml.representer.add_representer(pathlib.Path, _represent_path)  # noqa: TID251
    yaml.representer.add_representer(pathlib.PosixPath, _represent_path)  # noqa: TID251
    yaml.representer.add_representer(Path, _represent_path)

    def _represent_environment(representer: Representer, data: Environment) -> Any:
        return representer.represent_mapping('tag:yaml.org,2002:map', data.to_fmf_spec())

    yaml.representer.add_representer(Environment, _represent_environment)

    # Convert multiline strings
    scalarstring.walk_tree(data)
    if sort:
        # Sort the data https://stackoverflow.com/a/40227545
        sorted_data = CommentedMap()
        for key in sorted(data):
            # ignore[literal-required]: `data` may be either a generic
            # dictionary, or _RawFmfId which allows only a limited set
            # of keys. That spooks mypy, but we do not add any keys,
            # therefore we will not escape TypedDict constraints.
            sorted_data[key] = data[key]  # type: ignore[literal-required]
        data = sorted_data
    yaml.dump(data, output)
    return output.getvalue()


YamlTypType = Literal['rt', 'safe', 'unsafe', 'base']


def yaml_to_dict(data: Any,
                 yaml_type: Optional[YamlTypType] = None) -> dict[Any, Any]:
    """ Convert yaml into dictionary """
    yaml = YAML(typ=yaml_type)
    loaded_data = yaml.load(data)
    if loaded_data is None:
        return {}
    if not isinstance(loaded_data, dict):
        raise GeneralError(
            f"Expected dictionary in yaml data, "
            f"got '{type(loaded_data).__name__}'.")
    return loaded_data


def yaml_to_list(data: Any,
                 yaml_type: Optional[YamlTypType] = 'safe') -> list[Any]:
    """ Convert yaml into list """
    yaml = YAML(typ=yaml_type)
    try:
        loaded_data = yaml.load(data)
    except ParserError as error:
        raise GeneralError(f"Invalid yaml syntax: {error}")

    if loaded_data is None:
        return []
    if not isinstance(loaded_data, list):
        raise GeneralError(
            f"Expected list in yaml data, "
            f"got '{type(loaded_data).__name__}'.")
    return loaded_data


def json_to_list(data: Any) -> list[Any]:
    """ Convert json into list """

    try:
        loaded_data = json.load(data)
    except json.decoder.JSONDecodeError as error:
        raise GeneralError(f"Invalid json syntax: {error}")

    if not isinstance(loaded_data, list):
        raise GeneralError(
            f"Expected list in json data, "
            f"got '{type(loaded_data).__name__}'.")
    return loaded_data


#: A type representing compatible sources of keys and values.
KeySource = Union[dict[str, Any], fmf.Tree]

#: Type of field's normalization callback.
NormalizeCallback = Callable[[str, Any, tmt.log.Logger], T]

#: Type of field's exporter callback.
FieldExporter = Callable[[T], Any]

#: Type of field's CLI option specification.
FieldCLIOption = Union[str, Sequence[str]]

#: Type of field's serialization callback.
SerializeCallback = Callable[[T], Any]

#: Type of field's unserialization callback.
UnserializeCallback = Callable[[Any], T]

#: Types for generic "data container" classes and instances. In tmt code, this
#: reduces to data classes and data class instances. Our :py:class:`DataContainer`
#: are perfectly compatible data classes, but some helper methods may be used
#: on raw data classes, not just on ``DataContainer`` instances.
ContainerClass: 'TypeAlias' = type['DataclassInstance']
ContainerInstance: 'TypeAlias' = 'DataclassInstance'
Container = Union[ContainerClass, ContainerInstance]


def key_to_option(key: str) -> str:
    """ Convert a key name to corresponding option name """

    return key.replace('_', '-')


def option_to_key(option: str) -> str:
    """ Convert an option name to corresponding key name """

    return option.replace('-', '_')


@dataclasses.dataclass
class FieldMetadata(Generic[T]):
    """
    A dataclass metadata container used by our custom dataclass field management.

    Attached to fields defined with :py:func:`field`
    """

    internal: bool = False

    #: Help text documenting the field.
    help: Optional[str] = None

    #: If field accepts a value, this string would represent it in documentation.
    #: This stores the metavar provided when field was created - it may be unset.
    #: py:attr:`metavar` provides the actual metavar to be used.
    _metavar: Optional[str] = None

    #: The default value for the field.
    default: Optional[T] = None

    #: A zero-argument callable that will be called when a default value is
    #: needed for the field.
    default_factory: Optional[Callable[[], T]] = None

    #: Marks the fields as a flag.
    is_flag: bool = False

    #: Marks the field as accepting multiple values. When used on command line,
    #: the option could be used multiple times, accumulating values.
    multiple: bool = False

    #: If set, show the default value in command line help.
    show_default: bool = False

    #: Either a list of allowed values the field can take, or a zero-argument
    #: callable that would return such a list.
    _choices: Union[None, Sequence[str], Callable[[], Sequence[str]]] = None

    #: Environment variable providing value for the field.
    envvar: Optional[str] = None

    #: Mark the option as deprecated. Instance of :py:class:`Deprecated`
    #: describes the version in which the field was deprecated plus an optional
    #: hint with the recommended alternative. Documentation and help texts would
    #: contain this info.
    deprecated: Optional['tmt.options.Deprecated'] = None

    #: One or more command-line option names.
    cli_option: Optional[FieldCLIOption] = None

    #: A normalization callback to call when loading the value from key source
    #: (performed by :py:class:`NormalizeKeysMixin`).
    normalize_callback: Optional['NormalizeCallback[T]'] = None

    # Callbacks for custom serialize/unserialize operations (performed by
    # :py:class:`SerializableContainer`).
    serialize_callback: Optional['SerializeCallback[T]'] = None
    unserialize_callback: Optional['SerializeCallback[T]'] = None

    #: An export callback to call when exporting the field (performed by
    #: :py:class:`tmt.export.Exportable`).
    export_callback: Optional['FieldExporter[T]'] = None

    #: CLI option parameters, for lazy option creation.
    _option_args: Optional['FieldCLIOption'] = None
    _option_kwargs: dict[str, Any] = dataclasses.field(default_factory=dict)

    #: A :py:func:`click.option` decorator defining a corresponding CLI option.
    _option: Optional['tmt.options.ClickOptionDecoratorType'] = None

    @functools.cached_property
    def choices(self) -> Optional[Sequence[str]]:
        """ A list of allowed values the field can take """

        if isinstance(self._choices, (list, tuple)):
            return list(self._choices)

        if callable(self._choices):
            return self._choices()

        return None

    @functools.cached_property
    def metavar(self) -> Optional[str]:
        """ Placeholder for field's value in documentation and help """

        if self._metavar:
            return self._metavar

        if self.choices:
            return '|'.join(self.choices)

        return None

    @property
    def has_default(self) -> bool:
        """ Whether the field has a default value """

        return self.default_factory is not None \
            or self.default is not dataclasses.MISSING

    @property
    def materialized_default(self) -> Optional[T]:
        """ Returns the actual default value of the field """

        if self.default_factory is not None:
            return self.default_factory()

        if self.default is not dataclasses.MISSING:
            return self.default

        return None

    @property
    def option(self) -> Optional['tmt.options.ClickOptionDecoratorType']:
        if self._option is None and self.cli_option:
            from tmt.options import option

            self._option_args = (self.cli_option,) if isinstance(self.cli_option, str) \
                else self.cli_option

            self._option_kwargs.update({
                'is_flag': self.is_flag,
                'multiple': self.multiple,
                'envvar': self.envvar,
                'metavar': self.metavar,
                'choices': self.choices,
                'show_default': self.show_default,
                'help': self.help,
                'deprecated': self.deprecated
                })

            if self.default is not dataclasses.MISSING and not self.is_flag:
                self._option_kwargs['default'] = self.default

            self._option = option(
                *self._option_args,
                **self._option_kwargs
                )

        return self._option


def container_fields(container: Container) -> Iterator[dataclasses.Field[Any]]:
    yield from dataclasses.fields(container)


def container_keys(container: Container) -> Iterator[str]:
    """ Iterate over key names in a container """

    for field in container_fields(container):
        yield field.name


def container_values(container: ContainerInstance) -> Iterator[Any]:
    """ Iterate over values in a container """

    for field in container_fields(container):
        yield container.__dict__[field.name]


def container_items(container: ContainerInstance) -> Iterator[tuple[str, Any]]:
    """ Iterate over key/value pairs in a container """

    for field in container_fields(container):
        yield field.name, container.__dict__[field.name]


def container_field(
        container: Container,
        key: str) -> tuple[str, str, Any, dataclasses.Field[Any], 'FieldMetadata[Any]']:
    """
    Return a dataclass/data container field info by the field's name.

    Surprisingly, :py:mod:`dataclasses` package does not have a helper for
    this. One can iterate over fields, but there's no *public* API for
    retrieving a field when one knows its name.

    :param cls: a dataclass/data container class whose fields to search.
    :param key: field name to retrieve.
    :raises GeneralError: when the field does not exist.
    """

    for field in container_fields(container):
        if field.name != key:
            continue

        metadata = field.metadata.get('tmt', FieldMetadata())
        return (
            field.name,
            key_to_option(field.name),
            container.__dict__[field.name] if not inspect.isclass(container) else None,
            field,
            metadata)

    if isinstance(container, DataContainer):
        raise GeneralError(
            f"Could not find field '{key}' in class '{container.__class__.__name__}'.")

    raise GeneralError(f"Could not find field '{key}' in class '{container}'.")


@dataclasses.dataclass
class DataContainer:
    """ A base class for objects that have keys and values """

    def to_dict(self) -> dict[str, Any]:
        """
        Convert to a mapping.

        See https://tmt.readthedocs.io/en/stable/code/classes.html#class-conversions
        for more details.
        """

        return dict(self.items())

    def to_minimal_dict(self) -> dict[str, Any]:
        """
        Convert to a mapping with unset keys omitted.

        See https://tmt.readthedocs.io/en/stable/code/classes.html#class-conversions
        for more details.
        """

        return {
            key: value for key, value in self.items() if value is not None
            }

    # This method should remain a class-method: 1. list of keys is known
    # already, therefore it's not necessary to create an instance, and
    # 2. some functionality makes use of this knowledge.
    @classmethod
    def keys(cls) -> Iterator[str]:
        """ Iterate over key names """

        yield from container_keys(cls)

    def values(self) -> Iterator[Any]:
        """ Iterate over key values """

        yield from container_values(self)

    def items(self) -> Iterator[tuple[str, Any]]:
        """ Iterate over key/value pairs """

        yield from container_items(self)

    @classmethod
    def _default(cls, key: str, default: Any = None) -> Any:
        """
        Return a default value for a given key.

        Keys may have a default value, or a default *factory* has been specified.

        :param key: key to look for.
        :param default: when key has no default value, ``default`` is returned.
        :returns: a default value defined for the key, or its ``default_factory``'s
            return value of ``default_factory``, or ``default`` when key has no
            default value.
        """

        for field in container_fields(cls):
            if key != field.name:
                continue

            if not isinstance(field.default_factory, dataclasses._MISSING_TYPE):
                return field.default_factory()

            if not isinstance(field.default, dataclasses._MISSING_TYPE):
                return field.default

        else:
            return default

    @property
    def is_bare(self) -> bool:
        """
        Check whether all keys are either unset or have their default value.

        :returns: ``True`` if all keys either hold their default value
            or are not set at all, ``False`` otherwise.
        """

        for field in container_fields(self):
            value = getattr(self, field.name)

            if not isinstance(field.default_factory, dataclasses._MISSING_TYPE):
                if value != field.default_factory():
                    return False

            elif not isinstance(field.default, dataclasses._MISSING_TYPE):
                if value != field.default:
                    return False

            else:
                pass

        return True


#: A typevar bound to spec-based container base class. A stand-in for all classes
#: derived from :py:class:`SpecBasedContainer`.
SpecBasedContainerT = TypeVar(
    'SpecBasedContainerT',
    # ignore[type-arg]: generic bounds are not supported by mypy.
    bound='SpecBasedContainer')  # type: ignore[type-arg]

# It may look weird, having two different typevars for "spec", but it does make
# sense: tmt is fairly open to what it accepts, e.g. "a string or a list of
# strings". This is the input part of the flow. But then the input is normalized,
# and the output may be just a subset of types tmt is willing to accept. For
# example, if `tag` can be either a string or a list of strings, when processed
# by tmt and converted back to spec, a list of strings is the only output, even
# if the original was a single string. Therefore `SpecBasedContainer` accepts
# two types, one for each direction. Usually, the output one would be a subset
# of the input one.

#: A typevar representing an *input* specification consumed by :py:class:`SpecBasedContainer`.
SpecInT = TypeVar('SpecInT')
#: A typevar representing an *output* specification produced by :py:class:`SpecBasedContainer`.
SpecOutT = TypeVar('SpecOutT')


class SpecBasedContainer(Generic[SpecInT, SpecOutT], DataContainer):
    @classmethod
    def from_spec(cls: type[SpecBasedContainerT], spec: SpecInT) -> SpecBasedContainerT:
        """
        Convert from a specification file or from a CLI option

        See https://tmt.readthedocs.io/en/stable/code/classes.html#class-conversions
        for more details.

        See :py:meth:`to_spec` for its counterpart.
        """

        raise NotImplementedError

    def to_spec(self) -> SpecOutT:
        """
        Convert to a form suitable for saving in a specification file

        See https://tmt.readthedocs.io/en/stable/code/classes.html#class-conversions
        for more details.

        See :py:meth:`from_spec` for its counterpart.
        """

        return cast(SpecOutT, self.to_dict())

    def to_minimal_spec(self) -> SpecOutT:
        """
        Convert to specification, skip default values

        See https://tmt.readthedocs.io/en/stable/code/classes.html#class-conversions
        for more details.

        See :py:meth:`from_spec` for its counterpart.
        """

        return cast(SpecOutT, self.to_minimal_dict())


SerializableContainerDerivedType = TypeVar(
    'SerializableContainerDerivedType',
    bound='SerializableContainer')


@dataclasses.dataclass
class SerializableContainer(DataContainer):
    """ A mixin class for saving and loading objects """

    @classmethod
    def default(cls, key: str, default: Any = None) -> Any:
        return cls._default(key, default=default)

    #
    # Moving data between containers and objects owning them
    #

    def inject_to(self, obj: Any) -> None:
        """ Inject keys from this container into attributes of a given object """

        for name, value in self.items():
            setattr(obj, name, value)

    @classmethod
    def extract_from(cls: type[SerializableContainerDerivedType],
                     obj: Any) -> SerializableContainerDerivedType:
        """ Extract keys from given object, and save them in a container """

        data = cls()
        # SIM118: Use `{key} in {dict}` instead of `{key} in {dict}.keys()`
        # "NormalizeKeysMixin" has no attribute "__iter__" (not iterable)
        for key in cls.keys():  # noqa: SIM118
            value = getattr(obj, key)
            if value is not None:
                setattr(data, key, value)

        return data

    #
    # Serialization - writing containers into YAML files, and restoring
    # them later.
    #

    def to_serialized(self) -> dict[str, Any]:
        """
        Convert to a form suitable for saving in a file.

        See https://tmt.readthedocs.io/en/stable/code/classes.html#class-conversions
        for more details.

        See :py:meth:`from_serialized` for its counterpart.
        """

        def _produce_serialized() -> Iterator[tuple[str, Any]]:
            for key in container_keys(self):
                _, option, value, _, metadata = container_field(self, key)

                if metadata.serialize_callback:
                    yield option, metadata.serialize_callback(value)

                else:
                    yield option, value

        serialized = dict(_produce_serialized())

        # Add a special field tracking what class we just shattered to pieces.
        serialized['__class__'] = {
            'module': self.__class__.__module__,
            'name': self.__class__.__name__
            }

        return serialized

    @classmethod
    def from_serialized(
            cls: type[SerializableContainerDerivedType],
            serialized: dict[str, Any]) -> SerializableContainerDerivedType:
        """
        Convert from a serialized form loaded from a file.

        See https://tmt.readthedocs.io/en/stable/code/classes.html#class-conversions
        for more details.

        See :py:meth:`to_serialized` for its counterpart.
        """

        # Our special key may or may not be present, depending on who
        # calls this method.  In any case, it is not needed, because we
        # already know what class to restore: this one.
        serialized.pop('__class__', None)

        def _produce_unserialized() -> Iterator[tuple[str, Any]]:
            for option, value in serialized.items():
                key = option_to_key(option)

                _, _, _, _, metadata = container_field(cls, key)

                if metadata.unserialize_callback:
                    yield key, metadata.unserialize_callback(value)

                else:
                    yield key, value

        # Set attribute by adding it to __dict__ directly. Messing with setattr()
        # might cause reuse of mutable values by other instances.
        # obj.__dict__[keyname] = unserialize_callback(value)

        return cls(**dict(_produce_unserialized()))

    # ignore[misc,type-var]: mypy is correct here, method does return a
    # TypeVar, but there is no way to deduce the actual type, because
    # the method is static. That's on purpose, method tries to find the
    # class to unserialize, therefore it's simply unknown. Returning Any
    # would make mypy happy, but we do know the return value will be
    # derived from SerializableContainer. We can mention that, and
    # silence mypy about the missing actual type.
    @staticmethod
    def unserialize(
            serialized: dict[str, Any],
            logger: tmt.log.Logger
            ) -> SerializableContainerDerivedType:  # type: ignore[misc,type-var]
        """
        Convert from a serialized form loaded from a file.

        Similar to :py:meth:`from_serialized`, but this method knows
        nothing about container's class, and will locate the correct
        module and class by inspecting serialized data. Discovered
        class' :py:meth:`from_serialized` is then used to create the
        container.

        Used to transform data read from a YAML file into original
        containers when their classes are not know to the code.
        Restoring such containers requires inspection of serialized data
        and dynamic imports of modules as needed.

        See https://tmt.readthedocs.io/en/stable/code/classes.html#class-conversions
        for more details.

        See :py:meth:`to_serialized` for its counterpart.
        """

        from tmt.plugins import import_member

        # Unpack class info, to get nicer variable names
        if "__class__" not in serialized:
            raise GeneralError(
                "Failed to load saved state, probably because of old data format.\n"
                "Use 'tmt clean runs' to clean up old runs.")

        klass_info = serialized.pop('__class__')
        klass = import_member(
            module=klass_info['module'],
            member=klass_info['name'],
            logger=logger)[1]

        # Stay away from classes that are not derived from this one, to
        # honor promise given by return value annotation.
        assert issubclass(klass, SerializableContainer)

        # Apparently, the issubclass() check above is not good enough for mypy.
        return cast(SerializableContainerDerivedType, klass.from_serialized(serialized))


def markdown_to_html(filename: Path) -> str:
    """
    Convert markdown to html

    Expects: Markdown document as a file.
    Returns: An HTML document as a string.
    """
    try:
        import markdown
    except ImportError:
        raise ConvertError("Install tmt+test-convert to export tests.")

    try:
        with open(filename) as file:
            try:
                text = file.read()
            except UnicodeError:
                raise MetadataError(f"Unable to read '{filename}'.")
            return markdown.markdown(text)
    except OSError:
        raise ConvertError(f"Unable to open '{filename}'.")


def shell_variables(
        data: Union[list[str], tuple[str, ...], dict[str, Any]]) -> list[str]:
    """
    Prepare variables to be consumed by shell

    Convert dictionary or list/tuple of key=value pairs to list of
    key=value pairs where value is quoted with shlex.quote().
    """

    # Convert from list/tuple
    if isinstance(data, (list, tuple)):
        converted_data = []
        for item in data:
            splitted_item = item.split('=')
            key = splitted_item[0]
            value = shlex.quote('='.join(splitted_item[1:]))
            converted_data.append(f'{key}={value}')
        return converted_data

    # Convert from dictionary
    return [f"{key}={shlex.quote(str(value))}" for key, value in data.items()]


def duration_to_seconds(duration: str) -> int:
    """ Convert extended sleep time format into seconds """
    units = {
        's': 1,
        'm': 60,
        'h': 60 * 60,
        'd': 60 * 60 * 24,
        }
    # Couldn't create working validation regexp to accept '2 1m 4'
    # thus fixing the string so \b can be used as word boundary
    fixed_duration = re.sub(r'([smhd])(\d)', r'\1 \2', str(duration))
    fixed_duration = re.sub(r'\s\s+', ' ', fixed_duration)
    raw_groups = r'''
            (   # Group all possibilities
                (  # Multiply by float number
                    (?P<asterisk>\*) # "*" character
                                \s*
                    (?P<float>\d+(\.\d+)?(?![smhd])) # float part
                                \s*
                )
                |   # Or
                ( # Time pattern
                    (?P<digit>\d+)  # digits
                    \s*
                    (?P<suffix>[smhd])? # suffix
                    \s*
                )
            )\b # Needs to end with word boundary to avoid splitting
        '''
    re_validate = re.compile(r'''
        ^(  # Match beginning, opening of input group
        ''' + raw_groups + r'''
        \s* # Optional spaces in the case of multiple inputs
        )+$ # Inputs can repeat
        ''', re.VERBOSE)
    re_split = re.compile(raw_groups, re.VERBOSE)
    if re_validate.match(fixed_duration) is None:
        raise SpecificationError(f"Invalid duration '{duration}'.")
    total_time = 0
    multiply_by = 1.0
    for match in re_split.finditer(fixed_duration):
        if match['asterisk'] == '*':
            multiply_by *= float(match['float'])
        else:
            total_time += int(match['digit']) * units.get(match['suffix'], 1)
    # Multiply in the end and round up
    return ceil(total_time * multiply_by)


@overload
def verdict(
        decision: bool,
        comment: Optional[str] = None,
        good: str = 'pass',
        bad: str = 'fail',
        problem: str = 'warn',
        **kwargs: Any) -> bool:
    pass


@overload
def verdict(
        decision: None,
        comment: Optional[str] = None,
        good: str = 'pass',
        bad: str = 'fail',
        problem: str = 'warn',
        **kwargs: Any) -> None:
    pass


def verdict(
        decision: Optional[bool],
        comment: Optional[str] = None,
        good: str = 'pass',
        bad: str = 'fail',
        problem: str = 'warn',
        **kwargs: Any) -> Optional[bool]:
    """
    Print verdict in green, red or yellow based on the decision

    The supported decision values are:

        True .... good (green)
        False ... bad (red)
        None .... problem (yellow)

    Anything else raises an exception. Additional arguments
    are passed to the `echo` function. Returns back the decision.
    """

    if decision is False:
        text = style(bad, fg='red')
    elif decision is True:
        text = style(good, fg='green')
    elif decision is None:
        text = style(problem, fg='yellow')
    else:
        raise GeneralError(
            "Invalid decision value, must be 'True', 'False' or 'None'.")
    if comment:
        text = text + ' ' + comment
    echo(text, **kwargs)
    return decision


#
# Value formatting a.k.a. pretty-print
#
# (And `pprint` is ugly and `dict_to_yaml` too YAML-ish...)
#
# NOTE: there are comments prefixed by "UX": these try to document
# various tweaks and "exceptions" we need to employ to produce nicely
# readable output for common inputs and corner cases.
#

FormatWrap = Literal[True, False, 'auto']


class ListFormat(enum.Enum):
    """ How to format lists """

    #: Use :py:func:`fmf.utils.listed`.
    LISTED = enum.auto()

    #: Produce comma-separated list.
    SHORT = enum.auto()

    #: One list item per line.
    LONG = enum.auto()


#: How dictionary key/value pairs are indented in their container.
_FORMAT_VALUE_DICT_ENTRY_INDENT = ' ' * INDENT
#: How list items are indented below their container.
_FORMAT_VALUE_LIST_ENTRY_INDENT = '  - '


def assert_window_size(window_size: Optional[int]) -> None:
    """
    Raise an exception if window size is zero or a negative integer.

    Protects possible underflows in formatters employed by :py:func:`format_value`.
    """

    if window_size is None or window_size > 0:
        return

    raise GeneralError(
        f"Allowed width of terminal exhausted, output cannot fit into {OUTPUT_WIDTH} columns.")


def _format_bool(
        value: bool,
        window_size: Optional[int],
        key_color: Optional[str],
        list_format: ListFormat,
        wrap: FormatWrap) -> Iterator[str]:
    """ Format a ``bool`` value """

    assert_window_size(window_size)

    yield 'true' if value else 'false'


def _format_list(
        value: list[Any],
        window_size: Optional[int],
        key_color: Optional[str],
        list_format: ListFormat,
        wrap: FormatWrap) -> Iterator[str]:
    """ Format a list """

    assert_window_size(window_size)

    # UX: if the list is empty, don't bother checking `listed()` or counting
    # spaces.
    if not value:
        yield '[]'
        return

    # UX: if there's just a single item, it's also a trivial case.
    if len(value) == 1:
        yield '\n'.join(_format_value(
            value[0],
            window_size=window_size,
            key_color=key_color,
            wrap=wrap))
        return

    # Render each item in the list. We get a list of possibly multiline strings,
    # one for each item in `value`.
    formatted_items = [
        '\n'.join(_format_value(item, window_size=window_size, key_color=key_color, wrap=wrap))
        for item in value
        ]

    # There are nice ways how to format a string, but those can be tried out
    # only when:
    #
    # * there is no multiline item,
    # * there is no item containing a space,
    # * the window size has been set.
    #
    # If one of these conditions is violated, we fall back to one-item-per-line
    # rendering.
    has_multiline = any('\n' in item for item in formatted_items)
    has_space = any(' ' in item for item in formatted_items)

    if not has_multiline and not has_space and window_size:
        if list_format is ListFormat.LISTED:
            listed_value: str = fmf.utils.listed(formatted_items, quote="'")

            # UX: an empty list, as an item, would be rendered as "[]". Thanks
            # to `quote="'"`, it would be wrapped with quotes, but that looks
            # pretty ugly: foo: 'bar', 'baz' and '[]'. Drop the quotes to make
            # the output a bit nicer.
            listed_value = listed_value.replace("'[]'", '[]')

            if len(listed_value) < window_size:
                yield listed_value
                return

        elif list_format is ListFormat.SHORT:
            short_value = ', '.join(formatted_items)

            if len(short_value) < window_size:
                yield short_value
                return

    yield from formatted_items


def _format_str(
        value: str,
        window_size: Optional[int],
        key_color: Optional[str],
        list_format: ListFormat,
        wrap: FormatWrap) -> Iterator[str]:
    """ Format a string """

    assert_window_size(window_size)

    # UX: if the window size is known, rewrap lines to fit in. Otherwise, put
    # each line on its own, well, line.
    # Work with *paragraphs* - lines within a paragraph may get reformatted to
    # fit the line, but we should preserve empty lines between paragraps as
    # much as possible.
    is_multiline = bool('\n' in value)

    if window_size:
        for paragraph in value.rstrip().split('\n\n'):
            stripped_paragraph = paragraph.rstrip()

            if not stripped_paragraph:
                yield ''

            elif wrap is False:
                yield stripped_paragraph

                if is_multiline:
                    yield ''

            else:
                if all(len(line) <= window_size for line in stripped_paragraph.splitlines()):
                    yield from stripped_paragraph.splitlines()

                else:
                    yield from textwrap.wrap(stripped_paragraph, width=window_size)

                if is_multiline:
                    yield ''

    elif not value.rstrip():
        yield ''

    else:
        yield from value.rstrip().split('\n')


def _format_dict(
        value: dict[Any, Any],
        window_size: Optional[int],
        key_color: Optional[str],
        list_format: ListFormat,
        wrap: FormatWrap) -> Iterator[str]:
    """ Format a dictionary """

    assert_window_size(window_size)

    # UX: if the dictionary is empty, it's trivial to render.
    if not value:
        yield '{}'
        return

    for k, v in value.items():
        # First, render the key.
        k_formatted = click.style(k, fg=key_color) if key_color else k
        k_size = len(k) + 2

        # Then, render the value. If the window size is known, the value must be
        # propagated, but it must be updated to not include the space consumed by
        # key.
        if window_size:
            v_formatted = _format_value(
                v,
                window_size=window_size - k_size,
                key_color=key_color,
                wrap=wrap)
        else:
            v_formatted = _format_value(
                v,
                key_color=key_color,
                wrap=wrap)

        # Now attach key and value in a nice and respectful way.
        if len(v_formatted) == 0:
            # This should never happen, even an empty list should be
            # formatted as a list with one item.
            raise AssertionError

        def _emit_list_entries(lines: list[str]) -> Iterator[str]:
            for i, line in enumerate(lines):
                if i == 0:
                    yield f'{_FORMAT_VALUE_LIST_ENTRY_INDENT}{line}'

                else:
                    yield f'{_FORMAT_VALUE_DICT_ENTRY_INDENT}{line}'

        def _emit_dict_entry(lines: list[str]) -> Iterator[str]:
            yield from (f'{_FORMAT_VALUE_DICT_ENTRY_INDENT}{line}' for line in lines)

        # UX: special handling of containers with just a single item, i.e. the
        # key value fits into a single line of text.
        if len(v_formatted) == 1:
            # UX: special tweaks when `v` is a dictionary
            if isinstance(v, dict):
                # UX: put the `v` on its own line. This way, we get `k` followed
                # by a nested and indented key/value pair.
                #
                # foo:
                #     bar: ...
                if v:
                    yield f'{k_formatted}:'
                    yield from _emit_dict_entry(v_formatted)

                # UX: an empty dictionary shall lead to just a key being emitted
                #
                # foo:<nothing>
                else:
                    yield f'{k_formatted}:'

            # UX: special tweaks when `v` is a list
            elif isinstance(v, list):
                # UX: put both key and value on the same line. We have a list
                # with a single item, trivial case.
                if v:
                    lines = v_formatted[0].splitlines()

                    # UX: If there is just a single line, put key and value on the
                    # same line.
                    if len(lines) <= 1:
                        yield f'{k_formatted}: {lines[0]}'

                    # UX: Otherwise, put lines under the key, and mark the first
                    # line with the list-entry prefix to make it clear the key
                    # holds a list. Remaining lines are indented as well.
                    else:
                        yield f'{k_formatted}:'
                        yield from _emit_list_entries(lines)

                # UX: an empty list, just like an empty dictionary, shall lead to
                # just a key being emitted
                #
                # foo:<nothing>
                else:
                    yield f'{k_formatted}:'

            # UX: every other type
            else:
                lines = v_formatted[0].splitlines()

                # UX: If there is just a single line, put key and value on the
                # same line.
                if not lines:
                    yield f'{k_formatted}:'

                elif len(lines) == 1:
                    yield f'{k_formatted}: {lines[0]}'

                # UX: Otherwise, put lines under the key, and indent them.
                else:
                    yield f'{k_formatted}:'
                    yield from _emit_dict_entry(lines)

        # UX: multi-item dictionaries are much less complicated, there is no
        # chance to simplify the output. Each key would land on its own line,
        # with content well-aligned.
        else:
            yield f'{k_formatted}:'

            # UX: when rendering a list, indent the lines properly with the
            # first one
            if isinstance(v, list):
                for item in v_formatted:
                    yield from _emit_list_entries(item.splitlines())

            else:
                yield from _emit_dict_entry(v_formatted)


#: A type describing a per-type formatting helper.
ValueFormatter = Callable[
    [Any, Optional[int], Optional[str], ListFormat, FormatWrap],
    Iterator[str]
    ]


#: Available formatters, as ``type``/``formatter`` pairs. If a value is instance
#: of ``type``, the ``formatter`` is called to render it.
_VALUE_FORMATTERS: list[tuple[Any, ValueFormatter]] = [
    (bool, _format_bool),
    (str, _format_str),
    (list, _format_list),
    (dict, _format_dict),
    ]


def _format_value(
        value: Any,
        window_size: Optional[int] = None,
        key_color: Optional[str] = None,
        list_format: ListFormat = ListFormat.LISTED,
        wrap: FormatWrap = 'auto') -> list[str]:
    """
    Render a nicely-formatted string representation of a value.

    A main workhorse for :py:func:`format_value` and value formatters
    defined for various types. This function is responsible for
    picking the right one.

    :param value: an object to format.
    :param window_size: if set, rendering will try to produce
        lines whose length would not exceed ``window_size``. A
        window not wide enough may result into not using
        :py:func:`fmf.utils.listed`, or wrapping lines in a text
        paragraph.
    :param key_color: if set, dictionary keys would be colorized by
        this color.
    :param list_format: preferred list formatting. It may be ignored
        if ``window_size`` is set and not wide enough to hold the
        desired formatting; :py:member:`ListFormat.LONG` would be
        the fallback choice.
    :returns: a list of lines representing the formatted string
        representation of ``value``.
    """

    assert_window_size(window_size)

    for type_, formatter in _VALUE_FORMATTERS:
        if isinstance(value, type_):
            return list(formatter(value, window_size, key_color, list_format, wrap))

    return [str(value)]


def format_value(
        value: Any,
        window_size: Optional[int] = None,
        key_color: Optional[str] = None,
        list_format: ListFormat = ListFormat.LISTED,
        wrap: FormatWrap = 'auto') -> str:
    """
    Render a nicely-formatted string representation of a value.

    :param value: an object to format.
    :param window_size: if set, rendering will try to produce
        lines whose length would not exceed ``window_size``. A
        window not wide enough may result into not using
        :py:func:`fmf.utils.listed`, or wrapping lines in a text
        paragraph.
    :param key_color: if set, dictionary keys would be colorized by
        this color.
    :param list_format: preferred list formatting. It may be ignored
        if ``window_size`` is set and not wide enough to hold the
        desired formatting; :py:attr:`ListFormat.LONG` would be
        the fallback choice.
    :returns: a formatted string representation of ``value``.
    """

    assert_window_size(window_size)

    formatted_value = _format_value(
        value,
        window_size=window_size,
        key_color=key_color,
        list_format=list_format,
        wrap=wrap)

    # UX: post-process lists: this top-level is the "container" of the list,
    # and therefore needs to apply indentation and prefixes.
    if isinstance(value, list):
        # UX: an empty list should be represented as an empty string.
        # We get a nice `foo <nothing>` from `format()` under
        # various `show` commands.
        if not value:
            return ''

        # UX: if there is just a single formatted item, prefixing it with `-`
        # would not help readability.
        if len(value) == 1:
            return formatted_value[0]

        # UX: if there are multiple items, we do not add prefixes as long as
        # there are no multi-line items - once there is just a single one item
        # rendered across multiple lines, we need to add `-` prefix & indentation
        # to signal where items start and end visually.
        if len(value) > 1 and any('\n' in formatted_item for formatted_item in formatted_value):
            prefixed: list[str] = []

            for item in formatted_value:
                for i, line in enumerate(item.splitlines()):
                    if i == 0:
                        prefixed.append(f'- {line}')

                    else:
                        prefixed.append(f'  {line}')

            return '\n'.join(prefixed)

    return '\n'.join(formatted_value)


def format(
        key: str,
        value: Union[None, float, bool, str, list[Any], dict[Any, Any]] = None,
        indent: int = 24,
        window_size: int = OUTPUT_WIDTH,
        wrap: FormatWrap = 'auto',
        key_color: Optional[str] = 'green',
        value_color: Optional[str] = 'black',
        list_format: ListFormat = ListFormat.LISTED) -> str:
    """
    Nicely format and indent a key-value pair

    :param key: a key introducing the value.
    :param value: an object to format.
    :param indent: the key would be right-justified to this column.
    :param window_size: rendering will try to fit produce lines
        whose length would exceed ``window_size``. A window not wide
        enough may result into not using :py:func:`fmf.utils.listed`
        for lists, or wrapping lines in a text paragraph.
    :param wrap: if set to ``True``, always reformat text and wrap
        long lines; if set to ``False``, preserve text formatting
        and make no changes; the default, ``auto``, tries to rewrap
        lines as needed to obey ``window_size``.
    :param key_color: if set, dictionary keys would be colorized by
        this color.
    :param list_format: preferred list formatting. It may be ignored
        if ``window_size`` is set and not wide enough to hold the
        desired formatting; :py:attr:`ListFormat.LONG` would be
        the fallback choice.
    :returns: a formatted string representation of ``value``.
    """

    assert_window_size(window_size)

    indent_string = (indent + 1) * ' '

    # Format the key first
    output = f"{str(key).rjust(indent, ' ')} "
    if key_color is not None:
        output = style(output, fg=key_color)

    # Then the value
    formatted_value = format_value(
        value,
        window_size=window_size - indent,
        key_color=key_color,
        list_format=list_format,
        wrap=wrap)

    # A special care must be taken when joining key and some types of values
    if isinstance(value, list):
        value_as_lines = formatted_value.splitlines()

        if len(value_as_lines) == 1:
            return output + formatted_value

        return output + ('\n' + indent_string).join(value_as_lines)

    if isinstance(value, dict):
        return output + ('\n' + indent_string).join(formatted_value.splitlines())

    # TODO: the whole text wrap should be handled by the `_format_value()`!
    if isinstance(value, str):
        value_as_lines = formatted_value.splitlines()

        # Undo the line rewrapping. This would be resolved once `_format_value`
        # takes over.
        if wrap is False:
            return output + ''.join(value_as_lines)

        # In 'auto' mode enable wrapping when long lines present
        if wrap == 'auto':
            wrap = any(len(line) + indent - 7 > window_size for line in value_as_lines)

        if wrap:
            return output \
                + wrap_text(
                    value,
                    width=window_size,
                    preserve_paragraphs=True,
                    initial_indent=indent_string,
                    subsequent_indent=indent_string).lstrip()

        return output + ('\n' + indent_string).join(value_as_lines)

    return output + formatted_value


def create_directory(
        *,
        path: Path,
        name: str,
        dry: bool = False,
        quiet: bool = False,
        logger: tmt.log.Logger) -> None:
    """
    Create a new directory.

    Before creating the directory, function checks whether it exists
    already - the existing directory is **not** removed and re-created.

    The outcome of the operation will be logged in a debug log, but
    may also be sent to console with ``quiet=False``.

    :param path: a path to be created.
    :param name: a "label" of the path, used for logging.
    :param dry: if set, directory would not be created. Still, the
        existence check will happen.
    :param quiet: if set, an outcome of the operation would not be logged
        to console.
    :param logger: logger to use for logging.
    :raises FileError: when function tried to create the directory,
        but failed.
    """

    # Streamline the logging a bit: wrap the creating with a function returning
    # a message & optional exception. Later we will send the message to debug
    # log, and maybe also to console.
    def _create_directory() -> tuple[str, Optional[Exception]]:
        if path.is_dir():
            return (f"{name.capitalize()} '{path}' already exists.", None)

        if dry:
            return (f"{name.capitalize()} '{path}' would be created.", None)

        try:
            path.mkdir(exist_ok=True, parents=True)

        except OSError as error:
            return (f"Failed to create {name} '{path}'.", error)

        return (f"{name.capitalize()} '{path}' created.", None)

    message, exc = _create_directory()

    if exc:
        raise FileError(message) from exc

    logger.debug(message)

    if quiet:
        return

    echo(message)


def create_file(
        *,
        path: Path,
        content: str,
        name: str,
        dry: bool = False,
        force: bool = False,
        mode: int = 0o664,
        quiet: bool = False,
        logger: tmt.log.Logger) -> None:
    """
    Create a new file.

    Before creating the file, function checks whether it exists
    already - the existing file is **not** removed and re-created,
    unless ``force`` is set.

    The outcome of the operation will be logged in a debug log, but
    may also be sent to console with ``quiet=False``.

    :param path: a path to be created.
    :param content: content to save into the file
    :param name: a "label" of the path, used for logging.
    :param dry: if set, the file would not be created or overwritten. Still,
        the existence check will happen.
    :param force: if set, the file would be overwritten if it already exists.
    :param mode: permissions to set for the file.
    :param quiet: if set, an outcome of the operation would not be logged
        to console.
    :param logger: logger to use for logging.
    :raises FileError: when function tried to create the file,
        but failed.
    """

    # Streamline the logging a bit: wrap the creating with a function returning
    # a message & optional exception. Later we will send the message to debug
    # log, and maybe also to console.
    def _create_file() -> tuple[str, Optional[Exception]]:
        # When overwriting an existing path, we need to provide different message.
        # Let's save the action taken for logging.
        action: str = 'created'

        if path.exists():
            if not force:
                message = f"{name.capitalize()} '{path}' already exists."

                # Return a custom exception - it was not raised by any FS-related code,
                # but we need to signal the operation failed to our caller.
                return message, FileExistsError(message)

            action = 'overwritten'

        if dry:
            return f"{name.capitalize()} '{path}' would be {action}.", None

        try:
            path.write_text(content)
            path.chmod(mode)

        except OSError as error:
            return f"Failed to create {name} '{path}'.", error

        return f"{name.capitalize()} '{path}' {action}.", None

    message, exc = _create_file()

    if exc:
        raise FileError(message) from exc

    logger.debug(message)

    if quiet:
        return

    echo(message)


@functools.cache
def fmf_id(
        *,
        name: str,
        fmf_root: Path,
        always_get_ref: bool = False,
        logger: tmt.log.Logger) -> 'tmt.base.FmfId':
    """ Return full fmf identifier of the node """

    def run(command: Command) -> str:
        """ Run command, return output """
        try:
            result = command.run(cwd=fmf_root, logger=logger)
            if result.stdout is None:
                return ""
            return result.stdout.strip()
        except RunError:
            # Always return an empty string in case 'git' command is run in a non-git repo
            return ""

    from tmt.base import FmfId

    fmf_id = FmfId(fmf_root=fmf_root, name=name)

    # Prepare url (for now handle just the most common schemas)
    branch = run(Command("git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"))
    try:
        remote_name = branch[:branch.index('/')]
    except ValueError:
        remote_name = 'origin'
    remote = run(Command("git", "config", "--get", f"remote.{remote_name}.url"))

    from tmt.utils.git import default_branch, git_root, public_git_url
    fmf_id.url = public_git_url(remote) if remote else None

    # Construct path (if different from git root)
    fmf_id.git_root = git_root(fmf_root=fmf_root, logger=logger)

    if fmf_id.git_root:
        if fmf_id.git_root.resolve() != fmf_root.resolve():
            fmf_id.path = Path('/') / fmf_root.relative_to(fmf_id.git_root)

        # Get the ref (skip for the default)
        fmf_id.default_branch = default_branch(repository=fmf_id.git_root, logger=logger)
        if fmf_id.default_branch is None:
            fmf_id.ref = None
        else:
            ref = run(Command("git", "rev-parse", "--abbrev-ref", "HEAD"))
            if ref != fmf_id.default_branch or always_get_ref:
                fmf_id.ref = ref
            else:
                # Note that it is a valid configuration without having a default
                # branch here. Consumers of returned fmf_id object should check
                # the fmf_id contains everything they need.
                fmf_id.ref = None

    return fmf_id


class TimeoutHTTPAdapter(requests.adapters.HTTPAdapter):
    """ Spice up request's session with custom timeout """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.timeout = kwargs.pop('timeout', None)

        super().__init__(*args, **kwargs)

    # ignore[override]: signature does not match superclass on purpose.
    # send() does declare plenty of parameters we do not care about.
    def send(  # type: ignore[override]
            self,
            request: requests.PreparedRequest,
            **kwargs: Any) -> requests.Response:
        """
        Send request.

        All arguments are passed to superclass after enforcing the timeout.

        :param request: the request to send.
        """

        kwargs.setdefault('timeout', self.timeout)

        return super().send(request, **kwargs)


class RetryStrategy(urllib3.util.retry.Retry):
    def increment(
            self,
            *args: Any,
            **kwargs: Any
            ) -> urllib3.util.retry.Retry:
        error = cast(Optional[Exception], kwargs.get('error', None))

        # Detect a subset of exception we do not want to follow with a retry.
        # SIM102: Use a single `if` statement instead of nested `if` statements. Keeping for
        # readability.
        if error is not None:  # noqa: SIM102
            # Failed certificate verification - this issue will probably not get any better
            # should we try again.
            if isinstance(error, urllib3.exceptions.SSLError) \
                    and 'certificate verify failed' in str(error):

                # [mpr] I'm not sure how stable this *iternal* API is, but pool seems to be the
                # only place aware of the remote hostname. Try our best to get the hostname for
                # a better error message, but don't crash because of a missing attribute or
                # something as dumb.

                connection_pool = kwargs.get('_pool', None)

                if connection_pool is not None and hasattr(connection_pool, 'host'):
                    message = f"Certificate verify failed for '{connection_pool.host}'."
                else:
                    message = 'Certificate verify failed.'

                raise GeneralError(message) from error

        return super().increment(*args, **kwargs)


# ignore[type-arg]: base class is a generic class, but we cannot list
# its parameter type, because in Python 3.6 the class "is not subscriptable".
class retry_session(contextlib.AbstractContextManager):  # type: ignore[type-arg]  # noqa: N801
    """ Context manager for :py:class:`requests.Session` with retries and timeout """

    @staticmethod
    def create(
            retries: int = DEFAULT_RETRY_SESSION_RETRIES,
            backoff_factor: float = DEFAULT_RETRY_SESSION_BACKOFF_FACTOR,
            allowed_methods: Optional[tuple[str, ...]] = None,
            status_forcelist: Optional[tuple[int, ...]] = None,
            timeout: Optional[int] = None
            ) -> requests.Session:

        # `method_whitelist`` has been renamed to `allowed_methods` since
        # urllib3 1.26, and it will be removed in urllib3 2.0.
        # `allowed_methods` is therefore the future-proof name, but for the
        # sake of backward compatibility, internally might need to use the
        # deprecated parameter.
        if urllib3.__version__.startswith('1.'):
            retry_strategy = RetryStrategy(
                total=retries,
                status_forcelist=status_forcelist,
                method_whitelist=allowed_methods,
                backoff_factor=backoff_factor)

        else:
            retry_strategy = RetryStrategy(
                total=retries,
                status_forcelist=status_forcelist,
                allowed_methods=allowed_methods,
                backoff_factor=backoff_factor)

        if timeout is not None:
            http_adapter: requests.adapters.HTTPAdapter = TimeoutHTTPAdapter(
                timeout=timeout, max_retries=retry_strategy)
        else:
            http_adapter = requests.adapters.HTTPAdapter(
                max_retries=retry_strategy)

        session = requests.Session()
        session.mount('http://', http_adapter)
        session.mount('https://', http_adapter)

        return session

    def __init__(
            self,
            retries: int = DEFAULT_RETRY_SESSION_RETRIES,
            backoff_factor: float = DEFAULT_RETRY_SESSION_BACKOFF_FACTOR,
            allowed_methods: Optional[tuple[str, ...]] = None,
            status_forcelist: Optional[tuple[int, ...]] = None,
            timeout: Optional[int] = None
            ) -> None:
        self.retries = retries
        self.backoff_factor = backoff_factor
        self.allowed_methods = allowed_methods
        self.status_forcelist = status_forcelist
        self.timeout = timeout

    def __enter__(self) -> requests.Session:
        return self.create(
            retries=self.retries,
            backoff_factor=self.backoff_factor,
            allowed_methods=self.allowed_methods,
            status_forcelist=self.status_forcelist,
            timeout=self.timeout)

    def __exit__(self, *args: object) -> None:
        pass


def remove_color(text: str) -> str:
    """ Remove ansi color sequences from the string """
    return re.sub(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])', '', text)


def generate_runs(
        path: Path,
        id_: tuple[str, ...]) -> Iterator[Path]:
    """ Generate absolute paths to runs from path """
    # Prepare absolute workdir path if --id was used
    run_path = None
    for id_name in id_:
        if id_name:
            run_path = Path(id_name)
            if '/' not in id_name:
                run_path = path / run_path
            if run_path.is_absolute() and run_path.exists():
                yield run_path
        else:
            raise tmt.utils.GeneralError("Value of '--id' option cannot be an empty string.")
    if run_path:
        return
    if not path.exists():
        return
    for childpath in path.iterdir():
        abs_child_path = childpath.absolute()
        # If id_ is None, the abs_path is considered valid (no filtering
        # is being applied). If it is defined, it has been transformed
        # to absolute path and must be equal to abs_path for the run
        # in abs_path to be generated.
        invalid_id = id_ and str(abs_child_path) not in id_
        invalid_run = not abs_child_path.joinpath('run.yaml').exists()
        if not abs_child_path.is_dir() or invalid_id or invalid_run:
            continue
        yield abs_child_path


def load_run(run: 'tmt.base.Run') -> tuple[bool, Optional[Exception]]:
    """ Load a run and its steps from the workdir """
    try:
        run.load_from_workdir()

        for plan in run.plans:
            for step in plan.steps(enabled_only=False):
                step.load()

    except GeneralError as error:
        return False, error

    return True, None


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#  StructuredField
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

SFSectionValueType = Union[str, list[str]]


class StructuredField:
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
    names. Here's an example of a simple StructuredField:

    .. code-block:: ini

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
    surrounding text and escapes any section-like lines in the content:

    .. code-block:: ini

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
    the ini config format:

    .. code-block:: ini

        [section]
        key1 = value1
        key2 = value2
        key3 = value3

    Provide the key name as the optional argument 'item' when accessing
    these single-line items. Note that the section cannot contain both
    plain text data and key-value pairs.

    .. code-block:: python

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
    of a single string. Similarly use list for setting multiple values:

    .. code-block:: python

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

    def __init__(
            self,
            text: Optional[str] = None,
            version: int = 1,
            multi: bool = False) -> None:
        """ Initialize the structured field """
        self.version(version)
        self._header: str = ""
        self._footer: str = ""
        # Sections are internally stored in their serialized form, i.e. as
        # strings.
        self._sections: dict[str, str] = {}
        self._order: list[str] = []
        self._multi = multi
        if text is not None:
            self.load(text)

    def __iter__(self) -> Iterator[str]:
        """ By default iterate through all available section names """
        yield from self._order

    def __nonzero__(self) -> bool:
        """ True when any section is defined """
        return len(self._order) > 0

    __bool__ = __nonzero__

    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    #  StructuredField Private
    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    def _load_version_zero(self, text: str) -> None:
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

    def _load(self, text: str) -> None:
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
            log.debug(f"Parsed header:\n{self._header}")
        self._footer = re.sub("^\n", "", matched.groups()[2])
        if self._footer:
            log.debug(f"Parsed footer:\n{self._footer}")
        # Split the content on the section names
        section = re.compile(r"\n\[([^\]]+)\][ \t]*\n", re.MULTILINE)
        parts = section.split(matched.groups()[1])
        # Detect the version
        version_match = re.search(r"version (\d+)", parts[0])
        if not version_match:
            log.error(parts[0])
            raise StructuredFieldError(
                "Unable to detect StructuredField version")
        self.version(int(version_match.groups()[0]))
        log.debug(
            f"Detected StructuredField version {self.version()}")
        # Convert to dictionary, remove escapes and save the order
        keys = parts[1::2]
        escape = re.compile(r"^\[structured-field-escape\]", re.MULTILINE)
        values = [escape.sub("", value) for value in parts[2::2]]
        for key, value in zip(keys, values):
            self.set(key, value)
        log.debug(f"Parsed sections:\n{format_value(self._sections)}")

    def _save_version_zero(self) -> str:
        """ Save version 0 format """
        result = []
        if self._header:
            result.append(self._header)
        for section, content in self.iterate():
            result.append(f"[{section}]\n{content}")
        if self:
            result.append("[end]\n")
        if self._footer:
            result.append(self._footer)
        return "\n".join(result)

    def _save(self) -> str:
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
                "[structured-field-start]\n"
                f"This is StructuredField version {self._version}. "
                "Please, edit with care.\n")
            for section, content in self.iterate():
                result.append("[{}]\n{}".format(section, escape.sub(
                    "[structured-field-escape]\\1", content)))
            result.append("[structured-field-end]\n")
        # Footer
        if self._footer:
            result.append(self._footer)
        return "\n".join(result)

    def _read_section(self, content: str) -> dict[str, SFSectionValueType]:
        """ Parse config section and return ordered dictionary """
        dictionary: dict[str, SFSectionValueType] = OrderedDict()
        for line in content.split("\n"):
            # Remove comments and skip empty lines
            line = re.sub("#.*", "", line)
            if re.match(r"^\s*$", line):
                continue
            # Parse key and value
            matched = re.search("([^=]+)=(.*)", line)
            if not matched:
                raise StructuredFieldError(
                    f"Invalid key/value line: {line}")
            key = matched.groups()[0].strip()
            value = matched.groups()[1].strip()
            # Handle multiple values if enabled
            if key in dictionary and self._multi:
                stored_value = dictionary[key]
                if isinstance(stored_value, list):
                    stored_value.append(value)
                else:
                    dictionary[key] = [stored_value, value]
            else:
                dictionary[key] = value
        return dictionary

    def _write_section(self, dictionary: dict[str, SFSectionValueType]) -> str:
        """ Convert dictionary into a config section format """
        section = ""
        for key in dictionary:
            if isinstance(dictionary[key], list):
                for value in dictionary[key]:
                    section += f"{key} = {value}\n"
            else:
                section += f"{key} = {dictionary[key]}\n"
        return section

    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    #  StructuredField Methods
    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    def iterate(self) -> Iterator[tuple[str, str]]:
        """ Return (section, content) tuples for all sections """
        for section in self:
            yield section, self._sections[section]

    def version(self, version: Optional[int] = None) -> int:
        """ Get or set the StructuredField version """
        if version is not None:
            if version in [0, 1]:
                self._version = version
            else:
                raise StructuredFieldError(
                    f"Bad StructuredField version: {version}")
        return self._version

    def load(self, text: str, version: Optional[int] = None) -> None:
        """ Load the StructuredField from a string """
        if version is not None:
            self.version(version)
        # Make sure we got a text, convert from bytes if necessary
        if isinstance(text, bytes):
            text = text.decode("utf8")
        if not isinstance(text, str):
            raise StructuredFieldError(
                "Invalid StructuredField, expecting string")
        # Remove possible carriage returns
        text = re.sub("\r\n", "\n", text)
        # Make sure the text has a new line at the end
        if text and text[-1] != "\n":
            text += "\n"
        log.debug(f"Parsing StructuredField\n{text}")
        # Parse respective format version
        if self._version == 0:
            self._load_version_zero(text)
        else:
            self._load(text)

    def save(self) -> str:
        """ Convert the StructuredField into a string """
        if self.version() == 0:
            return self._save_version_zero()
        return self._save()

    def header(self, content: Optional[str] = None) -> str:
        """ Get or set the header content """
        if content is not None:
            self._header = content
        return self._header

    def footer(self, content: Optional[str] = None) -> str:
        """ Get or set the footer content """
        if content is not None:
            self._footer = content
        return self._footer

    def sections(self) -> list[str]:
        """ Get the list of available sections """
        return self._order

    def get(
            self,
            section: str,
            item: Optional[str] = None) -> SFSectionValueType:
        """ Return content of given section or section item """
        try:
            content = self._sections[section]
        except KeyError:
            raise StructuredFieldError(
                f"Section [{pure_ascii(section)!r}] not found")
        # Return the whole section content
        if item is None:
            return content
        # Return only selected item from the section
        try:
            return self._read_section(content)[item]
        except KeyError:
            raise StructuredFieldError(
                f"Unable to read '{pure_ascii(item)!r}' from section '{pure_ascii(section)!r}'")

    def set(self, section: str, content: Any,
            item: Optional[str] = None) -> None:
        """ Update content of given section or section item """
        # Convert to string if necessary, keep lists untouched
        if isinstance(content, list):
            pass
        elif isinstance(content, bytes):
            content = content.decode("utf8")
        elif not isinstance(content, str):
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

    def remove(self, section: str, item: Optional[str] = None) -> None:
        """ Remove given section or section item """
        # Remove the whole section
        if item is None:
            try:
                del self._sections[section]
                del self._order[self._order.index(section)]
            except KeyError:
                raise StructuredFieldError(
                    f"Section [{pure_ascii(section)!r}] not found")
        # Remove only selected item from the section
        else:
            try:
                dictionary = self._read_section(self._sections[section])
                del (dictionary[item])
            except KeyError:
                raise StructuredFieldError(
                    f"Unable to remove '{pure_ascii(item)!r}' "
                    f"from section '{pure_ascii(section)!r}'"
                    )
            self._sections[section] = self._write_section(dictionary)


class DistGitHandler:
    """ Common functionality for DistGit handlers """

    sources_file_name = 'sources'
    uri = "/rpms/{name}/{filename}/{hashtype}/{hash}/{filename}"

    usage_name: str  # Name to use for dist-git-type
    re_source: Pattern[str]
    # https://www.gnu.org/software/tar/manual/tar.html#auto_002dcompress
    re_supported_extensions: Pattern[str] = re.compile(
        r'\.((tar\.(gz|Z|bz2|lz|lzma|lzo|xz|zst))|tgz|taz|taZ|tz2|tbz2|tbz|tlz|tzst)$')
    lookaside_server: str
    remote_substring: Pattern[str]

    def url_and_name(self, cwd: Optional[Path] = None) -> list[tuple[str, str]]:
        """
        Return list of urls and basenames of the used source

        The 'cwd' parameter has to be a DistGit directory.
        """
        cwd = cwd or Path.cwd()
        # Assumes <package>.spec
        globbed = list(cwd.glob('*.spec'))
        if len(globbed) != 1:
            raise GeneralError(f"No .spec file is present in '{cwd}'.")
        package = globbed[0].stem
        ret_values = []
        try:
            with open(cwd / self.sources_file_name) as f:
                for line in f:
                    match = self.re_source.match(line)
                    if match is None:
                        raise GeneralError(
                            f"Couldn't match '{self.sources_file_name}' "
                            f"content with '{self.re_source.pattern}'.")
                    used_hash, source_name, hash_value = match.groups()
                    ret_values.append((self.lookaside_server + self.uri.format(
                        name=package,
                        filename=source_name,
                        hash=hash_value,
                        hashtype=used_hash.lower()
                        ), source_name))
        except Exception as error:
            raise GeneralError(f"Couldn't read '{self.sources_file_name}' file.") from error
        if not ret_values:
            raise GeneralError(
                "No sources found in '{self.sources_file_name}' file.")
        return ret_values

    def its_me(self, remotes: list[str]) -> bool:
        """ True if self can work with remotes """
        return any(self.remote_substring.search(item) for item in remotes)


class FedoraDistGit(DistGitHandler):
    """ Fedora Handler """

    usage_name = "fedora"
    re_source = re.compile(r"^(\w+) \(([^)]+)\) = ([0-9a-fA-F]+)$")
    lookaside_server = "https://src.fedoraproject.org/repo/pkgs"
    remote_substring = re.compile(r'fedoraproject\.org')


class CentOSDistGit(DistGitHandler):
    """ CentOS Handler """

    usage_name = "centos"
    re_source = re.compile(r"^(\w+) \(([^)]+)\) = ([0-9a-fA-F]+)$")
    lookaside_server = "https://sources.stream.centos.org/sources"
    remote_substring = re.compile(r'redhat/centos')


class RedHatGitlab(DistGitHandler):
    """ Red Hat on Gitlab """

    usage_name = "redhatgitlab"
    re_source = re.compile(r"^(\w+) \(([^)]+)\) = ([0-9a-fA-F]+)$")
    # Location already public (standard-test-roles)
    lookaside_server = "http://pkgs.devel.redhat.com/repo"
    remote_substring = re.compile(r'redhat/rhel/')


def get_distgit_handler(
        remotes: Optional[list[str]] = None,
        usage_name: Optional[str] = None) -> DistGitHandler:
    """
    Return the right DistGitHandler

    Pick the DistGitHandler class which understands specified
    remotes or by usage_name.
    """
    for candidate_class in DistGitHandler.__subclasses__():
        if usage_name is not None and usage_name == candidate_class.usage_name:
            return candidate_class()
        if remotes is not None:
            ret_val = candidate_class()
            if ret_val.its_me(remotes):
                return ret_val
    raise GeneralError(f"No known remote in '{remotes}'.")


def get_distgit_handler_names() -> list[str]:
    """ All known distgit handlers """
    return [i.usage_name for i in DistGitHandler.__subclasses__()]


def distgit_download(
        *,
        distgit_dir: Path,
        target_dir: Path,
        handler_name: Optional[str] = None,
        caller: Optional['Common'] = None,
        logger: tmt.log.Logger
        ) -> None:
    """
    Download sources to the target_dir

    distgit_dir is path to the DistGit repository
    """
    # Get the handler unless specified
    if handler_name is None:
        cmd = Command("git", "config", "--get-regexp", '^remote\\..*.url')
        output = cmd.run(cwd=distgit_dir,
                         caller=caller,
                         logger=logger)
        if output.stdout is None:
            raise tmt.utils.GeneralError("Missing remote origin url.")
        remotes = output.stdout.split('\n')
        handler = tmt.utils.get_distgit_handler(remotes=remotes)
    else:
        handler = tmt.utils.get_distgit_handler(usage_name=handler_name)

    for url, source_name in handler.url_and_name(distgit_dir):
        logger.debug(f"Download sources from '{url}'.")
        with tmt.utils.retry_session() as session:
            response = session.get(url)
        response.raise_for_status()
        target_dir.mkdir(exist_ok=True, parents=True)
        with open(target_dir / source_name, 'wb') as tarball:
            tarball.write(response.content)


# ignore[type-arg]: base class is a generic class, but we cannot list its parameter type, because
# in Python 3.6 the class "is not subscriptable".
class UpdatableMessage(contextlib.AbstractContextManager):  # type: ignore[type-arg]
    """ Updatable message suitable for progress-bar-like reporting """

    def __init__(
            self,
            key: str,
            enabled: bool = True,
            indent_level: int = 0,
            key_color: Optional[str] = None,
            default_value_color: Optional[str] = None,
            clear_on_exit: bool = False
            ) -> None:
        """
        Updatable message suitable for progress-bar-like reporting.

        .. code-block:: python3

           with UpdatableMessage('foo') as message:
               while ...:
                   ...

                   # check state of remote request, and update message
                   state = remote_api.check()
                   message.update(state)

        :param key: a string to use as the left-hand part of logged message.
        :param enabled: if unset, no output would be performed.
        :param indent_level: desired indentation level.
        :param key_color: optional color to apply to ``key``.
        :param default_color: optional color to apply to value when
            :py:meth:`update` is called with ``color`` left out.
        :param clear_on_exit: if set, the message area would be cleared when
            leaving the progress bar when used as a context manager.
        """

        self.key = key
        self.enabled = enabled
        self.indent_level = indent_level
        self.key_color = key_color
        self.default_value_color = default_value_color
        self.clear_on_exit = clear_on_exit

        # No progress if terminal not attached
        if not sys.stdout.isatty():
            self.enabled = False

        self._previous_line: Optional[str] = None

    def __enter__(self) -> 'Self':
        return self

    def __exit__(self, *args: object) -> None:
        if self.clear_on_exit:
            self.clear()

        sys.stdout.write('\n')
        sys.stdout.flush()

    def clear(self) -> None:
        """ Clear the message area """

        self._update_message_area('')

    def _update_message_area(self, value: str, color: Optional[str] = None) -> None:
        """
        Update message area with given value.

        .. note::

            This method is the workhorse for :py:meth:`update` which, in our
            basic implementation, is a thin wrapper for
            :py:meth:`_update_message_area`.

            Derived classes may choose to override the default implementation of
            :py:meth:`update`, to simplify the message construction, and call
            :py:meth:`_update_message_area` to emit the message.
        """

        if not self.enabled:
            return

        if self._previous_line is not None:
            message = value.ljust(len(self._previous_line))

        else:
            message = value

        self._previous_line = value

        message = tmt.log.indent(
            self.key,
            value=style(
                message,
                fg=color or self.default_value_color),
            color=self.key_color,
            level=self.indent_level)

        sys.stdout.write(f"\r{message}")
        sys.stdout.flush()

    def update(self, value: str, color: Optional[str] = None) -> None:
        """
        Update progress message.

        :param value: new message to update message area with.
        :param color: optional message color.
        """

        self._update_message_area(value, color=color)


def find_fmf_root(path: Path, ignore_paths: Optional[list[Path]] = None) -> list[Path]:
    """
    Search through path and return all fmf roots that exist there

    Returned list is ordered by path length, shortest one first.

    Raise `MetadataError` if no fmf root is found.
    """
    fmf_roots = []
    for _root, _, files in os.walk(path):
        root = Path(_root)
        if root.name != '.fmf':
            continue
        if ignore_paths and root.parent in ignore_paths:
            continue
        if 'version' in files:
            fmf_roots.append(root.parent)
    if not fmf_roots:
        raise MetadataError(f"No fmf root present inside '{path}'.")
    fmf_roots.sort(key=lambda path: len(str(path)))
    return fmf_roots


#
# JSON schema-based validation helpers
#
# Aims at FMF data consumed by tmt, but can be used for any structure.
#

# `Schema` represents a loaded JSON schema structure. It may be fairly complex,
# but it's not needed to provide the exhaustive and fully detailed type since
# tmt code is not actually "reading" it. Loaded schema is passed down to
# jsonschema library, and while `Any` would be perfectly valid, let's use an
# alias to make schema easier to track in our code.
Schema = dict[str, Any]
SchemaStore = dict[str, Schema]


def _patch_plan_schema(schema: Schema, store: SchemaStore) -> None:
    """
    Resolve references to per-plugin schema known to steps. All schemas have
    been loaded into store, all that's left is to update each step in plan
    schema with the list of schemas allowed for that particular step.

    For each step, we create the following schema (see also plan.yaml for the
    rest of plan schema):

    .. code-block:: yaml

       <step name>:
         oneOf:
           - $ref: "/schemas/<step name>/plugin1"
           - $ref: "/schemas/<step name>/plugin2"
           ...
           - $ref: "/schemas/<step name>/pluginN"
           - type: array
             items:
               anyOf:
                 - $ref: "/schemas/<step name>/plugin1"
                 - $ref: "/schemas/<step name>/plugin2"
                 ...
                 - $ref: "/schemas/<step name>/pluginN"
    """

    for step in ('discover', 'execute', 'finish', 'prepare', 'provision', 'report'):
        step_schema_prefix = f'/schemas/{step}/'

        step_plugin_schema_ids = [schema_id for schema_id in store if schema_id.startswith(
            step_schema_prefix) and schema_id not in PLAN_SCHEMA_IGNORED_IDS]

        refs: list[Schema] = [
            {'$ref': schema_id} for schema_id in step_plugin_schema_ids
            ]

        schema['properties'][step] = {
            'oneOf': [*refs,
                      {
                          'type': 'array',
                          'items': {
                              'anyOf': refs
                              }
                          }
                      ]
            }


def _load_schema(schema_filepath: Path) -> Schema:
    """
    Load a JSON schema from a given filepath.

    A helper returning the raw loaded schema.
    """

    if not schema_filepath.is_absolute():
        schema_filepath = resource_files('schemas') / schema_filepath

    try:
        with open(schema_filepath, encoding='utf-8') as f:
            return cast(Schema, yaml_to_dict(f.read()))

    except Exception as exc:
        raise FileError(f"Failed to load schema file {schema_filepath}\n{exc}")


@functools.cache
def load_schema(schema_filepath: Path) -> Schema:
    """
    Load a JSON schema from a given filepath.

    Recommended for general use, the method may apply some post-loading touches
    to the given schema, and unless caller is interested in the raw content of
    the file, this functions should be used instead of the real workhorse of
    schema loading, :py:func:`_load_schema`.
    """

    schema = _load_schema(schema_filepath)

    if schema.get('$id') == '/schemas/plan':
        _patch_plan_schema(schema, load_schema_store())

    return schema


@functools.cache
def load_schema_store() -> SchemaStore:
    """
    Load all available JSON schemas, and put them into a "store".

    Schema store is a simple mapping between schema IDs and schemas.
    """

    store: SchemaStore = {}
    schema_dirpath = resource_files('schemas')

    try:
        for filepath in schema_dirpath.glob('**/*ml'):
            # Ignore all files but YAML files.
            if filepath.suffix.lower() not in ('.yaml', '.yml'):
                continue

            schema = _load_schema(filepath)

            store[schema['$id']] = schema

    except Exception as exc:
        raise FileError(f"Failed to discover schema files\n{exc}")

    if '/schemas/plan' not in store:
        raise FileError('Failed to discover schema for plans')

    _patch_plan_schema(store['/schemas/plan'], store)

    return store


def _prenormalize_fmf_node(node: fmf.Tree, schema_name: str, logger: tmt.log.Logger) -> fmf.Tree:
    """
    Apply the minimal possible normalization steps to nodes before validating them with schemas.

    tmt allows some fields to have default values, and at least ``how`` field is necessary for
    schema-based validation to work reliably. Based on ``how`` field, plan schema identifies
    the correct *plugin* schema for step validation. Without ``how``, it's hard to pick the
    correct schema.

    This function tries to do minimal number of changes to a given fmf node to honor the promise
    of ``how`` being optional, with known defaults for each step. It might be possible to resolve
    this purely with schemas, but since we don't know how (yet?), a Python implementation has been
    chosen to unblock schema-based validation while keeping things easier for users. This may
    change in the future, dropping the need for this pre-validation step.

    .. note::

       This function is not part of the normalization process that happens after validation. The
       purpose of this function is to make the world nice and shiny for tmt users while avoiding
       the possibility of schema becoming way too complicated, especially when we would need
       non-trivial amount of time for experiments.

       The real normalization process takes place after validation, and is responsible for
       converting raw fmf data to data types and structures more suited for tmt internal
       implementation.
    """

    # As of now, only `how` field in plan steps seems to be required for schema-based validation
    # to work correctly, therefore ignore any other node.
    if schema_name != 'plan.yaml':
        return node

    # Perform the very crude and careful semi-validation. We need to set the `how` key to a default
    # value - but it's not our job to validate the general structure of node data. Walk the "happy"
    # path, touch the node only when it matches the specification of being a mapping of steps and
    # these being either mappings or lists of mappings. Whenever we notice some value does not
    # match this basic structure, ignore the step completely - its issues will be caught by schema
    # later, don't waste time on steps that do not follow specification.

    # Fmf data describing a plan shall be a mapping (with keys like `discover` or `adjust`).
    if not isinstance(node.data, dict):
        return node

    # Do NOT modify the given node! Changing it might taint or hide important
    # keys the later processing could need in their original state. Namely, we
    # need to initialize `how` to reach at least some schema, but CLI processing
    # needs to realize `how` was not given, and therefore it's possible to be
    # modified with `--update-missing`...
    node = node.copy()

    # Avoid possible circular imports
    import tmt.steps

    def _process_step(step_name: str, step: dict[Any, Any]) -> None:
        """ Process a single step configuration """

        # If `how` is set, don't touch it, and there's nothing to do.
        if 'how' in step:
            return

        # Magic!
        # No, seriously: step is implemented in `tmt.steps.$step_name` package,
        # by a class `tmt.steps.$step_name.$step_name_with_capitalized_first_letter`.
        # Instead of having a set of if-elif tests, we can reach the default `how`
        # dynamically.

        from tmt.plugins import import_member

        step_module_name = f'tmt.steps.{step_name}'
        step_class_name = step_name.capitalize()

        step_class = import_member(
            module=step_module_name,
            member=step_class_name,
            logger=logger)[1]

        if not issubclass(step_class, tmt.steps.Step):
            raise GeneralError(
                'Possible step {step_name} implementation '
                f'{step_module_name}.{step_class_name} is not a subclass '
                'of tmt.steps.Step class.')

        step['how'] = step_class.DEFAULT_HOW

    def _process_step_collection(step_name: str, step_collection: Any) -> None:
        """ Process a collection of step configurations """

        # Ignore anything that is not a step.
        if step_name not in tmt.steps.STEPS:
            return

        # A single step configuration, represented as a mapping.
        if isinstance(step_collection, dict):
            _process_step(step_name, step_collection)

            return

        # Multiple step configurations, as mappings in a list
        if isinstance(step_collection, list):
            for step_config in step_collection:
                # Unexpected, maybe instead of a mapping describing a step someone put
                # in an integer... Ignore, schema will report it.
                if not isinstance(step_config, dict):
                    continue

                _process_step(step_name, step_config)

    for step_name, step_config in node.data.items():
        _process_step_collection(step_name, step_config)

    return node


def preformat_jsonschema_validation_errors(
        raw_errors: list[jsonschema.ValidationError],
        prefix: Optional[str] = None) -> list[tuple[jsonschema.ValidationError, str]]:
    """
    A helper to preformat JSON schema validation errors.

    Raw errors can be converted to strings with a simple ``str()`` call,
    but resulting string is very JSON-ish. This helper provides
    simplified string representation consisting of error message and
    element path.

    :param raw_error: raw validation errors as provided by
        :py:mod:`jsonschema`.
    :param prefix: if specified, it is added at the beginning of each
        stringified error.
    :returns: a list of two-item tuples, the first item being the
        original validation error, the second item being its simplified
        string rendering.
    """

    prefix = f'{prefix}:' if prefix else ''
    errors: list[tuple[jsonschema.ValidationError, str]] = []

    for error in raw_errors:
        path = f'{prefix}{".".join(str(p) for p in error.path)}'

        errors.append((error, f'{path} - {error.message}'))

    return errors


def validate_fmf_node(
        node: fmf.Tree,
        schema_name: str,
        logger: tmt.log.Logger) -> list[tuple[jsonschema.ValidationError, str]]:
    """ Validate a given fmf node """

    node = _prenormalize_fmf_node(node, schema_name, logger)

    result = node.validate(load_schema(Path(schema_name)), schema_store=load_schema_store())

    if result.result is True:
        return []

    return preformat_jsonschema_validation_errors(result.errors, prefix=node.name)


# A type for callbacks given to wait()
WaitCheckType = Callable[[], T]


def wait(
        parent: Common,
        check: WaitCheckType[T],
        timeout: datetime.timedelta,
        tick: float = DEFAULT_WAIT_TICK,
        tick_increase: float = DEFAULT_WAIT_TICK_INCREASE
        ) -> T:
    """
    Wait for a condition to become true.

    To test the condition state, a ``check`` callback is called every ``tick``
    seconds until ``check`` reports a success. The callback may:

    * decide the condition has been fulfilled. This is a successful outcome,
      ``check`` shall then simply return, and waiting ends. Or,
    * decide more time is needed. This is not a successful outcome, ``check``
      shall then raise :py:class:`WaitingIncomplete` exception, and ``wait()``
      will try again later.

    :param parent: "owner" of the wait process. Used for its logging capability.
    :param check: a callable responsible for testing the condition. Accepts no
        arguments. To indicate more time and attempts are needed, the callable
        shall raise :py:class:`WaitingIncomplete`, otherwise it shall return
        without exception. Its return value will be propagated by ``wait()`` up
        to ``wait()``'s. All other exceptions raised by ``check`` will propagate
        to ``wait()``'s caller as well, terminating the wait.
    :param timeout: amount of time ``wait()`` is allowed to spend waiting for
        successful outcome of ``check`` call.
    :param tick: how many seconds to wait between two consecutive calls of
        ``check``.
    :param tick_increase: a multiplier applied to ``tick`` after every attempt.
    :returns: value returned by ``check`` reporting success.
    :raises GeneralError: when ``tick`` is not a positive integer.
    :raises WaitingTimedOutError: when time quota has been consumed.
    """

    if tick <= 0:
        raise GeneralError('Tick must be a positive integer')

    monotomic_clock = time.monotonic

    deadline = monotomic_clock() + timeout.total_seconds()

    parent.debug(
        'wait',
        f"waiting for condition '{check.__name__}' with timeout {timeout},"
        f" deadline in {timeout.total_seconds()} seconds,"
        f" checking every {tick:.2f} seconds")

    while True:
        now = monotomic_clock()

        if now > deadline:
            parent.debug(
                'wait',
                f"'{check.__name__}' did not succeed,"
                f" {now - deadline:.2f} over quota")

            raise WaitingTimedOutError(check, timeout)

        try:
            ret = check()

            # Perform one extra check: if `check()` succeeded, but took more time than
            # allowed, it should be recognized as a failed waiting too.
            now = monotomic_clock()

            if now > deadline:
                parent.debug(
                    'wait',
                    f"'{check.__name__}' finished successfully but took too much time,"
                    f" {now - deadline:.2f} over quota")

                raise WaitingTimedOutError(check, timeout, check_success=True)

            parent.debug(
                'wait',
                f"'{check.__name__}' finished successfully,"
                f" {deadline - now:.2f} seconds left")

            return ret

        except WaitingIncompleteError:
            # Update timestamp for more accurate logging - check() could have taken minutes
            # to complete, using the pre-check timestamp for logging would be misleading.
            now = monotomic_clock()

            parent.debug(
                'wait',
                f"'{check.__name__}' still pending,"
                f" {deadline - now:.2f} seconds left,"
                f" current tick {tick:.2f} seconds")

            time.sleep(tick)

            tick *= tick_increase

            continue


class ValidateFmfMixin(_CommonBase):
    """
    Mixin adding validation of an fmf node.

    Loads a schema whose name is derived from class name, and uses fmf's validate()
    method to perform the validation.
    """

    def _validate_fmf_node(
            self,
            node: fmf.Tree,
            raise_on_validation_error: bool,
            logger: tmt.log.Logger) -> None:
        """ Validate a given fmf node """

        errors = validate_fmf_node(
            node, f'{self.__class__.__name__.lower()}.yaml', logger)

        if errors:
            if raise_on_validation_error:
                raise SpecificationError(
                    f'fmf node {node.name} failed validation',
                    validation_errors=errors)

            for _, error_message in errors:
                logger.warning(error_message, shift=1)

    def __init__(
            self,
            *,
            node: fmf.Tree,
            skip_validation: bool = False,
            raise_on_validation_error: bool = False,
            logger: tmt.log.Logger,
            **kwargs: Any) -> None:
        # Validate *before* letting next class in line touch the data.
        if not skip_validation:
            self._validate_fmf_node(node, raise_on_validation_error, logger)

        super().__init__(node=node, logger=logger, **kwargs)


def dataclass_normalize_field(
        container: Any,
        key_address: str,
        keyname: str,
        raw_value: Any,
        logger: tmt.log.Logger) -> Any:
    """
    Normalize and assign a value to container field.

    If there is a normalization callback defined for the field via ``normalize``
    parameter of :py:func:`field`, the callback is called to coerce ``raw_value``,
    and the return value is assigned to container field instead of ``value``.
    """

    # Find out whether there's a normalization callback, and use it. Otherwise,
    # the raw value is simply used.
    value = raw_value

    if dataclasses.is_dataclass(container):
        _, _, _, _, metadata = container_field(type(container), keyname)

        if metadata.normalize_callback:
            value = metadata.normalize_callback(key_address, raw_value, logger)

    # TODO: we already access parameter source when importing CLI invocations in `Step.wake()`,
    # we should do the same here as well. It will require adding (optional) Click context
    # as one of the inputs, but that's acceptable. Then we can get rid of this less-than-perfect
    # test.
    #
    # Keep for debugging purposes, as long as normalization settles down.
    if not value:
        logger.debug(
            f'field "{key_address}" normalized to false-ish value',
            f'{container.__class__.__name__}.{keyname}',
            level=4,
            topic=tmt.log.Topic.KEY_NORMALIZATION)

        with_getattr = getattr(container, keyname, None)
        with_dict = container.__dict__.get(keyname, None)

        logger.debug(
            'value',
            str(value),
            level=4,
            shift=1,
            topic=tmt.log.Topic.KEY_NORMALIZATION)
        logger.debug(
            'current value (getattr)',
            str(with_getattr),
            level=4,
            shift=1,
            topic=tmt.log.Topic.KEY_NORMALIZATION)
        logger.debug(
            'current value (__dict__)',
            str(with_dict),
            level=4,
            shift=1,
            topic=tmt.log.Topic.KEY_NORMALIZATION)

        if value != with_getattr or with_getattr != with_dict:
            logger.debug(
                'known values do not match',
                level=4,
                shift=2,
                topic=tmt.log.Topic.KEY_NORMALIZATION)

    # Set attribute by adding it to __dict__ directly. Messing with setattr()
    # might cause reuse of mutable values by other instances.
    container.__dict__[keyname] = value

    return value


def normalize_int(
        key_address: str,
        value: Any,
        logger: tmt.log.Logger) -> int:
    """
    Normalize an integer.

    For a field that takes an integer input. The field might be also
    left out, but it does have a default value.
    """

    if isinstance(value, int):
        return value

    try:
        return int(value)

    except ValueError as exc:
        raise NormalizationError(key_address, value, 'an integer') from exc


def normalize_optional_int(
        key_address: str,
        value: Any,
        logger: tmt.log.Logger) -> Optional[int]:
    """
    Normalize an integer that may be unset as well.

    For a field that takes an integer input, but might be also left out,
    and has no default value.
    """

    if value is None:
        return None

    if isinstance(value, int):
        return value

    try:
        return int(value)

    except ValueError as exc:
        raise NormalizationError(key_address, value, 'unset or an integer') from exc


def normalize_storage_size(
        key_address: str,
        value: Any,
        logger: tmt.log.Logger) -> int:
    """
    Normalize a storage size.

    As of now, it's just a simple integer with units interpreted by the owning
    plugin. In the future, we want this function to switch to proper units
    and return ``pint.Quantity`` instead.
    """

    return normalize_int(key_address, value, logger)


def normalize_string_list(
        key_address: str,
        value: Any,
        logger: tmt.log.Logger) -> list[str]:
    """
    Normalize a string-or-list-of-strings input value.

    This is a fairly common input format present mostly in fmf nodes where
    tmt, to make things easier for humans, allows this:

    .. code-block:: yaml

       foo: bar

       foo:
         - bar
         - baz

    Internally, we should stick to one type only, and make sure whatever we get
    on the input, a list of strings would be the output.

    :param value: input value from key source.
    """

    if value is None:
        return []

    if isinstance(value, str):
        return [value]

    if isinstance(value, (list, tuple)):
        normalized_value: list[str] = []

        for i, raw_item in enumerate(value):
            if isinstance(raw_item, str):
                normalized_value.append(raw_item)
                continue

            raise NormalizationError(f'{key_address}[{i}]', raw_item, 'a string')

        return normalized_value

    raise NormalizationError(key_address, value, 'a string or a list of strings')


def normalize_pattern_list(
        key_address: str,
        value: Any,
        logger: tmt.log.Logger) -> list[Pattern[str]]:
    """
    Normalize a pattern-or-list-of-patterns input value.

    .. code-block:: yaml

       foo: 'bar.*'

       foo:
         - 'bar.*'
         - '(?i)BaZ+'
    """

    def _normalize(raw_patterns: list[Any]) -> list[Pattern[str]]:
        patterns: list[Pattern[str]] = []

        for i, raw_pattern in enumerate(raw_patterns):
            if isinstance(raw_pattern, str):
                try:
                    patterns.append(re.compile(raw_pattern))

                except Exception:
                    raise NormalizationError(
                        f'{key_address}[{i}]', raw_pattern, 'a regular expression')

            elif isinstance(raw_pattern, re.Pattern):
                patterns.append(raw_pattern)

            else:
                raise NormalizationError(
                    f'{key_address}[{i}]', raw_pattern, 'a regular expression')

        return patterns

    if value is None:
        return []

    if isinstance(value, str):
        return _normalize([value])

    if isinstance(value, (list, tuple)):
        return _normalize(list(value))

    raise NormalizationError(
        key_address,
        value,
        'a regular expression or a list of regular expressions')


def normalize_integer_list(
        key_address: str,
        value: Any,
        logger: tmt.log.Logger) -> list[int]:
    """
    Normalize an integer-or-list-of-integers input value.

    .. code-block:: yaml

       foo: 11

       foo:
         - 11
         - 79

    :param value: input value from key source.
    """

    if value is None:
        return []

    normalized: list[int] = []

    if not isinstance(value, list):
        value = [value]

    for i, item in enumerate(value):
        try:
            normalized.append(int(item))

        except Exception as exc:
            raise NormalizationError(f'{key_address}[{i}]', item, 'an integer') from exc

    return normalized


def normalize_path(
        key_address: str,
        value: Any,
        logger: tmt.log.Logger) -> Optional[Path]:
    """ Normalize content of the test `path` key """

    if value is None:
        return None

    if isinstance(value, Path):
        return value

    if isinstance(value, str):
        return Path(value)

    raise tmt.utils.NormalizationError(key_address, value, 'a string')


def normalize_path_list(
        key_address: str,
        value: Union[None, str, list[str]],
        logger: tmt.log.Logger) -> list[Path]:
    """
    Normalize a path-or-list-of-paths input value.

    This is a fairly common input format present mostly in fmf nodes where
    tmt, to make things easier for humans, allows this:

    .. code-block:: yaml

       foo: /foo/bar

       foo:
         - /foo/bar
         - /baz

    Internally, we should stick to one type only, and make sure whatever we get
    on the input, a list of strings would be the output.

    :param value: input value from key source.
    """

    if value is None:
        return []

    if isinstance(value, str):
        return [Path(value)]

    if isinstance(value, (list, tuple)):
        return [Path(path) for path in value]

    raise NormalizationError(key_address, value, 'a path or a list of paths')


def normalize_shell_script_list(
        key_address: str,
        value: Union[None, str, list[str]],
        logger: tmt.log.Logger) -> list[ShellScript]:
    """
    Normalize a string-or-list-of-strings input value.

    This is a fairly common input format present mostly in fmf nodes where
    tmt, to make things easier for humans, allows this:

    .. code-block:: yaml

       foo: bar

       foo:
         - bar
         - baz

    Internally, we should stick to one type only, and make sure whatever we get
    on the input, a list of strings would be the output.

    :param value: input value from key source.
    """

    if value is None:
        return []

    if isinstance(value, str):
        return [ShellScript(value)]

    if isinstance(value, (list, tuple)):
        return [ShellScript(str(item)) for item in value]

    raise NormalizationError(key_address, value, 'a string or a list of strings')


def normalize_shell_script(
        key_address: str,
        value: Union[None, str],
        logger: tmt.log.Logger) -> Optional[ShellScript]:
    """
    Normalize a single shell script input that may be unset.

    :param value: input value from key source.
    """

    if value is None:
        return None

    if isinstance(value, str):
        return ShellScript(value)

    raise NormalizationError(key_address, value, 'a string')


class NormalizeKeysMixin(_CommonBase):
    """
    Mixin adding support for loading fmf keys into object attributes.

    When invoked, annotated class-level variables are searched for in a given source
    container - a mapping, an fmf node, etc. - and if the key of the same name as the
    variable exists, its value is "promoted" to instance variable.

    If a method named ``_normalize_<variable name>`` exists, it is called with the fmf
    key value as its single argument, and its return value is assigned to instance
    variable. This gives class chance to modify or transform the original value when
    needed, e.g. to convert the original value to a type more suitable for internal
    processing.
    """

    # If specified, keys would be iterated over in the order as listed here.
    _KEYS_SHOW_ORDER: list[str] = []

    @classmethod
    def _iter_key_annotations(cls) -> Iterator[tuple[str, Any]]:
        """
        Iterate over keys' type annotations.

        Keys are yielded in the order: keys declared by parent classes first, then
        keys declared by the class itself, all following the order in which keys
        were defined in their respective classes.

        :yields: pairs of key name and its annotations.
        """

        def _iter_class_annotations(klass: type) -> Iterator[tuple[str, Any]]:
            # Skip, needs fixes to become compatible
            if klass is Common:
                return

            for name, value in klass.__dict__.get('__annotations__', {}).items():
                # Skip special fields that are not keys.
                if name in ('_KEYS_SHOW_ORDER', '_linter_registry', '_export_plugin_registry'):
                    continue

                yield (name, value)

        # Reverse MRO to start with the most base classes first, to iterate over keys
        # in the order they are defined.
        for klass in reversed(cls.__mro__):
            yield from _iter_class_annotations(klass)

    @classmethod
    def keys(cls) -> Iterator[str]:
        """
        Iterate over key names.

        Keys are yielded in the order: keys declared by parent classes first, then
        keys declared by the class itself, all following the order in which keys
        were defined in their respective classes.

        :yields: key names.
        """

        for keyname, _ in cls._iter_key_annotations():
            yield keyname

    def items(self) -> Iterator[tuple[str, Any]]:
        """
        Iterate over keys and their values.

        Keys are yielded in the order: keys declared by parent classes first, then
        keys declared by the class itself, all following the order in which keys
        were defined in their respective classes.

        :yields: pairs of key name and its value.
        """
        # SIM118 Use `{key} in {dict}` instead of `{key} in {dict}.keys().
        # "Type[SerializableContainerDerivedType]" has no attribute "__iter__" (not iterable)
        for keyname in self.keys():
            yield (keyname, getattr(self, keyname))

    # TODO: exists for backward compatibility for the transition period. Once full
    # type annotations land, there should be no need for extra _keys attribute.
    @classmethod
    def _keys(cls) -> list[str]:
        """ Return a list of names of object's keys. """

        return list(cls.keys())

    def _load_keys(
            self,
            key_source: dict[str, Any],
            key_source_name: str,
            logger: tmt.log.Logger) -> None:
        """ Extract values for class-level attributes, and verify they match declared types. """

        log_shift, log_level = 2, 4

        debug_intro = functools.partial(
            logger.debug,
            shift=log_shift - 1,
            level=log_level,
            topic=tmt.log.Topic.KEY_NORMALIZATION)
        debug = functools.partial(
            logger.debug,
            shift=log_shift,
            level=log_level,
            topic=tmt.log.Topic.KEY_NORMALIZATION)

        debug_intro('key source')
        for k, v in key_source.items():
            debug(f'{k}: {v} ({type(v)})')

        debug('')

        for keyname, keytype in self._iter_key_annotations():
            key_address = f'{key_source_name}:{keyname}'

            source_keyname = key_to_option(keyname)
            source_keyname_cli = keyname

            # Do not indent this particular entry like the rest, so it could serve
            # as a "header" for a single key processing.
            debug_intro('key', key_address)
            debug('field', source_keyname)

            debug('desired type', str(keytype))

            value: Any = None

            # Verbose, let's hide it a bit deeper.
            debug('dict', self.__dict__, level=log_level + 1)

            if hasattr(self, keyname):
                # If the key exists as instance's attribute already, it is because it's been
                # declared with a default value, and the attribute now holds said default value.
                default_value = getattr(self, keyname)

                # If the default value is a mutable container, we cannot use it directly.
                # Should we do so, the very same default value would be assigned to multiple
                # instances/attributes instead of each instance having its own distinct container.
                if isinstance(default_value, (list, dict)):
                    debug('detected mutable default')
                    default_value = copy.copy(default_value)

                debug('default value', str(default_value))
                debug('default value type', str(type(default_value)))

                if source_keyname in key_source:
                    value = key_source[source_keyname]

                elif source_keyname_cli in key_source:
                    value = key_source[source_keyname_cli]

                else:
                    value = default_value

                debug('raw value', str(value))
                debug('raw value type', str(type(value)))

            else:
                if source_keyname in key_source:
                    value = key_source[source_keyname]

                elif source_keyname_cli in key_source:
                    value = key_source[source_keyname_cli]

                debug('raw value', str(value))
                debug('raw value type', str(type(value)))

            value = dataclass_normalize_field(self, key_address, keyname, value, logger)

            debug('final value', str(value))
            debug('final value type', str(type(value)))

            # Apparently pointless, but makes the debugging output more readable.
            # There may be plenty of tests and plans and keys, a bit of spacing
            # can't hurt.
            debug('')

        debug_intro('normalized fields')
        for k, v in self.__dict__.items():
            debug(f'{k}: {v} ({type(v)})')

        debug('')

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)


class LoadFmfKeysMixin(NormalizeKeysMixin):
    def __init__(
            self,
            *,
            node: fmf.Tree,
            logger: tmt.log.Logger,
            **kwargs: Any) -> None:
        self._load_keys(node.get(), node.name, logger)

        super().__init__(node=node, logger=logger, **kwargs)


@overload
def field(
        *,
        default: bool,
        # Options
        option: Optional[FieldCLIOption] = None,
        is_flag: bool = True,
        choices: Union[None, Sequence[str], Callable[[], Sequence[str]]] = None,
        multiple: bool = False,
        metavar: Optional[str] = None,
        envvar: Optional[str] = None,
        deprecated: Optional['tmt.options.Deprecated'] = None,
        help: Optional[str] = None,
        show_default: bool = False,
        internal: bool = False,
        # Input data normalization - not needed, the field is a boolean
        # flag.
        # normalize: Optional[NormalizeCallback[T]] = None
        # Custom serialization
        # serialize: Optional[SerializeCallback[bool]] = None,
        # unserialize: Optional[UnserializeCallback[bool]] = None
        # Custom exporter
        # exporter: Optional[FieldExporter[T]] = None
        ) -> bool:
    pass


@overload
def field(
        *,
        default: T,
        # Options
        option: Optional[FieldCLIOption] = None,
        is_flag: bool = False,
        choices: Union[None, Sequence[str], Callable[[], Sequence[str]]] = None,
        multiple: bool = False,
        metavar: Optional[str] = None,
        envvar: Optional[str] = None,
        deprecated: Optional['tmt.options.Deprecated'] = None,
        help: Optional[str] = None,
        show_default: bool = False,
        internal: bool = False,
        # Input data normalization
        normalize: Optional[NormalizeCallback[T]] = None,
        # Custom serialization
        serialize: Optional[SerializeCallback[T]] = None,
        unserialize: Optional[UnserializeCallback[T]] = None,
        # Custom exporter
        exporter: Optional[FieldExporter[T]] = None
        ) -> T:
    pass


@overload
def field(
        *,
        default_factory: Callable[[], T],
        # Options
        option: Optional[FieldCLIOption] = None,
        is_flag: bool = False,
        choices: Union[None, Sequence[str], Callable[[], Sequence[str]]] = None,
        multiple: bool = False,
        metavar: Optional[str] = None,
        envvar: Optional[str] = None,
        deprecated: Optional['tmt.options.Deprecated'] = None,
        help: Optional[str] = None,
        show_default: bool = False,
        internal: bool = False,
        # Input data normalization
        normalize: Optional[NormalizeCallback[T]] = None,
        # Custom serialization
        serialize: Optional[SerializeCallback[T]] = None,
        unserialize: Optional[UnserializeCallback[T]] = None,
        # Custom exporter
        exporter: Optional[FieldExporter[T]] = None
        ) -> T:
    pass


@overload
def field(
        *,
        # Options
        option: Optional[FieldCLIOption] = None,
        is_flag: bool = False,
        choices: Union[None, Sequence[str], Callable[[], Sequence[str]]] = None,
        multiple: bool = False,
        metavar: Optional[str] = None,
        envvar: Optional[str] = None,
        deprecated: Optional['tmt.options.Deprecated'] = None,
        help: Optional[str] = None,
        show_default: bool = False,
        internal: bool = False,
        # Input data normalization
        normalize: Optional[NormalizeCallback[T]] = None,
        # Custom serialization
        serialize: Optional[SerializeCallback[T]] = None,
        unserialize: Optional[UnserializeCallback[T]] = None,
        # Custom exporter
        exporter: Optional[FieldExporter[T]] = None
        ) -> T:
    pass


def field(
        *,
        default: Any = dataclasses.MISSING,
        default_factory: Any = None,
        # Options
        option: Optional[FieldCLIOption] = None,
        is_flag: bool = False,
        choices: Union[None, Sequence[str], Callable[[], Sequence[str]]] = None,
        multiple: bool = False,
        metavar: Optional[str] = None,
        envvar: Optional[str] = None,
        deprecated: Optional['tmt.options.Deprecated'] = None,
        help: Optional[str] = None,
        show_default: bool = False,
        internal: bool = False,
        # Input data normalization
        normalize: Optional[NormalizeCallback[T]] = None,
        # Custom serialization
        serialize: Optional[SerializeCallback[T]] = None,
        unserialize: Optional[UnserializeCallback[T]] = None,
        # Custom exporter
        exporter: Optional[FieldExporter[T]] = None
        ) -> Any:
    """
    Define a :py:class:`DataContainer` field.

    Effectively a fancy wrapper over :py:func:`dataclasses.field`, tailored for
    tmt code needs and simplification of various common tasks.

    :param default: if provided, this will be the default value for this field.
        Passed directly to :py:func:`dataclass.field`.
        It is an error to specify both ``default`` and ``default_factory``.
    :param default_factory: if provided, it must be a zero-argument callable
        that will be called when a default value is needed for this field.
        Passed directly to :py:func:`dataclass.field`.
        It is an error to specify both ``default`` and ``default_factory``.
    :param option: one or more command-line option names.
        Passed directly to :py:func:`click.option`.
    :param is_flag: marks this option as a flag.
        Passed directly to :py:func:`click.option`.
    :param choices: if provided, the command-line option would accept only
        the listed input values.
        Passed to :py:func:`click.option` as a :py:class:`click.Choice` instance.
    :param multiple: accept multiple arguments of the same name.
        Passed directly to :py:func:`click.option`.
    :param metavar: how the input value is represented in the help page.
        Passed directly to :py:func:`click.option`.
    :param envvar: environment variable used for this option.
        Passed directly to :py:func:`click.option`.
    :param deprecated: mark the option as deprecated
        Provide an instance of Deprecated() with version in which the
        option was obsoleted and an optional hint with the recommended
        alternative. A warning message will be added to the option help.
    :param help: the help string for the command-line option. Multiline strings
        can be used, :py:func:`textwrap.dedent` is applied before passing
        ``help`` to :py:func:`click.option`.
    :param show_default: show default value
        Passed directly to :py:func:`click.option`.
    :param internal: if set, the field is treated as internal-only, and will not
        appear when showing objects via ``show()`` method, or in export created
        by :py:meth:`Core._export`.
    :param normalize: a callback for normalizing the input value. Consumed by
        :py:class:`NormalizeKeysMixin`.
    :param serialize: a callback for custom serialization of the field value.
        Consumed by :py:class:`SerializableKeysMixin`.
    :param unserialize: a callback for custom unserialization of the field value.
        Consumed by :py:class:`SerializableKeysMixin`.
    :param exporter: a callback for custom export of the field value.
        Consumed by :py:class:`tmt.export.Exportable`.
    """

    if option:
        if is_flag is False and isinstance(default, bool):
            raise GeneralError(
                "Container field must be a flag to have boolean default value.")

        if is_flag is True and not isinstance(default, bool):
            raise GeneralError(
                "Container field must have a boolean default value when it is a flag.")

    metadata: FieldMetadata[T] = FieldMetadata(
        internal=internal,
        help=textwrap.dedent(help).strip() if help else None,
        _metavar=metavar,
        default=default,
        default_factory=default_factory,
        show_default=show_default,
        is_flag=is_flag,
        multiple=multiple,
        _choices=choices,
        envvar=envvar,
        deprecated=deprecated,
        cli_option=option,
        normalize_callback=normalize,
        serialize_callback=serialize,
        unserialize_callback=unserialize,
        export_callback=exporter)

    # ignore[call-overload]: returning "wrong" type on purpose. field() must be annotated
    # as if returning the value of type matching the field declaration, and the original
    # field() is called with wider argument types than expected, because we use our own
    # overloading to narrow types *our* custom field() accepts.
    return dataclasses.field(  # type: ignore[call-overload]
        default=default,
        default_factory=default_factory or dataclasses.MISSING,
        metadata={'tmt': metadata}
        )


@functools.cache
def is_selinux_supported() -> bool:
    """
    Returns ``true`` if SELinux filesystem is supported by the kernel, ``false`` otherwise.

    For detection ``/proc/filesystems`` is used, see ``man 5 filesystems`` for details.
    """
    with open('/proc/filesystems') as file:
        return any('selinuxfs' in line for line in file)


def locate_key_origin(node: fmf.Tree, key: str) -> Optional[fmf.Tree]:
    """
    Find an fmf node where the given key is defined.

    :param node: node to begin with.
    :param key: key to look for.
    :returns: first node in which the key is defined, ``None`` if ``node`` nor
        any of its parents define it.
    """

    # Find the closest parent with different key content
    while node.parent:
        if node.get(key) != node.parent.get(key):
            break
        node = node.parent

    # Return node only if the key is defined
    if node.get(key) is None:
        return None

    return node


def is_key_origin(node: fmf.Tree, key: str) -> bool:
    """
    Find out whether the given key is defined in the given node.

    :param node: node to check.
    :param key: key to check.
    :returns: ``True`` if the key is defined in ``node``, not by one of its
        parents, ``False`` otherwise.
    """

    origin = locate_key_origin(node, key)

    return origin is not None and node.name == origin.name


def resource_files(path: Union[str, Path], package: Union[str, ModuleType] = "tmt") -> Path:
    """
    Helper function to get path of package file or directory.

    A thin wrapper for :py:func:`importlib.resources.files`:
    ``files()`` returns ``Traversable`` object, though in our use-case
    it should always produce a :py:class:`pathlib.PosixPath` object.
    Converting it to :py:class:`tmt.utils.Path` instance should be
    safe and stick to the "``Path`` only!" rule in tmt's code base.

    :param path: file or directory path to retrieve, relative to the ``package`` root.
    :param package: package in which to search for the file/directory.
    :returns: an absolute path to the requested file or directory.
    """
    return Path(importlib.resources.files(package)) / path  # type: ignore[arg-type]


class Stopwatch(contextlib.AbstractContextManager['Stopwatch']):
    start_time: datetime.datetime
    end_time: datetime.datetime

    def __init__(self) -> None:
        pass

    def __enter__(self) -> 'Stopwatch':
        self.start_time = datetime.datetime.now(datetime.timezone.utc)

        return self

    def __exit__(self, *args: object) -> None:
        self.end_time = datetime.datetime.now(datetime.timezone.utc)

    @property
    def duration(self) -> datetime.timedelta:
        return self.end_time - self.start_time


def format_timestamp(timestamp: datetime.datetime) -> str:
    """ Convert timestamp to a human readable format """

    return timestamp.isoformat()


def format_duration(duration: datetime.timedelta) -> str:
    """ Convert duration to a human readable format """

    # A helper variable to hold the duration while we cut away days, hours and seconds.
    counter = int(duration.total_seconds())

    hours, counter = divmod(counter, 3600)
    minutes, seconds = divmod(counter, 60)

    return f'{hours:02}:{minutes:02}:{seconds:02}'


def retry(
        func: Callable[..., T],
        attempts: int,
        interval: int,
        label: str,
        logger: tmt.log.Logger,
        *args: Any,
        **kwargs: Any
        ) -> T:
    """
    Retry functionality to be used elsewhere in the code.

    :param func: function to be called with all unclaimed positional
        and keyword arguments.
    :param attempts: number of tries to call the function
    :param interval: amount of seconds to wait before a new try
    :param label: action to retry
    :returns: propagates return value of ``func``.
    """
    exceptions: list[Exception] = []
    for i in range(attempts):
        try:
            return func(*args, **kwargs)
        except Exception as exc:
            exceptions.append(exc)
            logger.debug(
                'retry',
                f"{label} failed, {attempts - i} retries left, "
                f"trying again in {interval:.2f} seconds.")
            logger.fail(str(exc))
            time.sleep(interval)
    raise RetryError(label, causes=exceptions)


def get_url_content(url: str) -> str:
    """ Get content of a given URL as a string """
    try:
        with retry_session() as session:
            response = session.get(url)

            if response.ok:
                return response.text

    except Exception as error:
        raise GeneralError(f"Could not open url '{url}'.") from error

    raise GeneralError(f"Could not open url '{url}'.")


def is_url(url: str) -> bool:
    """ Check if the given string is a valid URL """
    parsed = urllib.parse.urlparse(url)
    return bool(parsed.scheme and parsed.netloc)


#
# ReST rendering
#
class RestVisitor(docutils.nodes.NodeVisitor):
    """
    Custom renderer of docutils nodes.

    See :py:class:`docutils.nodes.NodeVisitor` for details, but the
    functionality is fairly simple: for each node type, a pair of
    methods is expected, ``visit_$NODE_TYPE`` and ``depart_$NODE_TYPE``.
    As the visitor class iterates over nodes in the document,
    corresponding methods are called. These methods render the given
    node, filling "rendered paragraphs" list with rendered strings.
    """

    def __init__(self, document: docutils.nodes.document, logger: Logger) -> None:
        super().__init__(document)

        self.logger = logger
        self.debug = functools.partial(logger.debug, level=4, topic=tmt.log.Topic.HELP_RENDERING)
        self.log_visit = functools.partial(
            logger.debug, 'visit', level=4, topic=tmt.log.Topic.HELP_RENDERING)
        self.log_departure = functools.partial(
            logger.debug, 'depart', level=4, topic=tmt.log.Topic.HELP_RENDERING)

        #: Collects all rendered paragraps - text, blocks, lists, etc.
        self._rendered_paragraphs: list[str] = []
        #: Collect components of a single paragraph - sentences, literals,
        #: list items, etc.
        self._rendered_paragraph: list[str] = []

        self.in_literal_block: bool = False
        self.in_note: bool = False
        self.in_warning: bool = False

        #: Used by rendering of nested blocks, e.g. paragraphs positioned
        #: as list items.
        self._indent: int = 0
        self._text_prefix: Optional[str] = None

    @property
    def rendered(self) -> str:
        """ Return the rendered document as a single string """

        return '\n'.join(self._rendered_paragraphs)

    def _emit(self, s: str) -> None:
        """ Add a string to the paragraph being rendered """

        self._rendered_paragraph.append(s)

    def _emit_paragraphs(self, paragraphs: list[str]) -> None:
        """ Add new rendered paragraphs """

        self._rendered_paragraphs += paragraphs

    def flush(self) -> None:
        """ Finalize rendering of the current paragraph """

        if not self._rendered_paragraph:
            self.nl()

        else:
            self._emit_paragraphs([''.join(self._rendered_paragraph)])
            self._rendered_paragraph = []

    def nl(self) -> None:
        """ Render a new, empty line """

        # To simplify the implementation, this is merging of multiple
        # empty lines into one. Rendering of nodes than does not have
        # to worry about an empty line already being on the stack.
        if self._rendered_paragraphs[-1] != '':
            self._emit_paragraphs([''])

    # Simple logging for nodes that have no effect
    def _noop_visit(self, node: docutils.nodes.Node) -> None:
        self.log_visit(str(node))

    def _noop_departure(self, node: docutils.nodes.Node) -> None:
        self.log_departure(str(node))

    # Node renderers
    visit_document = _noop_visit

    def depart_document(self, node: docutils.nodes.document) -> None:
        self.log_departure(str(node))

        self.flush()

    def visit_paragraph(self, node: docutils.nodes.paragraph) -> None:
        self.log_visit(str(node))

        if isinstance(node.parent, docutils.nodes.list_item):
            if self._text_prefix:
                self._emit(self._text_prefix)
                self._text_prefix = None

            else:
                self._emit(' ' * self._indent)

        elif self.in_note:
            self._emit(click.style('NOTE: ', fg='blue', bold=True))
            return

        elif self.in_warning:
            self._emit(click.style('WARNING: ', fg='yellow', bold=True))
            return

    def depart_paragraph(self, node: docutils.nodes.paragraph) -> None:
        self.log_departure(str(node))

        self.flush()

    def visit_Text(self, node: docutils.nodes.Text) -> None:  # noqa: N802
        self.log_visit(str(node))

        if isinstance(node.parent, docutils.nodes.literal):
            return

        if self.in_literal_block:
            return

        if self.in_note:
            self._emit(click.style(node.astext(), fg='blue'))

            return

        if self.in_warning:
            self._emit(click.style(node.astext(), fg='yellow'))

            return

        self._emit(node.astext())

    depart_Text = _noop_departure  # noqa: N815

    def visit_literal(self, node: docutils.nodes.literal) -> None:
        self.log_visit(str(node))

        self._emit(click.style(node.astext(), fg='green'))

    depart_literal = _noop_departure

    def visit_literal_block(self, node: docutils.nodes.literal_block) -> None:
        self.log_visit(str(node))

        self.flush()

        fg: str = 'cyan'

        if 'yaml' in node.attributes['classes']:
            pass

        elif 'shell' in node.attributes['classes']:
            fg = 'yellow'

        self._emit_paragraphs([
            f'    {click.style(line, fg=fg)}' for line in node.astext().splitlines()
            ])

        self.in_literal_block = True

    def depart_literal_block(self, node: docutils.nodes.literal_block) -> None:
        self.log_departure(str(node))

        self.in_literal_block = False

        self.nl()

    def visit_bullet_list(self, node: docutils.nodes.bullet_list) -> None:
        self.log_visit(str(node))

        self.nl()

    def depart_bullet_list(self, node: docutils.nodes.bullet_list) -> None:
        self.log_departure(str(node))

        self.nl()

    def visit_list_item(self, node: docutils.nodes.list_item) -> None:
        self.log_visit(str(node))

        self._text_prefix = '* '
        self._indent += 2

    def depart_list_item(self, node: docutils.nodes.list_item) -> None:
        self.log_departure(str(node))

        self._indent -= 2

    visit_inline = _noop_visit
    depart_inline = _noop_departure

    visit_reference = _noop_visit
    depart_reference = _noop_departure

    def visit_note(self, node: docutils.nodes.note) -> None:
        self.log_visit(str(node))

        self.nl()
        self.in_note = True

    def depart_note(self, node: docutils.nodes.note) -> None:
        self.log_departure(str(node))

        self.in_note = False
        self.nl()

    def visit_warning(self, node: docutils.nodes.warning) -> None:
        self.log_visit(str(node))

        self.nl()
        self.in_warning = True

    def depart_warning(self, node: docutils.nodes.warning) -> None:
        self.log_departure(str(node))

        self.in_warning = False
        self.nl()

    def unknown_visit(self, node: docutils.nodes.Node) -> None:
        raise GeneralError(f"Unhandled ReST node '{node}'.")

    def unknown_departure(self, node: docutils.nodes.Node) -> None:
        raise GeneralError(f"Unhandled ReST node '{node}'.")


def parse_rst(text: str) -> docutils.nodes.document:
    """ Parse a ReST document into docutils tree of nodes """

    parser = docutils.parsers.rst.Parser()
    components = (docutils.parsers.rst.Parser,)
    settings = docutils.frontend.OptionParser(components=components).get_default_values()
    document = docutils.utils.new_document('<rst-doc>', settings=settings)

    parser.parse(text, document)

    return document


def render_rst(text: str, logger: Logger) -> str:
    """ Render a ReST document """

    document = parse_rst(text)
    visitor = RestVisitor(document, logger)

    document.walkabout(visitor)

    return visitor.rendered
