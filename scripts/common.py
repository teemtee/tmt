"""
Common data structures shared between sprint scripts.
"""

import dataclasses


@dataclasses.dataclass
class Item:
    """
    A sprint item (issue or pull request).
    """

    id: int
    type: str
    repo: str
    status: str
    size: int | None
    url: str
    title: str

    @property
    def safe_size(self) -> int:
        return self.size or 0

    def __str__(self) -> str:
        size_str = f"[{self.size}]" if self.size is not None else "[-]"
        identifier = f"{self.repo}#{self.id}"
        return f"{identifier:<10} {size_str:>4}  {self.title}"
