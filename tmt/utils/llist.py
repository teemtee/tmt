"""
Yet another linked list implementation.

Closest implementation is from ``llist`` or ``pyllist``, but those
are too old.
"""

from collections.abc import Iterable, Iterator
from typing import Generic, Optional, TypeVar

from tmt._compat.typing import Self

T = TypeVar("T")


class dllistNode(Generic[T]):  # ruff: ignore[invalid-class-name]
    __slots__ = ('__list', '__next', '__prev', 'value')

    __list: "dllist[T]"
    __next: Optional["dllistNode[T]"]
    __prev: Optional["dllistNode[T]"]
    value: T

    def __init__(
        self,
        value: T,
        _prev: Optional["dllistNode[T]"],
        _next: Optional["dllistNode[T]"],
        _list: "dllist[T]",
    ) -> None:
        self.__prev = _prev
        self.__next = _next
        self.value = value
        self.__list = _list

        if _prev is not None:
            _prev.__next = self
        if _next is not None:
            _next.__prev = self
        if _prev is None and _next is None:
            assert _list.size == 0
            assert _list.first is None
            assert _list.last is None
            _list._dllist__first = self  # type: ignore[attr-defined]
            _list._dllist__last = self  # type: ignore[attr-defined]
            _list._dllist__size = 1  # type: ignore[attr-defined]

    @property
    def prev(self) -> Optional["dllistNode[T]"]:
        return self.__prev

    @property
    def next(self) -> Optional["dllistNode[T]"]:
        return self.__next

    @property
    def list(self) -> "dllist[T]":
        return self.__list

    def appendleft(self, value: T) -> "dllistNode[T]":
        node = dllistNode(value, self.__prev, self, self.__list)
        self.__list._dllist__size += 1  # type: ignore[attr-defined]
        if node.prev is None:
            self.__list._dllist__first = node  # type: ignore[attr-defined]
        return node

    def appendright(self, value: T) -> "dllistNode[T]":
        node = dllistNode(value, self, self.__next, self.__list)
        self.__list._dllist__size += 1  # type: ignore[attr-defined]
        if node.next is None:
            self.__list._dllist__last = node  # type: ignore[attr-defined]
        return node

    def append(self, value: T) -> "dllistNode[T]":
        return self.appendright(value)

    def pop(self) -> T:
        if self.__prev:
            self.__prev.__next = self.__next
        else:
            self.__list._dllist__first = self.__next  # type: ignore[attr-defined]
        if self.__next:
            self.__next.__prev = self.__prev
        else:
            self.__list._dllist__last = self.__prev  # type: ignore[attr-defined]
        self.__list._dllist__size -= 1  # type: ignore[attr-defined]
        return self.value

    def _iter(self, reverse: bool = False) -> Iterator["dllistNode[T]"]:
        curr: Optional[dllistNode[T]] = self
        while curr is not None:
            yield curr
            curr = curr.__prev if reverse else curr.__next

    def iternext(self) -> Iterator["dllistNode[T]"]:
        yield from self._iter()

    def iterprev(self) -> Iterator["dllistNode[T]"]:
        yield from self._iter(reverse=True)

    def __lt__(self, other: "dllistNode[T]") -> bool:
        if other.list != self.__list:
            return False
        return any(check_node == self for check_node in other.iterprev())

    def __gt__(self, other: "dllistNode[T]") -> bool:
        if other.list != self.__list:
            return False
        return any(check_node == self for check_node in other.iternext())

    def __le__(self, other: "dllistNode[T]") -> bool:
        if self == other:
            return False
        return self < other

    def __ge__(self, other: "dllistNode[T]") -> bool:
        if self == other:
            return False
        return self > other


# TODO: Make this a MutableSequence? Needs to support sliced indexing
class dllist(Iterable[T], Generic[T]):  # ruff: ignore[invalid-class-name]
    __slots__ = ("__first", "__last", "__size")

    __first: Optional["dllistNode[T]"]
    __last: Optional["dllistNode[T]"]
    __size: int

    def __init__(self, sequence: Optional[Iterable[T]] = None) -> None:
        self.__first = None
        self.__last = None
        self.__size = 0

        if sequence is None:
            return

        for value in sequence:
            self.appendright(value)

    @property
    def first(self) -> Optional["dllistNode[T]"]:
        return self.__first

    @property
    def last(self) -> Optional["dllistNode[T]"]:
        return self.__last

    @property
    def size(self) -> int:
        return self.__size

    def __getitem__(self, index: int) -> T:
        return self.nodeat(index).value

    def __setitem__(self, index: int, value: T) -> dllistNode[T]:
        node = self.nodeat(index)
        node.value = value
        return node

    def __delitem__(self, index: int) -> None:
        self.nodeat(index).pop()

    def __len__(self) -> int:
        return self.__size

    def insert(self, index: int, value: T) -> dllistNode[T]:
        node = self.nodeat(index)
        return node.appendleft(value)

    def appendleft(self, value: T) -> dllistNode[T]:
        if self.__first:
            node = self.__first.appendleft(value)
        else:
            node = dllistNode(value, None, None, self)
        return node

    def appendright(self, value: T) -> dllistNode[T]:
        if self.__last:
            node = self.__last.appendright(value)
        else:
            node = dllistNode(value, None, None, self)
        return node

    def append(self, value: T) -> dllistNode[T]:
        return self.appendright(value)

    def popleft(self) -> T:
        if self.__first is None:
            raise ValueError("List is empty")
        return self.__first.pop()

    def popright(self) -> T:
        if self.__last is None:
            raise ValueError("List is empty")
        return self.__last.pop()

    def pop(self) -> T:
        return self.popright()

    def iternodes(self, reverse: bool = False) -> Iterator[dllistNode[T]]:
        curr = self.__last if reverse else self.__first
        if curr is not None:
            yield from curr._iter(reverse=reverse)

    def nodeat(self, index: int) -> dllistNode[T]:
        assert isinstance(index, int)

        if index < 0:
            index += self.__size
        if index < 0 or index >= self.__size:
            raise IndexError("index out of range")

        reverse = index > self.__size / 2
        for iter_index, node in enumerate(self.iternodes(reverse=reverse)):
            iter_index = self.__size - iter_index - 1 if reverse else iter_index
            if iter_index == index:
                return node
        raise AssertionError("Maths no maths")

    def __iter__(self) -> Iterator[T]:
        for node in self.iternodes():
            yield node.value

    def __reversed__(self) -> Iterator[T]:
        for node in self.iternodes(reverse=True):
            yield node.value

    def __add__(self, other: Iterable[T]) -> "dllist[T]":
        new_list = dllist(self)
        new_list += other
        return new_list

    def __iadd__(self, other: Iterable[T]) -> Self:
        for value in other:
            self.appendright(value)
        return self
