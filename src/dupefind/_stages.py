"""The comparison stages after the walk: identity, partial hash, full hash, change check."""

from __future__ import annotations

import os
from collections import defaultdict
from collections.abc import Callable, Iterator

from ._hash import hash_prefix, hash_whole
from ._options import ScanOptions
from ._scan import Entry, Walker, real_key
from ._types import DuplicateFile, DuplicateGroup, Progress, ScanIssue, ScanStats, Stage


class Stages:
    """Run the staged comparison over the size groups produced by a walk."""

    def __init__(self, walker: Walker, stats: ScanStats) -> None:
        self.walker = walker
        self.options: ScanOptions = walker.options
        self.stats = stats

    def identify(self, same_size: list[Entry]) -> list[Entry]:
        """Fill in file identities and merge several names of one file, unless asked not to."""
        merged: dict[tuple[int, int], Entry] = {}
        result: list[Entry] = []
        places: set[str] = set()
        for entry in same_size:
            place = real_key(entry.path)
            if place in places:
                continue  # the same directory entry reached by two spellings
            places.add(place)
            info = self._restat(entry)
            if info is None:
                continue
            if info.st_ino:
                entry.identity = (info.st_dev, info.st_ino)
            known = merged.get(entry.identity) if entry.identity else None
            if known is not None and not self.options.hardlinks:
                known.aliases.append(entry.path)
                continue
            if entry.identity:
                merged.setdefault(entry.identity, entry)
            result.append(entry)
        return result if len(result) >= 2 else []

    def run(self, groups: list[list[Entry]]) -> Iterator[DuplicateGroup]:
        """Yield confirmed groups, the largest files first."""
        total = sum(len(group) for group in groups)
        self.stats.candidates = total
        pending: list[list[Entry]] = []
        done: list[list[tuple[str, Entry]]] = []
        counter = _Counter("partial", total, self.walker.on_progress, self.stats.bytes_read)
        for group in groups:
            for prefix_group in self._regroup(group, self._partial, counter).values():
                if len(prefix_group) < 2:
                    continue
                if prefix_group[0][1].size <= self.options.partial_size:
                    done.append(prefix_group)  # the prefix covered the whole file
                else:
                    pending.append([entry for _, entry in prefix_group])
        for prefix_group in done:
            yield from self._confirm(prefix_group)
        total = sum(len(group) for group in pending)
        counter = _Counter("full", total, self.walker.on_progress, self.stats.bytes_read)
        for group in pending:
            for full_group in self._regroup(group, self._full, counter).values():
                yield from self._confirm(full_group)

    def _partial(self, entry: Entry) -> str:
        digest, read = hash_prefix(entry.path, self.options.algorithm, self.options.partial_size)
        self.stats.partial_hashed += 1
        self.stats.bytes_read += read
        return digest

    def _full(self, entry: Entry) -> str:
        digest, read = hash_whole(entry.path, self.options.algorithm)
        self.stats.full_hashed += 1
        self.stats.bytes_read += read
        if read != entry.size:
            raise _Changed(f"size changed from {entry.size} to {read} bytes while reading")
        return digest

    def _regroup(
        self, group: list[Entry], key: Callable[[Entry], str], counter: _Counter
    ) -> dict[str, list[tuple[str, Entry]]]:
        result: dict[str, list[tuple[str, Entry]]] = defaultdict(list)
        for entry in group:
            try:
                digest = key(entry)
            except _Changed as exc:
                self.walker.issues.append(ScanIssue(entry.path, "changed", str(exc)))
                continue
            except OSError as exc:
                self.walker.issue(entry.path, exc)
                continue
            finally:
                counter.step(self.stats.bytes_read)
            result[digest].append((digest, entry))
        return result

    def _confirm(self, matches: list[tuple[str, Entry]]) -> Iterator[DuplicateGroup]:
        """Drop files that changed since they were listed; yield what is still a group."""
        kept = [entry for _, entry in matches if self._unchanged(entry)]
        if len(kept) < 2:
            return
        kept.sort(key=lambda entry: str(entry.path))
        files = tuple(
            DuplicateFile(e.path, e.size, e.mtime_ns, tuple(sorted(e.aliases))) for e in kept
        )
        group = DuplicateGroup(matches[0][0], self.options.algorithm, kept[0].size, files)
        self.stats.groups += 1
        self.stats.duplicate_files += len(files)
        self.stats.wasted_bytes += group.wasted_bytes
        yield group

    def _restat(self, entry: Entry) -> os.stat_result | None:
        try:
            info = os.stat(entry.path, follow_symlinks=self.options.follow_symlinks)
        except OSError as exc:
            self.walker.issue(entry.path, exc)
            return None
        if (info.st_size, info.st_mtime_ns) != (entry.size, entry.mtime_ns):
            message = "size or modification time changed during the scan"
            self.walker.issues.append(ScanIssue(entry.path, "changed", message))
            return None
        return info

    def _unchanged(self, entry: Entry) -> bool:
        return self._restat(entry) is not None


class _Changed(Exception):
    """A file changed while it was being read."""


class _Counter:
    def __init__(
        self, stage: Stage, total: int, sink: Callable[[Progress], None] | None, start: int
    ) -> None:
        self.stage: Stage = stage
        self.total = total
        self.done = 0
        self.start = start
        self.sink = sink

    def step(self, bytes_read: int) -> None:
        self.done += 1
        if self.sink is not None:
            self.sink(Progress(self.stage, self.done, self.total, bytes_read - self.start))
