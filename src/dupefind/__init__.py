"""Find duplicate files by staged hashing: group by size, then partial hash, then full hash."""

from __future__ import annotations

from ._find import find_duplicates, iter_duplicates

__version__ = "0.1.0"

__all__ = ["find_duplicates", "iter_duplicates"]
