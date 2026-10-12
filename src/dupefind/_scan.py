"""Walk the roots read-only and collect the regular files worth comparing."""

from __future__ import annotations

import os
import stat
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from fnmatch import fnmatch
from pathlib import Path

from ._options import ScanOptions
from ._types import IssueKind, Progress, ScanIssue

_MOUNT_POINT = 0xA0000003  # IO_REPARSE_TAG_MOUNT_POINT: a Windows junction or mounted volume


@dataclass(slots=True)
class Entry:
    """A regular file found by the walk, with the stat values the scan relies on."""

    path: Path
    size: int
    mtime_ns: int
    identity: tuple[int, int] | None = None
    aliases: list[Path] = field(default_factory=list)


class Walker:
    """Collect files from several roots, recording what could not be read."""

    def __init__(
        self,
        options: ScanOptions,
        issues: list[ScanIssue],
        on_progress: Callable[[Progress], None] | None = None,
    ) -> None:
        self.options = options
        self.issues = issues
        self.on_progress = on_progress
        self.entries: list[Entry] = []
        self._dirs: set[str] = set()

    def walk(self, roots: Iterable[str | os.PathLike[str]]) -> list[Entry]:
        """Walk every root in order and return the files found, each once."""
        for root in roots:
            self._walk_root(Path(root))
        return self.entries

    def issue(self, path: Path, exc: OSError) -> None:
        """Record an OS error against ``path``."""
        self.issues.append(ScanIssue(path, issue_kind(exc), str(exc)))

    def _walk_root(self, root: Path) -> None:
        # Paths given explicitly are followed even when they are links, like `find -H`.
        try:
            info = os.stat(root)
        except OSError as exc:
            self.issue(root, exc)
            return
        if stat.S_ISDIR(info.st_mode):
            self._walk_dir(root)
        elif stat.S_ISREG(info.st_mode):
            self._consider(root, root.name, info)

    def _walk_dir(self, root: Path) -> None:
        stack: list[tuple[Path, str]] = [(root, "")]
        while stack:
            current, rel = stack.pop()
            if not _first(self._dirs, current):
                continue
            try:
                with os.scandir(current) as it:
                    entries = sorted(it, key=lambda e: e.name)
            except OSError as exc:
                self.issue(current, exc)
                continue
            subdirs: list[tuple[Path, str]] = []
            for entry in entries:
                child = f"{rel}{entry.name}"
                found = self._visit(entry, child)
                if found is not None:
                    subdirs.append((Path(entry.path), found))
            stack.extend(reversed(subdirs))

    def _visit(self, entry: os.DirEntry[str], rel: str) -> str | None:
        """Handle one directory entry; return the relative prefix if it is a directory."""
        follow = self.options.follow_symlinks
        path = Path(entry.path)
        try:
            linked = entry.is_symlink() or is_junction(entry.stat(follow_symlinks=False))
            if linked and not follow:
                return None
            if entry.is_dir(follow_symlinks=follow):
                return None if self._excluded(entry.name, rel) else rel + "/"
            if not entry.is_file(follow_symlinks=follow):
                return None
            if self._excluded(entry.name, rel) or not self._included(entry.name, rel):
                return None
            info = entry.stat(follow_symlinks=follow)
        except OSError as exc:
            self.issue(path, exc)
            return None
        self._consider(path, rel, info)
        return None

    def _consider(self, path: Path, rel: str, info: os.stat_result) -> None:
        if self.options.accepts_size(info.st_size):
            self.entries.append(Entry(path, info.st_size, info.st_mtime_ns))
        if self.on_progress is not None:
            count = len(self.entries)
            self.on_progress(Progress("walk", count, count))

    def _excluded(self, name: str, rel: str) -> bool:
        return any(_match(pattern, name, rel) for pattern in self.options.exclude)

    def _included(self, name: str, rel: str) -> bool:
        patterns = self.options.include
        return not patterns or any(_match(pattern, name, rel) for pattern in patterns)


def _match(pattern: str, name: str, rel: str) -> bool:
    return fnmatch(rel, pattern) if "/" in pattern else fnmatch(name, pattern)


def real_key(path: Path) -> str:
    """Return a key naming the location ``path`` really refers to, links resolved."""
    try:
        return os.path.normcase(os.path.realpath(path))
    except OSError:
        return os.path.normcase(os.path.abspath(path))


def _first(seen: set[str], path: Path) -> bool:
    """Return True the first time a real location is met, so nothing is walked twice."""
    key = real_key(path)
    if key in seen:
        return False
    seen.add(key)
    return True


def is_junction(info: os.stat_result) -> bool:
    """Return True for a Windows junction (a directory reparse point that is not a symlink)."""
    return getattr(info, "st_reparse_tag", 0) == _MOUNT_POINT


def issue_kind(exc: OSError) -> IssueKind:
    """Classify an OS error as one of the documented issue kinds."""
    if isinstance(exc, PermissionError):
        return "permission"
    if isinstance(exc, FileNotFoundError | NotADirectoryError):
        return "missing"
    return "error"


def group_by_size(entries: Iterable[Entry]) -> dict[int, list[Entry]]:
    """Group entries by size, keeping only sizes shared by two or more entries."""
    groups: dict[int, list[Entry]] = defaultdict(list)
    for entry in entries:
        groups[entry.size].append(entry)
    return {size: items for size, items in groups.items() if len(items) >= 2}
