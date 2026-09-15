"""
Date and time-related helpers.
"""


def sleep(delay: float) -> None:
    """
    Delay execution for a given number of seconds.

    An alternative to :py:func:`time.sleep`, this function is aware of
    tmt interrupt process, and can be safely used in threads. If tmt
    is interrupted before or while this function sleeps,
    :py:class:`tmt.utils.signals.Interrupted` is raised instead of
    returning.

    :param delay: how many seconds to sleep.
    :raises Interrupted: when tmt was interrupted.
    """

    from tmt.utils.signals import _INTERRUPT_PENDING, assert_not_interrupted

    # `wait()` will wait for the event to become set for the given delay,
    # at max. If the event has been set already, `wait()` returns immediately.
    # Which is nice: we get our delay, and if tmt gets interrupted, or it
    # got interrupted already, our sleep ends.
    _INTERRUPT_PENDING.wait(delay)

    assert_not_interrupted()
