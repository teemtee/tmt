"""
Common data structures shared between sprint scripts.
"""

import dataclasses
from typing import Optional


@dataclasses.dataclass
class Item:
    """
    A sprint item (issue or pull request).
    """

    id: int
    type: str
    repo: str
    status: str
    size: Optional[int]
    url: str
    title: str

    def __str__(self) -> str:
        size_str = f"[{self.size}]" if self.size is not None else "[-]"
        identifier = f"{self.repo}#{self.id}"
        return f"{identifier:<10} {size_str:>4}  {self.title}"
