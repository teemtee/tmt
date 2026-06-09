import abc
import contextlib
import os
import re
import shlex
from collections.abc import Generator, Iterable, Mapping, Sequence
from typing import (
    TYPE_CHECKING,
    Any,
    Optional,
    Union,
    cast,
)

import requests

import tmt.log
from tmt._compat.pathlib import Path
from tmt._compat.typing import Self

if TYPE_CHECKING:
    from tmt._compat.typing import TypeAlias
    from tmt.utils import FmfContext, ShellScript


#: A type of environment variable name.
EnvVarName: 'TypeAlias' = str

# This one is not an alias: a full-fledged class makes type linters
# enforce strict instantiation of objects rather than accepting
# strings where `EnvVarValue` is expected.


class EnvVarValue(str):
    """
    A type of environment variable value
    """

    def __new__(cls, raw_value: Any) -> Self:
        if isinstance(raw_value, str):
            return str.__new__(cls, raw_value)

        if isinstance(raw_value, Path):
            return str.__new__(cls, str(raw_value))

        from tmt.utils import GeneralError

        raise GeneralError(
            f"Only strings and paths can be environment variables, '{type(raw_value)}' found."
        )


@container
class EnvVar:
    """
    An environment variable recognized by tmt.
    """

    class Scope:
        """
        Scopes of environment variables.
        """

        #: Environment variable is consumed by tmt process itself.
        TMT = {'tmt'}

        #: Environment variable is exposed to ``discover`` phases.
        DISCOVER = {'discover'}

        #: Environment variable is exposed to ``provision`` phases.
        PROVISION = {'provision'}

        #: Environment variable is exposed to ``prepare`` phases.
        PREPARE = {'prepare'}

        #: Environment variable is exposed to ``execute`` phases.
        EXECUTE = {'execute'}

        #: Environment variable is exposed to ``finish`` phases.
        FINISH = {'finish'}

        #: Environment variable is exposed to individual tests..
        TEST = {'test'}

    #: Name of the environment variable
    name: EnvVarName

    #: Scope of the environment variable.
    scope: set[str] = simple_field(default_factory=set[str])

    def __init__(
        self,
        *,
        name: str,
        scope: Optional[set[str]] = None,
        doc: Optional[str] = None,
    ) -> None:
        self.name = name
        self.scope = scope or set()

        self.__doc__ = (
            textwrap.dedent(doc).strip() if doc else 'This environment variable is undocumented.'
        )


class HasEnvironment(abc.ABC):
    """
    A class that provides :py:attr:`environment` attribute.
    """

    @property
    @abc.abstractmethod
    def environment(self) -> 'Environment':
        """
        Environment variables this object wants to expose to user commands.
        """

        raise NotImplementedError


class Environment(dict[str, EnvVarValue]):
    """
    Represents a set of environment variables.

    See https://tmt.readthedocs.io/en/latest/spec/tests.html#environment,
    https://tmt.readthedocs.io/en/latest/spec/plans.html#environment and
    https://tmt.readthedocs.io/en/latest/spec/plans.html#environment-file.
    """

    def __init__(self, data: Optional[dict[Union[EnvVar, EnvVarName], EnvVarValue]] = None) -> None:
        super().__init__(
            {
                (key.name if isinstance(key, EnvVar) else key): value
                for key, value in (data or {}).items()
            }
        )

    def __getitem__(self, key: Union[EnvVar, EnvVarName]) -> EnvVarValue:
        return super().__getitem__(key.name if isinstance(key, EnvVar) else key)

    def __setitem__(self, key: Union[EnvVar, EnvVarName], value: EnvVarValue) -> None:
        super().__setitem__((key.name if isinstance(key, EnvVar) else key), value)

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
            from tmt.utils import GeneralError

            raise GeneralError("Failed to extract variables from 'dotenv' format.") from exc

        return environment

    @classmethod
    def from_yaml(cls, content: str) -> 'Environment':
        """
        Construct environment from a YAML format.

        :param content: string containing variables defined in a YAML
            dictionary, i.e. ``key: value`` entries.
        """

        from tmt.utils import yaml_to_dict

        data = yaml_to_dict(content)

        if any(isinstance(v, (dict, list)) for v in data.values()):
            from tmt.utils import GeneralError

            raise GeneralError(
                'Failed to extract variables from YAML format, '
                'only primitive types are accepted as values.'
            )

        return Environment({key: EnvVarValue(str(value)) for key, value in data.items()})

    @classmethod
    def from_yaml_file(
        cls,
        filepath: Path,
        logger: tmt.log.Logger,
    ) -> 'Environment':
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
            from tmt.utils import GeneralError

            raise GeneralError(
                f"Failed to extract variables from YAML file '{filepath}'."
            ) from exc

        return cls.from_yaml(content)

    @classmethod
    def from_sequence(
        cls,
        raw_variables: Union[str, Sequence[str]],
        logger: tmt.log.Logger,
    ) -> 'Environment':
        """
        Construct environment from a sequence of variables.

        Variables may be specified in two ways:

        * ``NAME=VALUE`` pairs, or
        * ``@foo.yaml`` signaling variables to be read from a file.

        If a "variable" starts with ``@``, it is treated as a path to
        a YAML or DOTENV file that contains key/value pairs which are then
        transparently loaded and added to the final environment.

        :param raw_variables: string or a sequence of strings containing
            variables. The acceptable formats are:

            * ``'X=1'``
            * ``'X=1 Y=2 Z=3'``
            * ``['X=1', 'Y=2', 'Z=3']``
            * ``['X=1 Y=2 Z=3', 'A=1 B=2 C=3']``
            * ``'TXT="Some text with spaces in it"'``
            * ``@foo.yaml``
            * ``@../../bar.yaml``
            * ``@foo.env``
        """

        if isinstance(raw_variables, str):
            variables: Iterable[str] = [raw_variables]

        else:
            variables = raw_variables

        result = Environment()

        for variable in variables:
            if variable is None:  # type: ignore[reportUnnecessary,unused-ignore]
                continue
            for var in shlex.split(variable):
                if var.startswith('@'):
                    if not var[1:]:
                        from tmt.utils import GeneralError

                        raise GeneralError(f"Invalid variable file specification '{var}'.")

                    filename = var[1:]
                    environment = cls.from_file(filename=filename, logger=logger)

                    if not environment:
                        logger.warning(f"Empty environment file '{filename}'.")

                    result.update(environment)

                else:
                    matched = re.match("([^=]+)=(.*)", var)
                    if not matched:
                        from tmt.utils import GeneralError

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
        logger: tmt.log.Logger,
    ) -> 'Environment':
        """
        Construct environment from a file.

        YAML files - recognized by ``.yaml`` or ``.yml`` suffixes - or
        ``.env``-like files are supported.

        .. code-block:: bash

           A=B
           C=D

        .. code-block:: yaml

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
            from tmt.utils import retry_session

            # Create retry session for longer retries, see #1229
            session = retry_session.create(
                allowed_methods=('GET',),
                logger=logger,
            )
            try:
                response = session.get(filename)
                response.raise_for_status()
                content = response.text
            except requests.RequestException as error:
                from tmt.utils import GeneralError

                raise GeneralError(
                    f"Failed to extract variables from URL '{filename}'."
                ) from error

        # Read a local file
        else:
            # Ensure we don't escape from the metadata tree root

            root = root.resolve()
            environment_filepath = root.joinpath(filename).resolve()

            if not environment_filepath.is_relative_to(root):
                from tmt.utils import GeneralError

                raise GeneralError(
                    f"Failed to extract variables from file '{environment_filepath}' as it "
                    f"lies outside the metadata tree root '{root}'."
                )
            if not environment_filepath.is_file():
                from tmt.utils import GeneralError

                raise GeneralError(f"File '{environment_filepath}' doesn't exist.")

            content = environment_filepath.read_text()

        # Parse yaml file
        if Path(filename).suffix.lower() in ('.yaml', '.yml'):
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
        logger: tmt.log.Logger,
    ) -> 'Environment':
        """
        Read environment variables from the given list of files.

        Files should be in YAML format (``.yaml`` or ``.yml`` suffixes), or in dotenv format.

        .. code-block:: bash

           A=B
           C=D

        .. code-block:: yaml

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
    def from_cli_options(
        cls,
        *,
        raw_cli_environment_files: Sequence[str],
        raw_cli_environment: Sequence[str],
        file_root: Optional[Path] = None,
        logger: tmt.log.Logger,
    ) -> Self:
        """
        Extract environment variables from CLI options.

        Combines ``--environment-file`` and ``--environment`` options
        into a set of environment variables. Both options are optional,
        and there is a clear order of preference, which is,
        from the least preferred:

        * ``--environment-file``
        * ``--environment``

          .. note::

             This set includes also files with environment variables
             when such files are pointed at using the ``@<filepath>``
             form.

        :param raw_cli_environment_files: content of the `--environment-file``
            CLI option.
        :param raw_cli_environment: content of the ``--environment`` CLI
            option.
        """

        # Combine all sources into one mapping, honor the order in which
        # they override other sources.
        return cls(
            {
                **cls.from_files(
                    filenames=raw_cli_environment_files,
                    root=file_root,
                    logger=logger,
                ),
                **cls.from_sequence(
                    raw_variables=raw_cli_environment,
                    logger=logger,
                ),
            }
        )

    @classmethod
    def from_fmf_keys(
        cls,
        *,
        raw_fmf_environment_files: Sequence[str],
        raw_fmf_environment: Mapping[str, Any],
        file_root: Optional[Path] = None,
        logger: tmt.log.Logger,
    ) -> Self:
        """
        Extract environment variables from fmf keys.

        Combines ``environment-file`` and ``environment`` fmf keys
        into a set of environment variables. Both keys are optional,
        and there is a clear order of preference, which is,
        from the least preferred:

        * ``environment-file``
        * ``environment``

          .. note::

             This set includes also files with environment variables
             when such files are pointed at using the ``@<filepath>``
             form.

        :param raw_fmf_environment_files: content of the `environment-file``
            key.
        :param raw_fmf_environment: content of the ``environment`` key.
        """

        # Combine all sources into one mapping, honor the order in which
        # they override other sources.
        return cls(
            {
                **cls.from_files(
                    filenames=raw_fmf_environment_files,
                    root=file_root,
                    logger=logger,
                ),
                **cls.from_dict(
                    raw_fmf_environment,
                ),
            }
        )

    @classmethod
    def from_dict(cls, data: Optional[Mapping[str, Any]] = None) -> 'Environment':
        """
        Create environment variables from a dictionary
        """

        if not data:
            return Environment()

        return Environment({str(key): EnvVarValue(str(value)) for key, value in data.items()})

    @classmethod
    def from_environ(cls) -> 'Environment':
        """
        Extract environment variables from the live environment
        """

        return Environment({key: EnvVarValue(value) for key, value in os.environ.items()})

    @classmethod
    def from_fmf_context(cls, fmf_context: 'FmfContext') -> 'Environment':
        """
        Create environment variables from an fmf context
        """

        return Environment(
            {key: EnvVarValue(','.join(value)) for key, value in fmf_context.items()}
        )

    @classmethod
    def from_fmf_spec(cls, data: Optional[dict[str, Any]] = None) -> 'Environment':
        """
        Create environment from an fmf specification
        """

        if not data:
            return Environment()

        return Environment({key: EnvVarValue(str(value)) for key, value in data.items()})

    def to_fmf_spec(self) -> dict[str, str]:
        """
        Convert to an fmf specification
        """

        return {key: str(value) for key, value in self.items()}

    def to_popen(self) -> dict[str, str]:
        """
        Convert to a form accepted by :py:class:`subprocess.Popen`
        """

        return self.to_environ()

    def to_environ(self) -> dict[str, str]:
        """
        Convert to a form compatible with :py:attr:`os.environ`
        """

        return {key: str(value) for key, value in self.items()}

    def to_shell(self) -> list[str]:
        """
        Convert to a form accepted by shell commands.

        .. code-block:: python

            >>> Environment({'FOO': EnvVarValue('bar'), 'BAZ': EnvVarValue('qu ux')}).to_shell()
            ['FOO=bar', "BAZ='qu ux'"]
        """

        return [f"{key}={shlex.quote(str(value))}" for key, value in self.items()]

    def to_shell_exports(self) -> list['ShellScript']:
        """
        Convert to a sequence of ``export`` shell commands.

        .. code-block:: python

            >>> Environment({'FOO': EnvVarValue('bar'), 'BAZ': EnvVarValue('qu ux')}).to_shell_exports()
            [ShellScript("export FOO=bar"), ShellScript("export BAZ='qu ux'")]
        """  # noqa: E501

        from tmt.utils import ShellScript

        return [ShellScript(f'export {variable}') for variable in self.to_shell()]

    def copy(self) -> 'Environment':
        return Environment(self)

    def update(  # type: ignore[override]
        self, *others: Union[dict[str, EnvVarValue], HasEnvironment]
    ) -> None:
        for other in others:
            if isinstance(other, dict):
                super().update(other)

            else:
                super().update(other.environment)

    @classmethod
    def normalize(
        cls,
        key_address: str,
        value: Any,
        logger: tmt.log.Logger,
    ) -> 'Environment':
        """
        Normalize value of ``environment`` key
        """

        # Note: this normalization callback is an exception, it does not
        # bother with CLI input. Environment handling is complex, and CLI
        # options have their special handling. The `environment` as an
        # fmf key does not really have a 1:1 CLI option, the corresponding
        # options are always "special".
        if value is None:
            return cls()

        if isinstance(value, dict):
            # redundant-cast: mypy sees it as redundant, pyright does
            # need it, since `isinstance(value, dict)` says nothing
            # about types of keys or values.
            return cls(
                {
                    k: EnvVarValue(str(v))
                    for k, v in cast(dict[Any, Any], value).items()  # type: ignore[redundant-cast]
                }
            )

        from tmt.utils import NormalizationError

        raise NormalizationError(key_address, value, 'unset or a dictionary')

    @contextlib.contextmanager
    def as_environ(self) -> Generator[None]:
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
        os.environ.update(self.to_environ())
        try:
            yield
        finally:
            os.environ.clear()
            os.environ.update(environ_backup)
