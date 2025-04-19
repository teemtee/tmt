"""
Loggers for use during tmt startup.

Very special loggers used by tmt plugin discovery and configuration
loaders. Established logging is needed even by this type of code, and
loggers must be independent on other packages, therefore they cannot
be located in ``tmt.cli`` or ``tmt.utils`` - otherwise, we might need
them for reporting exceptions raised while importing said packages.

By moving these loggers into their own module, both bootstrap and error
reporting code can use them without deadlocking.
"""

import tmt.log

#: A logger to use before the proper one can be established.
#:
#: .. warning::
#:
#:    This logger should be used with utmost care for logging while tmt
#:    is still starting. Once properly configured logger is spawned,
#:    honoring relevant options, this logger should not be used anymore.
_BOOTSTRAP_LOGGER = tmt.log.Logger.get_bootstrap_logger()

#: A logger to use for exception logging.
#:
#: .. warning::
#:
#:    This logger should be used with utmost care for logging exceptions
#:    only, no other traffic should be allowed. On top of that, the
#:    exception logging is handled by a dedicated function,
#:    :py:func:`tmt.utils.show_exception` - if you find yourself in need
#:    of logging an exception somewhere in the code, and you think about
#:    using this logger or calling ``show_exception()`` explicitly,
#:    it is highly likely you are not on the right track.
EXCEPTION_LOGGER: tmt.log.Logger = _BOOTSTRAP_LOGGER
