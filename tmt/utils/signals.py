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
import textwrap
import threading
from types import FrameType
from typing import Any, NoReturn, Optional

import tmt.log
import tmt.utils

#: All changes to :py:data:`_INTERRUPT_MASKED` and
#: :py:data:`_INTERRUPT_PENDING` must be performed while holding this
#: lock. It prevents inconsistencies between handlers and
#: uninterruptible blocks.
_INTERRUPT_LOCK = threading.Lock()

#: When set, it is not allowed to interrupt what tmt is doing.
_INTERRUPT_MASKED = threading.Event()

#: When set, interrupt was delivered to tmt, and tmt should react to it.
INTERRUPT_PENDING = threading.Event()


class Interrupted(tmt.utils.GeneralError):
    """
    Raised by code that interrupted its work because of tmt shutdown.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__('tmt was interrupted', *args, **kwargs)


def _quit_tmt(logger: tmt.log.Logger, repeated: bool = False) -> NoReturn:
    """
    Send tmt on the path of quitting by raising an exception.
    """

    if repeated:
        logger.warning(
            textwrap.dedent(
                """
                Repeated interruption requested.

                tmt will now cancel its work in progress and quit as soon as
                possible. Wait for it to finish, please.
                """
            ).strip()
        )

    else:
        logger.warning(
            textwrap.dedent(
                """
                Interrupting tmt operation as requested.

                tmt will now cancel its work in progress and quit as soon as
                possible. Wait for it to finish, please.

                Interrupt tmt again for faster termination but be aware that
                it may result in resource leaks as various cleanup tasks will
                not finish.
                """
            ).strip()
        )

    raise KeyboardInterrupt


def _interrupt_handler(signum: int, frame: Optional[FrameType]) -> None:
    """
    A signal handler for signals that interrupt tmt, ``SIGINT`` and ``SIGTERM`.

    :param signum: delivered signal.
    :param frame: stack frame active when the signal was received.
    """

    logger = tmt.log.Logger.get_bootstrap_logger()

    logger.warning(f'Interrupt requested via {signal.Signals(signum).name} signal.')

    with _INTERRUPT_LOCK:
        repeated = INTERRUPT_PENDING.is_set()

        INTERRUPT_PENDING.set()

        if _INTERRUPT_MASKED.is_set():
            logger.warning('Interrupt is masked, postponing the reaction.')

            return

        _quit_tmt(logger, repeated=repeated)


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

            if not INTERRUPT_PENDING.is_set():
                self.logger.debug('Interrupt not detected, leaving safe block.', level=2)

                return

            _quit_tmt(self.logger)
