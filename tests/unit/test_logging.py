import logging
from typing import Optional

import _pytest.capture
import _pytest.logging
import pytest

import tmt.utils
from tmt.log import (
    DebugLevelFilter,
    Logger,
    LogRecordDetails,
    QuietnessFilter,
    Topic,
    TopicFilter,
    VerbosityLevelFilter,
    indent,
    render_labels,
    )

from . import assert_log, assert_not_log


def _exercise_logger(
        caplog: _pytest.logging.LogCaptureFixture,
        capsys: _pytest.capture.CaptureFixture[str],
        logger: Logger,
        indent_by: str = '',
        labels: Optional[list[str]] = None,
        reset: bool = True) -> None:
    labels = labels or []

    prefix = tmt.utils.remove_color(render_labels(labels)) + indent_by + ' ' \
        if labels else indent_by

    if reset:
        caplog.clear()

    logger.print('this is printed')
    logger.debug('this is a debug message')
    logger.verbose('this is a verbose message')
    logger.info('this is just an info')
    logger.warning('this is a warning')
    logger.fail('this is a failure')

    captured = capsys.readouterr()

    assert_not_log(
        caplog,
        message=f'{prefix}this is printed',
        details_key='this is printed',
        details_logger_labels=labels,
        levelno=logging.INFO)
    assert tmt.utils.remove_color(captured.out) == f'{prefix}this is printed\n'
    assert_log(
        caplog,
        message=f'{prefix}this is a debug message',
        details_key='this is a debug message',
        details_logger_labels=labels,
        levelno=logging.DEBUG)
    assert_log(
        caplog,
        message=f'{prefix}this is a verbose message',
        details_key='this is a verbose message',
        details_logger_labels=labels,
        levelno=logging.INFO)
    assert_log(
        caplog,
        message=f'{prefix}this is just an info',
        details_key='this is just an info',
        details_logger_labels=labels,
        levelno=logging.INFO)
    assert_log(
        caplog,
        message=f'{prefix}warn: this is a warning',
        details_key='warn',
        details_value='this is a warning',
        details_logger_labels=labels,
        levelno=logging.WARNING)
    assert_log(
        caplog,
        message=f'{prefix}fail: this is a failure',
        details_key='fail',
        details_value='this is a failure',
        details_logger_labels=labels,
        levelno=logging.ERROR)


def test_sanity(
        caplog: _pytest.logging.LogCaptureFixture,
        capsys: _pytest.capture.CaptureFixture[str],
        root_logger: Logger) -> None:
    _exercise_logger(caplog, capsys, root_logger)


def test_creation(caplog: _pytest.logging.LogCaptureFixture, root_logger: Logger) -> None:
    logger = Logger.create()
    assert logger._logger.name == 'tmt'

    actual_logger = logging.Logger('3rd-party-app-logger')  # noqa: LOG001
    logger = Logger.create(actual_logger)
    assert logger._logger is actual_logger


def test_descend(
        caplog: _pytest.logging.LogCaptureFixture,
        capsys: _pytest.capture.CaptureFixture[str],
        root_logger: Logger) -> None:
    deeper_logger = root_logger.descend().descend().descend()

    _exercise_logger(caplog, capsys, deeper_logger, indent_by='            ')


@pytest.mark.parametrize(
    ('logger_verbosity', 'message_verbosity', 'filter_outcome'),
    [
        # (
        #   logger verbosity - corresponds to -v, -vv, -vvv CLI options,
        #   message verbosity - `level` parameter of `verbosity(...)` call,
        #   expected outcome of `VerbosityLevelFilter.filter()` - returns integer!
        # )
        (0, 1, 0),
        (1, 1, 1),
        (2, 1, 1),
        (3, 1, 1),
        (4, 1, 1),
        (0, 2, 0),
        (1, 2, 0),
        (2, 2, 1),
        (3, 2, 1),
        (4, 2, 1),
        (0, 3, 0),
        (1, 3, 0),
        (2, 3, 0),
        (3, 3, 1),
        (4, 3, 1),
        (0, 4, 0),
        (1, 4, 0),
        (2, 4, 0),
        (3, 4, 0),
        (4, 4, 1)
        ]
    )
def test_verbosity_filter(
        logger_verbosity: int,
        message_verbosity: int,
        filter_outcome: int
        ) -> None:
    filter = VerbosityLevelFilter()

    assert filter.filter(logging.makeLogRecord({
        'levelno': logging.INFO,
        'details': LogRecordDetails(
            key='dummy key',
            logger_verbosity_level=logger_verbosity,
            message_verbosity_level=message_verbosity)
        })) == filter_outcome


@pytest.mark.parametrize(
    ('logger_debug', 'message_debug', 'filter_outcome'),
    [
        # (
        #   logger debug level - corresponds to -d, -dd, -ddd CLI options,
        #   message debug level - `level` parameter of `debug(...)` call,
        #   expected outcome of `DebugLevelFilter.filter()` - returns integer!
        # )
        (0, 1, 0),
        (1, 1, 1),
        (2, 1, 1),
        (3, 1, 1),
        (4, 1, 1),
        (0, 2, 0),
        (1, 2, 0),
        (2, 2, 1),
        (3, 2, 1),
        (4, 2, 1),
        (0, 3, 0),
        (1, 3, 0),
        (2, 3, 0),
        (3, 3, 1),
        (4, 3, 1),
        (0, 4, 0),
        (1, 4, 0),
        (2, 4, 0),
        (3, 4, 0),
        (4, 4, 1)
        ]
    )
def test_debug_filter(
        logger_debug: int,
        message_debug: int,
        filter_outcome: int
        ) -> None:
    filter = DebugLevelFilter()

    assert filter.filter(logging.makeLogRecord({
        'levelno': logging.DEBUG,
        'details': LogRecordDetails(
            key='dummy key',
            logger_debug_level=logger_debug,
            message_debug_level=message_debug)
        })) == filter_outcome


@pytest.mark.parametrize(
    ('levelno', 'filter_outcome'),
    [
        # (
        #   log message level,
        #   expected outcome of `QietnessFilter.filter()` - returns integer!
        # )
        (logging.DEBUG, 0),
        (logging.INFO, 0),
        (logging.WARNING, 0),
        (logging.ERROR, 1),
        (logging.CRITICAL, 1)
        ]
    )
def test_quietness_filter(levelno: int, filter_outcome: int) -> None:
    filter = QuietnessFilter()

    assert filter.filter(logging.makeLogRecord({
        'levelno': levelno
        })) == filter_outcome


def test_labels(
        caplog: _pytest.logging.LogCaptureFixture,
        capsys: _pytest.capture.CaptureFixture[str],
        root_logger: Logger) -> None:
    _exercise_logger(caplog, capsys, root_logger, labels=[])

    root_logger.labels += ['foo']

    _exercise_logger(caplog, capsys, root_logger, labels=['foo'])

    root_logger.labels += ['bar']

    _exercise_logger(caplog, capsys, root_logger, labels=['foo', 'bar'])


def test_bootstrap_logger(
        caplog: _pytest.logging.LogCaptureFixture,
        capsys: _pytest.capture.CaptureFixture[str]) -> None:
    _exercise_logger(caplog, capsys, Logger.get_bootstrap_logger())


# Helpers for the test below, to make strings slightly shorter: Rendered Labels...
RL = render_labels(["foo", "bar"])
# ... and Rendered Labels with Padding.
RLP = render_labels(["foo", "bar"]) + '   '


@pytest.mark.parametrize(
    ('key', 'value', 'color', 'level', 'labels', 'labels_padding', 'expected'),
    [
        ('dummy-key', None, None, 0, None, 0, 'dummy-key'),
        ('dummy-key', 'dummy-value', None, 0, None, 0, 'dummy-key: dummy-value'),
        (
            'dummy-key',
            'dummy\nmultiline\nvalue',
            None,
            0,
            None,
            0,
            'dummy-key:\n    dummy\n    multiline\n    value'),

        ('dummy-key', None, None, 2, None, 0, '        dummy-key'),
        ('dummy-key', 'dummy-value', None, 2, None, 0, '        dummy-key: dummy-value'),
        (
            'dummy-key',
            'dummy\nmultiline\nvalue',
            None,
            2,
            None,
            0,
            '        dummy-key:\n'
            '            dummy\n'
            '            multiline\n'
            '            value'),
        (
            'dummy-key',
            'dummy\nmultiline\nvalue',
            None,
            2,
            ['foo', 'bar'],
            0,
            f'{RL}         dummy-key:\n'
            f'{RL}             dummy\n'
            f'{RL}             multiline\n'
            f'{RL}             value'),
        (
            'dummy-key',
            'dummy\nmultiline\nvalue',
            None,
            2,
            ['foo', 'bar'],
            # Pad labels to occupy their actual length plus 3 more characters
            len(RL) + 3,
            f'{RLP}         dummy-key:\n'
            f'{RLP}             dummy\n'
            f'{RLP}             multiline\n'
            f'{RLP}             value')
        ], ids=[
        'key only',
        'key and value',
        'key and multiline value',
        'key only, indented',
        'key and value, indented',
        'key and multiline value, indented',
        'key and multiline value, indented, with labels',
        'key and multiline value, indented, with labels, padded',
        ]
    )
def test_indent(key, value, color, level, labels, labels_padding, expected):
    assert indent(
        key,
        value=value,
        color=color,
        level=level,
        labels=labels,
        labels_padding=labels_padding) == expected


@pytest.mark.parametrize(
    ('logger_topics', 'message_topic', 'filter_outcome'),
    [
        # (
        #     logger topics,
        #     message topic,
        #   expected outcome of `QietnessFilter.filter()`
        # )
        (
            set(),
            None,
            True
            ),
        (
            set(),
            Topic.KEY_NORMALIZATION,
            False
            ),
        (
            {Topic.KEY_NORMALIZATION},
            Topic.KEY_NORMALIZATION,
            True
            ),
        (
            {Topic.KEY_NORMALIZATION},
            None,
            True
            ),
        ],
    ids=(
        'no logger topics, no message topic',
        'no logger topics, message has topic',
        'message for enabled topic',
        'logger topic, no message topic'
        # TODO: enable once we have more than one topic
        # 'message for disabled topic'
        )
    )
def test_topic_filter(
        logger_topics: set[Topic],
        message_topic: Optional[Topic],
        filter_outcome: bool) -> None:
    filter = TopicFilter()

    assert filter.filter(logging.makeLogRecord({
        'levelno': logging.INFO,
        'details': LogRecordDetails(
            key='dummy key',
            logger_topics=logger_topics,
            message_topic=message_topic)
        })) == filter_outcome
