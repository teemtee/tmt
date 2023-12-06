"""
tmt's logging subsystem.

Adds a layer on top of Python's own :py:mod:`logging` subsystem. This layer implements the desired
verbosity and debug levels, colorization, formatting, verbosity inheritance and other features used
by tmt commands and code.

The main workhorses are :py:class:`Logger` instances. Each instance wraps a particular
:py:class:`logging.Logger` instance - usually there's a chain of such instances, with the root one
having console and logfile handlers attached. tmt's log verbosity/debug/quiet features are handled
on our side, with the use of :py:class:`logging.Filter` classes.

``Logger`` instances can be cloned and modified, to match various levels of tmt's runtime class
tree - ``tmt`` spawns a "root logger" from which a new one is cloned - and indented by one extra
level - for ``Run`` instance, and so on. This way, every object in tmt's hierarchy uses a given
logger, which may have its own specific settings, and, in the future, possibly also handlers for
special output channels.

While tmt recognizes several levels of verbosity (``-v``) and debugging (``-d``), all messages
emitted by :py:meth:`Logger.verbose` and :py:meth:`Logger.debug` use a single logging level,
``INFO`` or ``DEBUG``, respectively. The level of verbosity and debugging is then handled by a
special :py:class:`logging.Filter`` classes. This allows different levels when logging to console
but all-capturing log files while keeping implementation simple - the other option would be
managing handlers themselves, which would be very messy given the propagation of messages.
"""

import dataclasses
import enum
import itertools
import logging
import logging.handlers
import os
import sys
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Optional,
    Protocol,
    Union,
    cast,
    )

import click

if TYPE_CHECKING:
    import tmt.cli
    import tmt.utils

# Log in workdir
LOG_FILENAME = 'log.txt'

# Hierarchy indent
INDENT = 4

DEFAULT_VERBOSITY_LEVEL = 0
DEFAULT_DEBUG_LEVEL = 0


class Topic(enum.Enum):
    KEY_NORMALIZATION = 'key-normalization'
    CLI_INVOCATIONS = 'cli-invocations'
    COMMAND_EVENTS = 'command-events'
    ADJUST_DECISIONS = 'adjust-decisions'
    HELP_RENDERING = 'help-rendering'


DEFAULT_TOPICS: set[Topic] = set()


LABEL_FORMAT = '[{label}]'


LoggableValue = Union[
    str,
    int,
    bool,
    float,
    'tmt.utils.Path',
    'tmt.utils.Command',
    'tmt.utils.ShellScript']


# TODO: this is an ugly hack, removing colors after they have been added...
# Wouldn't it be better to not add them at first place?
#
# This is needed to deal with the code that colorizes just part of the message, like
# tmt.result.Result outcomes: these are colorized, then merged with the number
# of such outcomes, for example, and the string is handed over to logging method.
# When colors are *not* to be applied, it's too late because colors have been
# applied already. Something to fix...
def _dont_decolorize(s: str) -> str:
    return s


def create_decolorizer(apply_colors: bool) -> Callable[[str], str]:
    if apply_colors:
        return _dont_decolorize

    import tmt.utils

    return tmt.utils.remove_color


def _debug_level_from_global_envvar() -> int:
    import tmt.utils

    raw_value = os.getenv('TMT_DEBUG', None)

    if raw_value is None:
        return 0

    try:
        return int(raw_value)

    except ValueError:
        raise tmt.utils.GeneralError(f"Invalid debug level '{raw_value}', use an integer.")


def decide_colorization(no_color: bool, force_color: bool) -> tuple[bool, bool]:
    """
    Decide whether the output and logging should be colorized.

    Based on values of CLI options, environment variables and output stream
    properties, a colorization setup is decided. The following inputs are
    evaluated, in this order:

    * if either of the ``--no-color`` CLI option, ``NO_COLOR`` or
        ``TMT_NO_COLOR`` environment variables are set, colorization would be
        disabled.
    * if either of the ``--force-color`` CLI option or ``TMT_FORCE_COLOR``
        environment variable are set, colorization would be forcefully
        enabled.

    If none of the situations above happened, colorization would be enabled for
    output and logging based on their respective stream TTY status. Output is
    sent to standard output, logging then to standard error output,
    colorization would then be the outcome of stream's :py:meth:`file.isatty`
    method.

    .. note::

       Be aware that "forced enable" is stronger than "forced disable". If
       ``--force-color`` or ``TMT_FORCE_COLOR`` are set, colors will be enabled
       despite any disabling options or environment variables.

    .. note::

       All inputs with the exception of ``isatty`` result control both types of
       output, regular output and logging, and applies to both of them. Only
       ``isatty`` outcome is specific for each type, and may result in one
       output type dropping colors while the other would be colorized.

    :param no_color: value of the ``--no-color`` CLI option.
    :param force_color: value of the `--force-color`` CLI option.
    :returns: a tuple of two booleans, one for output colorization, the other
        for logging colorization.
    """

    # Default values: assume colors & unicorns everywhere.
    apply_colors_output = apply_colors_logging = True

    # Enforce colors if `--force-color` was used, or `TMT_FORCE_COLOR` envvar is set.
    if force_color or 'TMT_FORCE_COLOR' in os.environ:
        apply_colors_output = apply_colors_logging = True

    # Disable coloring if `--no-color` was used, or `NO_COLOR` or `TMT_NO_COLOR` envvar is set.
    elif no_color or 'NO_COLOR' in os.environ or 'TMT_NO_COLOR' in os.environ:
        apply_colors_output = apply_colors_logging = False

    # Autodetection, disable colors when not talking to a terminal.
    else:
        apply_colors_output = sys.stdout.isatty()
        apply_colors_logging = sys.stderr.isatty()

    return apply_colors_output, apply_colors_logging


def render_labels(labels: list[str]) -> str:
    if not labels:
        return ''

    return ''.join(
        # TODO: color here is questionable - it will be removed, but I'd rather not
        # add it at first place, and it should be configurable.
        click.style(LABEL_FORMAT.format(label=label), fg='cyan')
        for label in labels
        )


def indent(
        key: str,
        value: Optional[LoggableValue] = None,
        color: Optional[str] = None,
        level: int = 0,
        labels: Optional[list[str]] = None,
        labels_padding: int = 0) -> str:
    """
    Indent a key/value message.

    If both ``key`` and ``value`` are specified, ``{key}: {value}``
    message is rendered. Otherwise, just ``key`` is used alone. If
    ``value`` contains multiple lines, each but the very first line is
    indented by one extra level.

    :param value: optional value to print at right side of ``key``.
    :param color: optional color to apply on ``key``.
    :param level: number of indentation levels. Each level is indented
                  by :py:data:`INDENT` spaces.
    :param labels: optional list of strings to prepend to each message.
        Each item would be wrapped within square brackets (``[foo] message...``).
    :param labels_padding: if set, rendered labels would be padded to this
        length.
    """

    indent = ' ' * INDENT * level

    # Colorize
    if color is not None:
        key = click.style(key, fg=color)

    # Prepare prefix if labels provided
    prefix = render_labels(labels).ljust(labels_padding) + ' ' if labels else ''

    # Handle key only
    if value is None:
        return f'{prefix}{indent}{key}'

    # Key + non-string values
    if not isinstance(value, str):
        from tmt.utils import format_value

        value = format_value(value, wrap=False)

    # If there's just a single line (or less...), emit just that line,
    # with prefix and indentation, of course.
    lines = value.splitlines()
    if len(lines) <= 1:
        return f'{prefix}{indent}{key}: {value}'

    # If we have multiple lines to emit, a key is emitted on its own line,
    # and all lines of the value are emitted below the key, all with an
    # extra bit of indentation ("deeper").
    deeper = ' ' * INDENT

    return f'{prefix}{indent}{key}:\n' \
        + '\n'.join(f'{prefix}{indent}{deeper}{line}' for line in lines)


@dataclasses.dataclass
class LogRecordDetails:
    """ tmt's log message components attached to log records """

    key: str
    value: Optional[LoggableValue] = None

    color: Optional[str] = None
    shift: int = 0

    logger_labels: list[str] = dataclasses.field(default_factory=list)
    logger_labels_padding: int = 0

    logger_verbosity_level: int = 0
    message_verbosity_level: Optional[int] = None

    logger_debug_level: int = 0
    message_debug_level: Optional[int] = None

    logger_quiet: bool = False
    ignore_quietness: bool = False

    logger_topics: set[Topic] = dataclasses.field(default_factory=set)
    message_topic: Optional[Topic] = None


class LogfileHandler(logging.FileHandler):
    def __init__(self, filepath: 'tmt.utils.Path') -> None:
        super().__init__(filepath, mode='a')


# ignore[type-arg]: StreamHandler is a generic type, but such expression would be incompatible
# with older Python versions. Since it's not critical to mark the handler as "str only", we can
# ignore the issue for now.
class ConsoleHandler(logging.StreamHandler):  # type: ignore[type-arg]
    pass


class _Formatter(logging.Formatter):
    def __init__(self, fmt: str, apply_colors: bool = False) -> None:
        super().__init__(fmt, datefmt='%H:%M:%S')

        self.apply_colors = apply_colors

        self._decolorize = create_decolorizer(apply_colors)

    def format(self, record: logging.LogRecord) -> str:
        if self.usesTime():
            record.asctime = self.formatTime(record, self.datefmt)

        # When message already exists, do nothing - it either some other logging subsystem,
        # or tmt's own, already rendered message.
        if hasattr(record, 'message'):
            pass

        # Otherwise render the message.
        else:
            if record.msg and record.args:
                record.message = record.msg % record.args

            else:
                record.message = record.msg

        # Original code from Formatter.format() - hard to inherit when overriding
        # Formatter.format()...
        s = self._decolorize(self.formatMessage(record))
        # SIM102: Use a single `if` statement instead of nested `if` statements. Keeping for
        # readability.
        if record.exc_info:  # noqa: SIM102
            # Cache the traceback text to avoid converting it multiple times
            # (it's constant anyway)
            if not record.exc_text:
                record.exc_text = self.formatException(record.exc_info)
        if record.exc_text:
            if s[-1:] != "\n":
                s = s + "\n"
            s = s + record.exc_text
        if record.stack_info:
            if s[-1:] != "\n":
                s = s + "\n"
            s = s + self.formatStack(record.stack_info)
        return s


class LogfileFormatter(_Formatter):
    def __init__(self) -> None:
        super().__init__('%(asctime)s %(message)s', apply_colors=False)


class ConsoleFormatter(_Formatter):
    def __init__(self, apply_colors: bool = True, show_timestamps: bool = False) -> None:
        super().__init__(
            '%(asctime)s %(message)s' if show_timestamps else '%(message)s',
            apply_colors=apply_colors)


class VerbosityLevelFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno != logging.INFO:
            return True

        details: Optional[LogRecordDetails] = getattr(record, 'details', None)

        if details is None:
            return True

        if details.message_verbosity_level is None:
            return True

        return details.logger_verbosity_level >= details.message_verbosity_level


class DebugLevelFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno != logging.DEBUG:
            return True

        details: Optional[LogRecordDetails] = getattr(record, 'details', None)

        if details is None:
            return True

        if details.message_debug_level is None:
            return True

        return details.logger_debug_level >= details.message_debug_level


class QuietnessFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno not in (logging.DEBUG, logging.INFO):
            return True

        details: Optional[LogRecordDetails] = getattr(record, 'details', None)

        if details is None:
            return False

        if not details.logger_quiet:
            return True

        if details.ignore_quietness:
            return True

        return False


class TopicFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno not in (logging.DEBUG, logging.INFO):
            return True

        details: Optional[LogRecordDetails] = getattr(record, 'details', None)

        if details is None:
            return False

        if details.message_topic is None:
            return True

        if details.message_topic in details.logger_topics:
            return True

        return False


class LoggingFunction(Protocol):
    def __call__(
            self,
            key: str,
            value: Optional[str] = None,
            color: Optional[str] = None,
            shift: int = 0,
            level: int = 1,
            topic: Optional[Topic] = None) -> None:
        pass


class Logger:
    """
    A logging entry point, representing a certain level of verbosity and handlers.

    Provides actual logging methods plus methods for managing verbosity levels
    and handlers.
    """

    def __init__(
            self,
            actual_logger: logging.Logger,
            base_shift: int = 0,
            labels: Optional[list[str]] = None,
            labels_padding: int = 0,
            verbosity_level: int = DEFAULT_VERBOSITY_LEVEL,
            debug_level: int = DEFAULT_DEBUG_LEVEL,
            quiet: bool = False,
            topics: Optional[set[Topic]] = None,
            apply_colors_output: bool = True,
            apply_colors_logging: bool = True
            ) -> None:
        """
        Create a ``Logger`` instance with given verbosity levels.

        :param actual_logger: a :py:class:`logging.Logger` instance, the raw logger
            to use for logging.
        :param base_shift: shift applied to all messages processed by this logger.
        :param labels_padding: if set, rendered labels would be padded to this
            length.
        :param verbosity_level: desired verbosity level, usually derived from ``-v``
            command-line option.
        :param debug_level: desired debugging level, usually derived from ``-d``
            command-line option.
        :param quiet: if set, all messages would be supressed, with the exception of
            warnings (:py:meth:`warn`), errors (:py:meth:`fail`) and messages emitted
            with :py:meth:`print`.
        """

        self._logger = actual_logger

        self._base_shift = base_shift

        self._child_id_counter = itertools.count()

        self.labels = labels or []
        self.labels_padding = labels_padding

        self.verbosity_level = verbosity_level
        self.debug_level = debug_level
        self.quiet = quiet
        self.topics = topics or DEFAULT_TOPICS

        self.apply_colors_output = apply_colors_output
        self.apply_colors_logging = apply_colors_logging

        self._decolorize_output = create_decolorizer(apply_colors_output)

    def __repr__(self) -> str:
        return '<Logger:' \
            f' name={self._logger.name}' \
            f' verbosity={self.verbosity_level}' \
            f' debug={self.debug_level}' \
            f' quiet={self.quiet}' \
            f' topics={self.topics}' \
            f' apply_colors_output={self.apply_colors_output}' \
            f' apply_colors_logging={self.apply_colors_logging}' \
            '>'

    @property
    def labels_span(self) -> int:
        """ Length of rendered labels """
        return len(render_labels(self.labels))

    @staticmethod
    def _normalize_logger(logger: logging.Logger) -> logging.Logger:
        """ Reset properties of a given :py:class:`logging.Logger` instance """

        logger.propagate = True
        logger.level = logging.DEBUG

        logger.handlers = []

        return logger

    def clone(self) -> 'Logger':
        """
        Create a copy of this logger instance.

        All its settings are propagated to new instance. Settings are **not** shared,
        and may be freely modified after cloning without affecting the other logger.
        """

        return Logger(
            self._logger,
            base_shift=self._base_shift,
            labels=self.labels[:],
            labels_padding=self.labels_padding,
            verbosity_level=self.verbosity_level,
            debug_level=self.debug_level,
            quiet=self.quiet,
            topics=self.topics,
            apply_colors_output=self.apply_colors_output,
            apply_colors_logging=self.apply_colors_logging
            )

    def descend(
            self,
            logger_name: Optional[str] = None,
            extra_shift: int = 1
            ) -> 'Logger':
        """
        Create a copy of this logger instance, but with a new raw logger.

        New :py:class:`logging.Logger` instance is created from our raw logger, forming a
        parent/child relationship betwen them, and it's then wrapped with ``Logger`` instance.
        Settings of this logger are copied to new one, with the exception of ``base_shift``
        which is increased by one, effectively indenting all messages passing through new logger.

        :param logger_name: optional name for the underlying :py:class:`logging.Logger` instance.
            Useful for debugging. If not set, a generic one is created.
        :param extra_shift: by how many extra levels should messages be indented by new logger.
        """

        logger_name = logger_name or f'logger{next(self._child_id_counter)}'
        actual_logger = self._normalize_logger(self._logger.getChild(logger_name))

        return Logger(
            actual_logger,
            base_shift=self._base_shift + extra_shift,
            labels=self.labels[:],
            labels_padding=self.labels_padding,
            verbosity_level=self.verbosity_level,
            debug_level=self.debug_level,
            quiet=self.quiet,
            topics=self.topics,
            apply_colors_output=self.apply_colors_output,
            apply_colors_logging=self.apply_colors_logging
            )

    def add_logfile_handler(self, filepath: 'tmt.utils.Path') -> None:
        """ Attach a log file handler to this logger """

        handler = LogfileHandler(filepath)

        handler.setFormatter(LogfileFormatter())

        handler.addFilter(TopicFilter())

        self._logger.addHandler(handler)

    def add_console_handler(self, show_timestamps: bool = False) -> None:
        """
        Attach console handler to this logger.

        :param show_timestamps: when set, emitted messages would include
            the time.
        """

        handler = ConsoleHandler(stream=sys.stderr)

        handler.setFormatter(ConsoleFormatter(
            apply_colors=self.apply_colors_logging,
            show_timestamps=show_timestamps))

        handler.addFilter(VerbosityLevelFilter())
        handler.addFilter(DebugLevelFilter())
        handler.addFilter(QuietnessFilter())
        handler.addFilter(TopicFilter())

        self._logger.addHandler(handler)

    def apply_verbosity_options(
            self,
            cli_invocation: Optional['tmt.cli.CliInvocation'] = None,
            **kwargs: Any) -> 'Logger':
        """
        Update logger's settings to match given CLI options.

        Use this method to update logger's settings after :py:meth:`Logger.descend` call,
        to reflect options given to a tmt subcommand.
        """

        actual_kwargs: dict[str, Any] = {}

        if cli_invocation is not None:
            actual_kwargs = cli_invocation.options

        actual_kwargs.update(kwargs)

        verbosity_level = cast(Optional[int], actual_kwargs.get('verbose', None))
        if verbosity_level is None or verbosity_level == 0:
            pass

        else:
            self.verbosity_level = verbosity_level

        debug_level_from_global_envvar = _debug_level_from_global_envvar()

        if debug_level_from_global_envvar not in (None, 0):
            self.debug_level = debug_level_from_global_envvar

        else:
            debug_level_from_option = cast(Optional[int], actual_kwargs.get('debug', None))

            if debug_level_from_option is None or debug_level_from_option == 0:
                pass

            else:
                self.debug_level = debug_level_from_option

        quietness_level = actual_kwargs.get('quiet', False)

        if quietness_level is True:
            self.quiet = quietness_level

        topic_specs = actual_kwargs.get('log_topic', [])

        for topic_spec in topic_specs:
            try:
                self.topics.add(Topic(topic_spec))

            except Exception:
                import tmt.utils

                raise tmt.utils.GeneralError(
                    f'Logging topic "{topic_spec}" is invalid.'
                    f" Possible choices are {', '.join(topic.value for topic in Topic)}")

        return self

    @classmethod
    def create(
            cls,
            actual_logger: Optional[logging.Logger] = None,
            apply_colors_output: bool = True,
            apply_colors_logging: bool = True,
            **verbosity_options: Any) -> 'Logger':
        """
        Create a (root) tmt logger.

        This method has a very limited set of use cases:

        * CLI bootstrapping right after tmt started.
        * Unit tests of code that requires logger as one of its inputs.
        * 3rd party apps treating tmt as a library, i.e. when they wish tmt to
          use their logger instead of tmt's default one.

        :param actual_logger: a :py:class:`logging.Logger` instance to wrap.
            If not set, a default logger named ``tmt`` is created.
        """

        actual_logger = actual_logger or cls._normalize_logger(logging.getLogger('tmt'))

        return Logger(
            actual_logger,
            apply_colors_output=apply_colors_output,
            apply_colors_logging=apply_colors_logging) \
            .apply_verbosity_options(**verbosity_options)

    def _log(
            self,
            level: int,
            details: LogRecordDetails,
            message: str = ''
            ) -> None:
        """
        Emit a log record describing the message and related properties.

        This method converts tmt's specific logging approach, with keys, values, colors
        and shifts, to :py:class:`logging.LogRecord` instances compatible with :py:mod:`logging`
        workflow and carrying extra information for our custom filters and handlers.
        """

        details.logger_labels = self.labels
        details.logger_labels_padding = self.labels_padding

        details.logger_verbosity_level = self.verbosity_level
        details.logger_debug_level = self.debug_level
        details.logger_quiet = self.quiet
        details.logger_topics = self.topics

        details.shift = details.shift + self._base_shift

        if not message:
            message = indent(
                details.key,
                value=details.value,
                # Always apply colors - message can be decolorized later.
                color=details.color,
                level=details.shift,
                labels=self.labels,
                labels_padding=self.labels_padding)

        self._logger._log(level, message, (), extra={'details': details})

    def print(
            self,
            text: str,
            color: Optional[str] = None,
            shift: int = 0,
            ) -> None:

        message = indent(
            text,
            # Always apply colors - message can be decolorized later.
            color=color,
            level=shift + self._base_shift,
            labels=self.labels,
            labels_padding=self.labels_padding)

        message = self._decolorize_output(message)

        print(message)

    def info(
            self,
            key: str,
            value: Optional[LoggableValue] = None,
            color: Optional[str] = None,
            shift: int = 0
            ) -> None:
        self._log(
            logging.INFO,
            LogRecordDetails(
                key=key,
                value=value,
                color=color,
                shift=shift)
            )

    def verbose(
            self,
            key: str,
            value: Optional[LoggableValue] = None,
            color: Optional[str] = None,
            shift: int = 0,
            level: int = 1,
            topic: Optional[Topic] = None
            ) -> None:
        self._log(
            logging.INFO,
            LogRecordDetails(
                key=key,
                value=value,
                color=color,
                shift=shift,
                message_verbosity_level=level,
                message_topic=topic)
            )

    def debug(
            self,
            key: str,
            value: Optional[LoggableValue] = None,
            color: Optional[str] = None,
            shift: int = 0,
            level: int = 1,
            topic: Optional[Topic] = None
            ) -> None:
        self._log(
            logging.DEBUG,
            LogRecordDetails(
                key=key,
                value=value,
                color=color,
                shift=shift,
                message_debug_level=level,
                message_topic=topic)
            )

    def warn(
            self,
            message: str,
            shift: int = 0
            ) -> None:
        self._log(
            logging.WARN,
            LogRecordDetails(
                key='warn',
                value=message,
                color='yellow',
                shift=shift)
            )

    def fail(
            self,
            message: str,
            shift: int = 0
            ) -> None:
        self._log(
            logging.ERROR,
            LogRecordDetails(
                key='fail',
                value=message,
                color='red',
                shift=shift)
            )

    _bootstrap_logger: Optional['Logger'] = None

    @classmethod
    def get_bootstrap_logger(cls) -> 'Logger':
        """
        Create a logger designed for tmt startup time.

        .. warning::

            This logger has a **very** limited use case span, i.e.
            before tmt can digest its command-line options and create a
            proper logger. This happens inside :py:func:`tmt.cli.main`
            function, but there are some actions taken by tmt code
            before this function is called by Click, actions that need
            to emit logging messages. Using it anywhere outside of this
            brief time in tmt's runtime should be ruled out.
        """

        if cls._bootstrap_logger is None:
            # Stay away of our future main logger
            actual_logger = Logger._normalize_logger(logging.getLogger('_tmt_bootstrap'))

            cls._bootstrap_logger = Logger.create(actual_logger=actual_logger)
            cls._bootstrap_logger.add_console_handler()

        return cls._bootstrap_logger
