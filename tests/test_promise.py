"""The whole promise on one real tree: correct groups, read-only scan, safe clean-up."""

from __future__ import annotations

import contextlib
import hashlib
import os
import sys
from pathlib import Path

from helpers import as_sets, oracle, write

from dupefind import ScanOptions, apply_actions, find_duplicates, plan_actions, scan


def _snapshot(root: Path) -> dict[str, tuple[int, str]]:
    return {
        str(p): (p.stat().st_mtime_ns, hashlib.sha256(p.read_bytes()).hexdigest())
        for p in sorted(root.rglob("*"))
        if p.is_file() and not p.is_symlink()
    }


def _build(root: Path) -> None:
    write(root / "photos" / "a.jpg", b"J" * 6000)
    write(root / "backup" / "a copy.jpg", b"J" * 6000)
    write(root / "backup" / "old" / "a.jpg", b"J" * 6000)
    write(root / "near" / "x", b"N" * 6000 + b"1")
    write(root / "near" / "y", b"N" * 6000 + b"2")
    write(root / "empty1", b"")
    write(root / "empty2", b"")
    write(root / "solo.txt", b"unique content")
    os.link(root / "photos" / "a.jpg", root / "photos" / "a-link.jpg")
    os.link(root / "solo.txt", root / "solo-link.txt")
    if sys.platform == "win32":
        import _winapi

        _winapi.CreateJunction(str(root / "photos"), str(root / "photos-junction"))
    with contextlib.suppress(OSError):
        (root / "solo-symlink.txt").symlink_to(root / "solo.txt")


def test_the_complete_promise(tmp_path: Path) -> None:
    _build(tmp_path)
    before = _snapshot(tmp_path)

    report = scan(tmp_path)

    # Groups agree with brute force; hard links are aliases, links are not followed.
    assert as_sets(report.groups) == oracle(tmp_path)
    assert report.issues == []
    assert [g.size for g in report.groups] == [6000, 0]
    jpg = report.groups[0]
    assert len(jpg.files) == 3
    assert sum(len(f.aliases) for f in jpg.files) == 1
    assert all("solo" not in str(p) for g in report.groups for p in g.paths)
    # The old API agrees and the scan changed nothing.
    assert {d: sorted(p) for d, p in find_duplicates(tmp_path).items()} == {
        g.digest: sorted(g.paths) for g in report.groups
    }
    assert _snapshot(tmp_path) == before

    # Dry run changes nothing; applying keeps exactly one name-set per group.
    options = ScanOptions(min_size=1)
    plan = plan_actions(scan(tmp_path, options=options).groups, keep="shortest")
    assert {r.status for r in apply_actions(plan)} == {"dry-run"}
    assert _snapshot(tmp_path) == before
    results = apply_actions(plan, dry_run=False)
    assert {r.status for r in results} == {"done"}
    assert scan(tmp_path, options=options).groups == []
    assert (tmp_path / "solo.txt").read_bytes() == b"unique content"
    assert (tmp_path / "near" / "x").exists() and (tmp_path / "near" / "y").exists()
    survivors = [p for p in tmp_path.rglob("*.jpg") if not p.is_symlink()]
    assert {p.read_bytes() for p in survivors} == {b"J" * 6000}
