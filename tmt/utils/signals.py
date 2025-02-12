"""
Signal handling in tmt.

Provides custom signal handler for ``SIGINT`` (aka ``Ctrl+C``) and
``SIGTERM``, and delayed actions for these signals.

Some of the factors tmt need to take into account when dealing with
signals:

* tmt runs a lot of things in dedicated threads,
* sometimes tmt cannot let signals interrupt whatever is being done at
  the moment, namely saving API responses from provisioning services,
* signals in Python are always executed in the context of the main
  thread,
* signals are most often delivered to the main thread because that is
  what ``Ctrl+C`` will deliver to,
* masking signals in a thread will not affect other threads.

To support uninterruptible blocks, signal handler and
:py:class:`PreventSignals` use events to record whether a signal was
delivered and needs handling:

* if signals are not blocked, signal handler would raise the
  :py:exc:`KeyboardInterrupt` exception right away,
* if signals are blocked, signal handler would record its delivery, and
  :py:class:`PreventSignals` would raise the :py:exc:`KeyboardInterrupt`
  when leaving the uninterruptible block.
"""

import contextlib
import signal
import threading
from types import FrameType
from typing import Optional

import tmt.log

#: All changes to :py:data:`_INTERRUPT_MASKED` and
#: :py:data:`_INTERRUPT_PENDING` must be performed while holding this
#: lock. It prevents inconsistencies between handlers and
#: uninterruptible blocks.
_INTERRUPT_LOCK = threading.Lock()

#: When set, it is not allowed to interrupt what tmt is doing.
_INTERRUPT_MASKED = threading.Event()

#: When set, interrupt was delivered to tmt, and tmt should react to it.
_INTERRUPT_PENDING = threading.Event()


def _interrupt_handler(signum: int, frame: Optional[FrameType]) -> None:
    """
    A signal handler for signals that interrupt tmt, ``SIGINT`` and ``SIGTERM`.

    :param signum: delivered signal.
    :param frame: stack frame active when the signal was received.
    """

    logger = tmt.log.Logger.get_bootstrap_logger()

    logger.warning(f'Interrupt detected via {signal.Signals(signum).name} signal.')

    with _INTERRUPT_LOCK:
        if _INTERRUPT_MASKED.is_set():
            logger.warning('Interrupt is masked, postponing the reaction.')

            _INTERRUPT_PENDING.set()

            return

        logger.warning('Interrupting tmt operation as requested.')

        raise KeyboardInterrupt


def install_handlers() -> None:
    """Install tmt's signal handlers"""

    signal.signal(signal.SIGINT, _interrupt_handler)
    signal.signal(signal.SIGTERM, _interrupt_handler)


class PreventSignals(contextlib.AbstractContextManager['PreventSignals']):
    """
    For the duration of this context manager, interrupt signals are postponed.

    If, while the context was active, signals were delivered,
    :py:exc:`KeyboardInterrupt` exception would be raised when leaving
    the context.
    """

    logger: tmt.log.Logger

    def __init__(self, logger: tmt.log.Logger) -> None:
        self.logger = logger

    def __enter__(self) -> 'PreventSignals':
        with _INTERRUPT_LOCK:
            _INTERRUPT_MASKED.set()

        return self

    def __exit__(self, *args: object) -> None:
        with _INTERRUPT_LOCK:
            _INTERRUPT_MASKED.clear()

            if not _INTERRUPT_PENDING.is_set():
                self.logger.debug('Interrupt not detected, leaving safe block.')

                return

            _INTERRUPT_PENDING.clear()

            self.logger.warning('Interrupting tmt operation as requested')

            raise KeyboardInterrupt
