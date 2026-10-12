"""Hash file contents read-only: a cheap prefix first, the whole file on demand."""

from __future__ import annotations

import hashlib
from pathlib import Path

_CHUNK = 1 << 20


def _new(algorithm: str) -> hashlib._Hash:
    try:
        return hashlib.new(algorithm, usedforsecurity=False)
    except TypeError:  # pragma: no cover - builds without the keyword
        return hashlib.new(algorithm)


def hash_prefix(path: Path, algorithm: str, size: int) -> tuple[str, int]:
    """Hash the first ``size`` bytes of a file; return the hex digest and bytes read."""
    hasher = _new(algorithm)
    with path.open("rb") as handle:
        block = handle.read(size)
    hasher.update(block)
    return hasher.hexdigest(), len(block)


def hash_whole(path: Path, algorithm: str) -> tuple[str, int]:
    """Hash a whole file in fixed-size chunks; return the hex digest and bytes read."""
    hasher = _new(algorithm)
    total = 0
    with path.open("rb") as handle:
        while chunk := handle.read(_CHUNK):
            hasher.update(chunk)
            total += len(chunk)
    return hasher.hexdigest(), total


def same_content(first: Path, second: Path) -> bool:
    """Compare two files byte for byte, stopping at the first difference."""
    with first.open("rb") as one, second.open("rb") as two:
        while True:
            left = one.read(_CHUNK)
            right = two.read(_CHUNK)
            if left != right:
                return False
            if not left:
                return True
