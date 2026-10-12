"""Scan options, validated once at construction."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ScanOptions:
    """How to walk and compare. Every field has a safe default.

    algorithm:
        Name of a fixed-size ``hashlib`` algorithm (``sha256``, ``blake2b``,
        ``sha1``, ``md5`` and so on). The default keeps the keys of ``0.1.0``.
    partial_size:
        Bytes hashed from the start of each same-size file before any full read.
        A file no larger than this is read exactly once.
    min_size, max_size:
        Inclusive byte bounds; files outside them are ignored. ``None`` means no
        upper bound.
    include_empty:
        Whether zero-length files are compared at all. When true, all empty files
        form one group, which is rarely what a clean-up wants; set it to false or
        ``min_size=1`` to leave them alone.
    include, exclude:
        Glob patterns. A pattern without ``/`` matches the base name; one with ``/``
        matches the path relative to its root, written with ``/``. Matching follows
        the platform case rules (case-insensitive on Windows). ``exclude`` also
        prunes directories. When ``include`` is not empty, only matching files are
        compared.
    follow_symlinks:
        Walk into symlinked directories and Windows junctions and compare symlinked
        files. Off by default. Loops are detected and walked once.
    hardlinks:
        Report several names of one file (hard links) as duplicates of each other.
        Off by default: such names are merged into one ``DuplicateFile`` and listed
        in its ``aliases``.
    """

    algorithm: str = "sha256"
    partial_size: int = 4096
    min_size: int = 0
    max_size: int | None = None
    include_empty: bool = True
    include: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    follow_symlinks: bool = False
    hardlinks: bool = False

    def __post_init__(self) -> None:
        check_algorithm(self.algorithm)
        if self.partial_size < 1:
            raise ValueError(f"partial_size must be at least 1, got {self.partial_size}")
        if self.min_size < 0:
            raise ValueError(f"min_size must not be negative, got {self.min_size}")
        if self.max_size is not None and self.max_size < self.min_size:
            raise ValueError(f"max_size {self.max_size} is below min_size {self.min_size}")
        for name in ("include", "exclude"):
            value = getattr(self, name)
            if isinstance(value, str):
                raise TypeError(f"{name} must be a sequence of patterns, not a string")
            object.__setattr__(self, name, tuple(value))

    def accepts_size(self, size: int) -> bool:
        """Return True when a file of ``size`` bytes should be compared."""
        if size == 0 and not self.include_empty:
            return False
        if size < self.min_size:
            return False
        return self.max_size is None or size <= self.max_size


def check_algorithm(name: str) -> None:
    """Raise ``ValueError`` unless ``name`` is a fixed-size ``hashlib`` algorithm."""
    try:
        hasher = hashlib.new(name)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"unknown hash algorithm: {name!r}") from exc
    if hasher.digest_size == 0 or name.lower().startswith("shake"):
        raise ValueError(f"hash algorithm {name!r} has no fixed digest size")
