"""Issues, progress, stats and streaming on real trees."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from helpers import unreadable, write

from dupefind import Progress, ScanOptions, iter_groups, scan


def test_missing_root_is_reported_not_raised(tmp_path: Path) -> None:
    report = scan(tmp_path / "absent")

    assert report.groups == []
    (issue,) = report.issues
    assert issue.kind == "missing"
    assert issue.path == tmp_path / "absent"


def test_unreadable_file_is_skipped_and_reported(tmp_path: Path) -> None:
    write(tmp_path / "a", b"same bytes")
    write(tmp_path / "b", b"same bytes")
    locked = write(tmp_path / "c", b"same bytes")

    with unreadable(locked):
        report = scan(tmp_path)

    (group,) = report.groups
    assert group.paths == [tmp_path / "a", tmp_path / "b"]
    assert [(i.path, i.kind) for i in report.issues] == [(locked, "permission")]


def test_unreadable_directory_is_skipped_and_reported(tmp_path: Path) -> None:
    write(tmp_path / "a", b"same bytes")
    write(tmp_path / "b", b"same bytes")
    locked = tmp_path / "locked"
    write(locked / "c", b"same bytes")

    with unreadable(locked):
        try:
            os.listdir(locked)
        except PermissionError:
            report = scan(tmp_path)
        else:
            pytest.skip("this account can still list a directory it is denied")

    (group,) = report.groups
    assert len(group.files) == 2
    assert [(i.path, i.kind) for i in report.issues] == [(locked, "permission")]


def test_file_changed_during_the_scan_is_dropped_and_reported(tmp_path: Path) -> None:
    write(tmp_path / "a", b"q" * 10_000)
    write(tmp_path / "b", b"q" * 10_000)
    victim = write(tmp_path / "c", b"q" * 10_000)

    def touch_once(progress: Progress) -> None:
        if progress.stage == "partial" and progress.done == 1:
            stamp = victim.stat().st_mtime_ns + 5_000_000_000
            os.utime(victim, ns=(stamp, stamp))

    report = scan(tmp_path, on_progress=touch_once)

    (group,) = report.groups
    assert group.paths == [tmp_path / "a", tmp_path / "b"]
    assert [(i.path, i.kind) for i in report.issues] == [(victim, "changed")]


def test_file_growing_during_the_scan_is_dropped(tmp_path: Path) -> None:
    write(tmp_path / "a", b"g" * 10_000)
    victim = write(tmp_path / "b", b"g" * 10_000)

    def grow(progress: Progress) -> None:
        if progress.stage == "partial" and progress.done == 2:
            with victim.open("ab") as handle:
                handle.write(b"more")

    report = scan(tmp_path, on_progress=grow)

    assert report.groups == []
    assert [i.kind for i in report.issues] == ["changed"]


def test_progress_reports_every_stage_in_order(tmp_path: Path) -> None:
    for name in "abc":
        write(tmp_path / name, b"p" * 9000)
    events: list[Progress] = []

    scan(tmp_path, on_progress=events.append)

    stages = [e.stage for e in events]
    assert stages == ["walk"] * 3 + ["partial"] * 3 + ["full"] * 3
    assert events[-1] == Progress("full", 3, 3, 27_000)
    assert events[5] == Progress("partial", 3, 3, 3 * 4096)


def test_stats_count_the_work(tmp_path: Path) -> None:
    write(tmp_path / "a", b"s" * 5000)
    write(tmp_path / "b", b"s" * 5000)
    write(tmp_path / "c", b"s" * 5000)
    write(tmp_path / "unique", b"u")

    stats = scan(tmp_path).stats

    assert (stats.files_seen, stats.candidates, stats.groups) == (4, 3, 1)
    assert (stats.duplicate_files, stats.wasted_bytes) == (3, 10_000)


def test_groups_stream_largest_first_and_accept_files_as_roots(tmp_path: Path) -> None:
    small = [write(tmp_path / f"s{i}", b"1") for i in range(2)]
    large = [write(tmp_path / f"l{i}", b"2" * 100) for i in range(2)]

    groups = list(iter_groups(*small, *large, options=ScanOptions()))

    assert [g.size for g in groups] == [100, 1]
    assert groups[0].paths == large


def test_huge_sparse_files_differing_at_the_end(tmp_path: Path) -> None:
    size = 64 * 1024 * 1024
    for name, tail in (("a", b"1"), ("b", b"1"), ("c", b"2")):
        with (tmp_path / name).open("wb") as handle:
            handle.seek(size - 1)
            handle.write(tail)

    (group,) = scan(tmp_path).groups

    assert group.paths == [tmp_path / "a", tmp_path / "b"]
    assert group.size == size
