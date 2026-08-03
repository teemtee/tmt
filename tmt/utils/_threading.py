"""
Threading and synchronization helpers.
"""

import threading
from typing import Generic, TypeVar

T = TypeVar('T')
LockT = TypeVar('LockT', threading.Lock, threading.RLock)


class _Lock(Generic[LockT, T]):
    __lock: LockT
    __value: T

    def __init__(self, lock: LockT, value: T) -> None:
        self.__lock = lock
        self.__value = value

    def __enter__(self) -> T:
        self.__lock.acquire()

        return self.__value

    def __exit__(self, *args: object) -> None:
        self.__lock.release()


class Lock(_Lock[threading.Lock, T]):
    """
    A lock protecting its payload from unsynchronized access.

    In functionality it is similar to :py:class:`threading.Lock`, but
    bundles together the protected value and lock protecting it.
    To get the value, code is forced to acquire the lock:

    .. code-block:: python

        # A list, representing data shared between multiple threads,
        # is not assigned to any global name. Instead, it is wrapped by
        # the lock, and "borrowed" to caller using the context manager
        # approach:
        SHARED_DATA: Lock[list[str]] = Lock([])

        ...

        # `data` below is the list given to `Lock()` above:
        with SHARED_DATA as data:
            data += [...]

    Compared to :py:class:`RLock`, ``Lock`` is not reentrant, i.e. it
    can be acquired by the same thread only once, another attempt to
    acquire the lock while already holding it will end up with a
    deadlock. See :py:class:`threading.RLock` for more details on its
    reentrancy.
    """

    def __init__(self, value: T) -> None:
        super().__init__(threading.Lock(), value)


class RLock(_Lock[threading.RLock, T]):
    """
    A reentrant variant of :py:class:`Lock`.

    In functionality it is similar to :py:class:`threading.RLock`, but
    bundles together the protected value and lock protecting it.
    To get the value, code is forced to acquire the lock:

    .. code-block:: python

        # A list, representing data shared between multiple threads,
        # is not assigned to any global name. Instead, it is wrapped by
        # the lock, and "borrowed" to caller using the context manager
        # approach:
        SHARED_DATA: Lock[list[str]] = RLock([])

        ...

        # `data` below is the list given to `Lock()` above:
        with SHARED_DATA as data:
            data += [...]

    Compared to :py:class:`Lock`, ``RLock`` is reentrant, i.e. it can
    be reacquired by the same thread. See :py:class:`threading.RLock`
    for more details on its reentrancy.
    """

    def __init__(self, value: T) -> None:
        super().__init__(threading.RLock(), value)
