from collections.abc import Iterable
from typing import (
    Any,
    NoReturn,
    Optional,
    SupportsIndex,
    Union,
)

from tmt._compat.pathlib import Path
from tmt._compat.typing import Self


class Secret(str):
    def __new__(cls, raw_value: Union[str, Path]) -> Self:
        if isinstance(raw_value, Secret):
            raise ValueError("Secrets cannot be turned into secrets.")

        if isinstance(raw_value, str):
            return str.__new__(cls, raw_value)

        if isinstance(raw_value, Path):  # type: ignore[reportUnnecessaryIsInstance,unused-ignore]
            return str.__new__(cls, str(raw_value))

        raise ValueError(
            f"Only strings and paths can be environment variables, '{type(raw_value)}' found."
        )

    @property
    def dangerous_as_open(self) -> str:
        return str.__str__(self)

    def __add__(self, other: Any) -> Self:
        return self.__class__(str.__add__(self.dangerous_as_open, str(other)))

    def __contains__(self, other: Any) -> NoReturn:
        raise ValueError('Cannot test secret variable for substring presence.')

    def __format__(self, other: Any) -> NoReturn:
        raise ValueError('Cannot format secret variable.')

    def __getitem__(self, key: Any) -> NoReturn:
        raise ValueError('Cannot access characters in secret variable.')

    def __iter__(self) -> NoReturn:
        raise ValueError('Cannot iterate over characters in secret variable.')

    def __len__(self) -> NoReturn:
        raise ValueError('Cannot get length of secret variable.')

    def __mod__(self, other: Any) -> Self:
        return self.__class__(str.__mod__(self.dangerous_as_open, other))

    def __mul__(self, other: SupportsIndex) -> Self:
        return self.__class__(str.__mul__(self.dangerous_as_open, other))

    def __radd__(self, other: Any) -> Self:
        return self.__class__(str.__add__(str(other), self.dangerous_as_open))

    def __repr__(self) -> str:
        return 'SecretEnvVarValue("*******")'

    def __str__(self) -> str:
        return '*******'

    def capitalize(self) -> Self:
        return self.__class__(str.capitalize(self.dangerous_as_open))

    def casefold(self) -> Self:
        return self.__class__(str.casefold(self.dangerous_as_open))

    def center(self, width: SupportsIndex, fillchar: str = ' ', /) -> Self:
        return self.__class__(str.center(self.dangerous_as_open, width, fillchar))

    def count(
        self, sub: str, start: Optional[SupportsIndex] = None, end: Optional[SupportsIndex] = None
    ) -> NoReturn:
        raise ValueError('Cannot count substrings in secret variable.')

    def encode(self, encoding: str = 'utf-8', errors: str = 'strict') -> NoReturn:
        raise ValueError('Cannot encode secret variable.')

    def endswith(
        self,
        suffix: Union[str, tuple[str, ...]],
        start: Optional[SupportsIndex] = None,
        end: Optional[SupportsIndex] = None,
    ) -> NoReturn:
        raise ValueError('Cannot test substrings in secret variable.')

    def expandtabs(self, tabsize: SupportsIndex = 8) -> Self:
        return self.__class__(str.expandtabs(self.dangerous_as_open, tabsize=tabsize))

    def find(
        self, sub: str, start: Optional[SupportsIndex] = None, end: Optional[SupportsIndex] = None
    ) -> NoReturn:
        raise ValueError('Cannot test substrings in secret variable.')

    def format(self, *args: Any, **kwargs: Any) -> Self:
        return self.__class__(str.format(self.dangerous_as_open, *args, **kwargs))

    def format_map(self, mapping: Any) -> Self:  # _FormatMapMapping
        return self.__class__(str.format_map(self.dangerous_as_open, mapping))

    def index(
        self, sub: str, start: Optional[SupportsIndex] = None, end: Optional[SupportsIndex] = None
    ) -> NoReturn:
        raise ValueError('Cannot test substrings in secret variable.')

    def join(self, other: Iterable[str]) -> Self:
        return self.__class__(str.join(self.dangerous_as_open, other))

    def ljust(self, width: SupportsIndex, fillchar: str = ' ', /) -> Self:
        return self.__class__(str.ljust(self.dangerous_as_open, width, fillchar))

    def lower(self) -> Self:
        return self.__class__(str.lower(self.dangerous_as_open))

    def lstrip(self, chars: Optional[str] = None, /) -> Self:
        return self.__class__(str.lstrip(self.dangerous_as_open, chars))

    def partition(self, sep: str) -> tuple[Self, Self, Self]:
        return tuple(self.__class__(s) for s in str.partition(self.dangerous_as_open, sep))  # type: ignore[return-value]

    def removeprefix(self, prefix: str) -> Self:
        return self.__class__(str.removeprefix(self.dangerous_as_open, prefix))

    def removesuffix(self, suffix: str) -> Self:
        return self.__class__(str.removesuffix(self.dangerous_as_open, suffix))

    def replace(self, old: str, new: str, /, count: SupportsIndex = -1) -> Self:
        return self.__class__(str.replace(self.dangerous_as_open, old, new, count))

    def rfind(
        self, sub: str, start: Optional[SupportsIndex] = None, end: Optional[SupportsIndex] = None
    ) -> NoReturn:
        raise ValueError('Cannot test substrings in secret variable.')

    def rindex(
        self, sub: str, start: Optional[SupportsIndex] = None, end: Optional[SupportsIndex] = None
    ) -> NoReturn:
        raise ValueError('Cannot test substrings in secret variable.')

    def rjust(self, width: SupportsIndex, fillchar: str = ' ', /) -> Self:
        return self.__class__(str.rjust(self.dangerous_as_open, width, fillchar))

    def rpartition(self, sep: str) -> tuple[Self, Self, Self]:
        return tuple(self.__class__(s) for s in str.partition(self.dangerous_as_open, sep))  # type: ignore[return-value]

    def rsplit(self, sep: Optional[str] = None, maxsplit: SupportsIndex = -1) -> list[Self]:  # type: ignore[override]
        return [self.__class__(s) for s in str.rsplit(self.dangerous_as_open, sep, maxsplit)]

    def rstrip(self, chars: Optional[str] = None) -> Self:
        return self.__class__(str.rstrip(self.dangerous_as_open, chars))

    def split(self, sep: Optional[str] = None, maxsplit: SupportsIndex = -1) -> list[Self]:  # type: ignore[override]
        return [self.__class__(s) for s in str.split(self.dangerous_as_open, sep, maxsplit)]

    def splitlines(self, keepends: bool = False) -> list[Self]:  # type: ignore[override]
        return [self.__class__(s) for s in str.splitlines(self.dangerous_as_open, keepends)]

    def startswith(
        self,
        suffix: Union[str, tuple[str, ...]],
        start: Optional[SupportsIndex] = None,
        end: Optional[SupportsIndex] = None,
    ) -> NoReturn:
        raise ValueError('Cannot test substrings in secret variable.')

    def strip(self, chars: Optional[str] = None) -> Self:
        return self.__class__(str.strip(self.dangerous_as_open, chars))

    def swapcase(self) -> Self:
        return self.__class__(str.swapcase(self.dangerous_as_open))

    def title(self) -> Self:
        return self.__class__(str.title(self.dangerous_as_open))

    def translate(self, table: Any) -> Self:  # _TranslateTable
        return self.__class__(str.translate(self.dangerous_as_open, table))

    def upper(self) -> Self:
        return self.__class__(str.upper(self.dangerous_as_open))

    def zfill(self, width: SupportsIndex) -> Self:
        return self.__class__(str.zfill(self.dangerous_as_open, width))
