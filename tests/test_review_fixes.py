"""Regressions found in review: link keepers, symlinked roots, encodings, empty files."""

from __future__ import annotations

import io
import os
import subprocess
import sys
from pathlib import Path

from helpers import symlink, write

from dupefind import PlannedAction, ScanOptions, apply_actions, choose_keeper, plan_actions, scan
from dupefind._cli import main

SRC = Path(__file__).resolve().parents[1] / "src"


def test_hardlink_to_a_relative_symlink_keeper_links_the_real_file(tmp_path: Path) -> None:
    real = write(tmp_path / "d1" / "R", b"keeper bytes")
    link = symlink(tmp_path / "d1" / "L", Path("R"))
    other = write(tmp_path / "d2" / "R", b"keeper bytes")
    plan = [PlannedAction("hardlink", other, link, 12, "x")]

    (result,) = apply_actions(plan, dry_run=False)

    assert result.status == "done"
    assert other.read_bytes() == b"keeper bytes"
    assert not other.is_symlink()
    assert os.path.samefile(other, real)


def test_symlinked_root_keeps_the_regular_file_and_spares_the_link(tmp_path: Path) -> None:
    real = write(tmp_path / "d1" / "R", b"keeper bytes")
    os.utime(real, (1_000_000, 1_000_000))
    link = symlink(tmp_path / "d1" / "L", Path("R"))
    other = write(tmp_path / "d2" / "R", b"keeper bytes")

    groups = scan(link, tmp_path / "d2", options=ScanOptions(follow_symlinks=True)).groups
    results = apply_actions(plan_actions(groups, action="hardlink"), dry_run=False)

    (result,) = results
    assert (result.status, result.planned.keep, result.planned.target) == ("skipped", other, link)
    assert "link" in result.reason
    assert link.is_symlink()
    assert real.read_bytes() == other.read_bytes() == link.read_bytes() == b"keeper bytes"


def test_a_symlink_keeper_loses_to_a_regular_file(tmp_path: Path) -> None:
    outside = write(tmp_path / "outside" / "data", b"shared")
    os.utime(outside, (1_000_000, 1_000_000))
    link = symlink(tmp_path / "tree" / "a-link", outside)
    copy = write(tmp_path / "tree" / "b-copy", b"shared")

    (group,) = scan(tmp_path / "tree", options=ScanOptions(follow_symlinks=True)).groups

    assert choose_keeper(group, "oldest").path == copy
    (result,) = apply_actions(plan_actions([group]), dry_run=False)
    assert (result.planned.target, result.status) == (link, "skipped")
    assert link.is_symlink()
    assert copy.read_bytes() == b"shared" and outside.read_bytes() == b"shared"


def test_a_symlinked_file_given_as_a_root_is_compared(tmp_path: Path) -> None:
    target = write(tmp_path / "d1" / "R", b"twin")
    link = symlink(tmp_path / "d1" / "L", target)
    write(tmp_path / "d2" / "copy", b"twin")

    report = scan(link, tmp_path / "d2")

    assert report.issues == []
    (group,) = report.groups
    assert group.paths == [link, tmp_path / "d2" / "copy"]


def test_unencodable_paths_do_not_crash_the_cli(tmp_path: Path) -> None:
    write(tmp_path / "ü日本.txt", b"same")
    write(tmp_path / "plain.txt", b"same")
    env = {**os.environ, "PYTHONPATH": str(SRC), "PYTHONIOENCODING": "ascii"}

    done = subprocess.run(
        [sys.executable, "-m", "dupefind", str(tmp_path)],
        capture_output=True,
        env=env,
        check=False,
    )

    assert done.returncode == 0, done.stderr
    assert b"\\xfc\\u65e5\\u672c.txt" in done.stdout
    assert b"Traceback" not in done.stderr


def test_actions_leave_empty_files_alone_unless_asked(tmp_path: Path) -> None:
    write(tmp_path / "a" / "__init__.py", b"")
    write(tmp_path / "b" / "__init__.py", b"")

    assert main([str(tmp_path), "--delete", "--apply", "-q"], stdout=io.StringIO()) == 0
    assert len(list(tmp_path.rglob("__init__.py"))) == 2

    assert main([str(tmp_path), "--delete", "--apply", "--empty", "-q"], stdout=io.StringIO()) == 0
    assert len(list(tmp_path.rglob("__init__.py"))) == 1


def test_plain_report_still_lists_empty_files(tmp_path: Path) -> None:
    write(tmp_path / "x", b"")
    write(tmp_path / "y", b"")
    out = io.StringIO()

    main([str(tmp_path), "-q"], stdout=out)

    assert out.getvalue().startswith("# 0 bytes x 2 files")
