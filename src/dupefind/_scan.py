"""Walk a directory tree read-only and group regular files by byte size."""

from __future__ import annotations

import os
from collections import defaultdict
from collections.abc import Iterator
from pathlib import Path


def group_by_size(root: Path, *, follow_symlinks: bool) -> dict[int, list[Path]]:
    """Group every regular file under ``root`` by its size in bytes."""
    groups: dict[int, list[Path]] = defaultdict(list)
    for path in _iter_files(root, follow_symlinks=follow_symlinks):
        try:
            size = path.stat().st_size
        except OSError:
            continue
        groups[size].append(path)
    return groups


def _iter_files(root: Path, *, follow_symlinks: bool) -> Iterator[Path]:
    # When following symlinks, remember resolved directories so cycles cannot loop.
    seen: set[str] = set()
    stack = [root]
    while stack:
        current = stack.pop()
        if follow_symlinks and not _first_visit(current, seen):
            continue
        try:
            entries = list(os.scandir(current))
        except OSError:
            continue
        for entry in entries:
            if entry.is_symlink() and not follow_symlinks:
                continue
            try:
                if entry.is_dir(follow_symlinks=follow_symlinks):
                    stack.append(Path(entry.path))
                elif entry.is_file(follow_symlinks=follow_symlinks):
                    yield Path(entry.path)
            except OSError:
                continue


def _first_visit(path: Path, seen: set[str]) -> bool:
    """Return True the first time a resolved directory is seen, False after."""
    resolved = str(path.resolve())
    if resolved in seen:
        return False
    seen.add(resolved)
    return True
