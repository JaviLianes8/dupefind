"""Staged duplicate detection: size, then a partial hash, then a full hash."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterator
from pathlib import Path

from ._hash import full_digest, partial_digest
from ._scan import group_by_size


def iter_duplicates(
    root: str | Path, *, follow_symlinks: bool = False
) -> Iterator[tuple[str, list[Path]]]:
    """Yield ``(full hash, paths)`` for every set of two or more identical files.

    Files are read but never modified. The search is staged for speed: files are
    grouped by size, only same-size files have their first block hashed, and only
    files that share that partial hash are read in full. Symlinks are skipped
    unless ``follow_symlinks`` is true.
    """
    base = Path(root)
    for same_size in group_by_size(base, follow_symlinks=follow_symlinks).values():
        if len(same_size) < 2:
            continue
        for same_prefix in _regroup(same_size, partial_digest).values():
            if len(same_prefix) < 2:
                continue
            for digest, paths in _regroup(same_prefix, full_digest).items():
                if len(paths) >= 2:
                    yield digest, paths


def find_duplicates(root: str | Path, *, follow_symlinks: bool = False) -> dict[str, list[Path]]:
    """Return duplicate files under ``root`` grouped by their final full hash.

    Each value holds two or more paths with identical content. Files that have no
    duplicate are left out. Nothing on disk is modified. See ``iter_duplicates``
    for the streaming variant and the staging it uses.
    """
    return dict(iter_duplicates(root, follow_symlinks=follow_symlinks))


def _regroup(paths: list[Path], key: Callable[[Path], str]) -> dict[str, list[Path]]:
    """Regroup paths by a digest, dropping any that cannot be read."""
    groups: dict[str, list[Path]] = defaultdict(list)
    for path in paths:
        try:
            groups[key(path)].append(path)
        except OSError:
            continue
    return groups
