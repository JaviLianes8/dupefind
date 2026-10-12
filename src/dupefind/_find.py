"""Staged duplicate detection: size, then a partial hash, then a full hash."""

from __future__ import annotations

import dataclasses
import os
from collections.abc import Callable, Iterator
from pathlib import Path

from ._options import ScanOptions
from ._scan import Walker, group_by_size
from ._stages import Stages
from ._types import DuplicateGroup, Progress, ScanIssue, ScanReport, ScanStats

PathLike = str | os.PathLike[str]
ProgressCallback = Callable[[Progress], None]


def iter_groups(
    *roots: PathLike,
    options: ScanOptions | None = None,
    on_progress: ProgressCallback | None = None,
    issues: list[ScanIssue] | None = None,
    stats: ScanStats | None = None,
) -> Iterator[DuplicateGroup]:
    """Stream ``DuplicateGroup`` objects for files under ``roots`` as they are confirmed.

    Each root may be a directory (walked recursively) or a single file. Roots that
    are links are followed; links found inside them are not, unless
    ``options.follow_symlinks`` is true. A file reached twice (overlapping roots, a
    loop) is compared once. Files are only read, never changed.

    The work is staged so that most files are never read in full:

    1. walk and group by size; a unique size cannot have a duplicate;
    2. merge names of the same file (hard links) unless ``options.hardlinks``;
    3. hash the first ``options.partial_size`` bytes of same-size files;
    4. hash in full only files that still match, and re-check that each file's size
       and modification time did not change while it was being read.

    Paths that cannot be used are appended to ``issues`` (when given) and left out.
    ``stats`` (when given) is filled in while the generator runs. Groups of larger
    files come first.
    """
    opts = options if options is not None else ScanOptions()
    sink: list[ScanIssue] = issues if issues is not None else []
    counters = stats if stats is not None else ScanStats()
    walker = Walker(opts, sink, on_progress)
    entries = walker.walk(roots)
    counters.files_seen = len(entries)
    stages = Stages(walker, counters)
    by_size = group_by_size(entries)
    candidates = [stages.identify(by_size[size]) for size in sorted(by_size, reverse=True)]
    yield from stages.run([group for group in candidates if group])


def scan(
    *roots: PathLike,
    options: ScanOptions | None = None,
    on_progress: ProgressCallback | None = None,
) -> ScanReport:
    """Scan ``roots`` and return a ``ScanReport`` with groups, issues and counters.

    This is ``iter_groups`` collected into one object. See it for the staging and
    the link policies. Nothing on disk is modified.
    """
    report = ScanReport()
    report.groups = list(
        iter_groups(
            *roots,
            options=options,
            on_progress=on_progress,
            issues=report.issues,
            stats=report.stats,
        )
    )
    return report


def iter_duplicates(
    root: PathLike,
    *,
    follow_symlinks: bool = False,
    options: ScanOptions | None = None,
) -> Iterator[tuple[str, list[Path]]]:
    """Yield ``(full hash, paths)`` for every set of two or more identical files.

    The original ``0.1.0`` interface, kept for compatibility. ``options`` adds every
    scan setting; ``follow_symlinks=True`` turns link following on in either case.
    Paths are the first name reached for each file; hard links to the same file are
    one file here (see ``ScanOptions.hardlinks``). Use ``iter_groups`` for typed
    results and ``scan`` for the issues met.
    """
    opts = _with_follow(options, follow_symlinks)
    for group in iter_groups(root, options=opts):
        yield group.digest, group.paths


def find_duplicates(
    root: PathLike,
    *,
    follow_symlinks: bool = False,
    options: ScanOptions | None = None,
) -> dict[str, list[Path]]:
    """Return duplicate files under ``root`` grouped by their full content hash.

    Each value holds two or more paths with identical content; files with no
    duplicate are left out. Nothing on disk is modified. See ``iter_duplicates``.
    """
    return dict(iter_duplicates(root, follow_symlinks=follow_symlinks, options=options))


def _with_follow(options: ScanOptions | None, follow_symlinks: bool) -> ScanOptions:
    opts = options if options is not None else ScanOptions()
    if follow_symlinks and not opts.follow_symlinks:
        opts = dataclasses.replace(opts, follow_symlinks=True)
    return opts
