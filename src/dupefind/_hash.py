"""Hash file contents read-only: a cheap prefix first, the whole file on demand."""

from __future__ import annotations

import hashlib
from pathlib import Path

_PREFIX = 4096
_CHUNK = 65536


def partial_digest(path: Path) -> str:
    """Hash the first block of a file, a cheap discriminator before a full read."""
    with path.open("rb") as handle:
        block = handle.read(_PREFIX)
    return hashlib.sha256(block).hexdigest()


def full_digest(path: Path) -> str:
    """Hash the entire file, read in fixed-size chunks."""
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_CHUNK), b""):
            hasher.update(chunk)
    return hasher.hexdigest()
