import cProfile
import datetime
import functools
import io
import pstats
import time
from collections.abc import Iterator
from typing import Callable, Optional, TypeVar

# Using bootstrap logger on purpose: a profiler can be invoked while
# functions, classes and methods are still being defined and imported,
# and the proper logger may not be available yet.
from tmt._bootstrap import _BOOTSTRAP_LOGGER
from tmt._compat.typing import ParamSpec
from tmt.container import container

T = TypeVar('T')
P = ParamSpec('P')


#: How the profiler report should be sorted. See :py:mod:`pstats` for
#: more details.
DEFAULT_STAT_SORTING: tuple[str, ...] = ('cumulative', 'time')

#: How many items should the profiler report include.
DEFAULT_STAT_LIMIT: int = 100


@container
class Profiler:
    """
    Bundles together various parameters and helpers for profiling a code.
    """

    start_time: Optional[float] = None
    stop_time: Optional[float] = None

    _profiler: Optional[cProfile.Profile] = None

    @property
    def elapsed_time(self) -> Optional[datetime.timedelta]:
        """
        Return time elapsed between start and stop events.

        :returns: elapsed time between calls of :py:meth:`start` and
            :py:meth:`stop`, or ``None`` if either one of them did not
            happen yet.
        """

        if self.start_time is None or self.stop_time is None:
            return None

        return datetime.timedelta(seconds=self.stop_time - self.start_time)

    def start(self) -> None:
        """
        Begin profiling.
        """

        self.start_time = time.time()

        self._profiler = cProfile.Profile()

        self._profiler.enable()

    def stop(self) -> None:
        """
        Terminate profiling.
        """

        if self._profiler:
            self._profiler.disable()

        self.stop_time = time.time()

    def format(
        self,
        sort_stats: tuple[str, ...] = DEFAULT_STAT_SORTING,
        limit: int = DEFAULT_STAT_LIMIT,
    ) -> Iterator[str]:
        """
        Format captured profiling data report.

        :param sort_stats: arguments describing how statistics should be
            sorted. All are passed to for
            :py:meth:`pstats.Stats.sort_stats`.
        :param limit: how many entries should be reported in the summary.
        :yields: lines of the nicely formatted profiling report.
        """

        if self.elapsed_time is not None:
            yield f'Elapsed time: {self.elapsed_time.total_seconds():3}'

        if self._profiler is not None:
            s = io.StringIO()

            ps = pstats.Stats(self._profiler, stream=s).sort_stats(*sort_stats)
            ps.print_stats(limit)

            yield ''
            yield from s.getvalue().splitlines()
            yield ''

    @classmethod
    def profile(
        cls,
        sort_stats: tuple[str, ...] = DEFAULT_STAT_SORTING,
        limit: int = DEFAULT_STAT_LIMIT,
    ) -> Callable[[Callable[P, T]], Callable[P, T]]:
        """
        A decorator to profile a function or method.

        A decorated piece of code will be measured and profiled, and
        a report will be logged when the code finishes.

        .. code-block:: python

            @Profiler.profile()
            def foo():
                # do something expensive...
        """

        def _profile(fn: Callable[P, T]) -> Callable[P, T]:
            @functools.wraps(fn)
            def __profile(*args: P.args, **kwargs: P.kwargs) -> T:
                profiler = cls()

                try:
                    profiler.start()

                    return fn(*args, **kwargs)

                finally:
                    profiler.stop()

                    _BOOTSTRAP_LOGGER.info(
                        f"# Profiler report on '{fn.__name__}'",
                        '\n'.join(profiler.format(sort_stats=sort_stats, limit=limit)),
                    )

            return __profile

        return _profile
