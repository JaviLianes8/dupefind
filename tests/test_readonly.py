"""Read-only files are refused by every action and left exactly as they were."""

from __future__ import annotations

import io
import os
import stat
import sys
from pathlib import Path

import pytest
from helpers import write

from dupefind import apply_actions, plan_actions, scan
from dupefind._cli import main


def _read_only(path: Path) -> Path:
    os.chmod(path, 0o444)  # sets the read-only attribute on Windows
    return path


def _pair(tmp_path: Path) -> tuple[Path, Path]:
    keep = write(tmp_path / "a-keep.bin", b"payload " * 100)
    os.utime(keep, (1_000_000, 1_000_000))
    return keep, write(tmp_path / "b-copy.bin", b"payload " * 100)


@pytest.mark.parametrize("action", ["delete", "hardlink"])
def test_read_only_target_is_refused_and_untouched(tmp_path: Path, action: str) -> None:
    keep, target = _pair(tmp_path)
    _read_only(target)
    before = os.stat(target)

    plan = plan_actions(scan(tmp_path).groups, action=action)  # type: ignore[arg-type]
    (dry,) = apply_actions(plan)
    (result,) = apply_actions(plan, dry_run=False)

    assert (dry.status, result.status) == ("skipped", "skipped")
    assert result.reason == "target is read-only"
    after = os.stat(target)
    assert (after.st_ino, after.st_mode, after.st_mtime_ns) == (
        before.st_ino,
        before.st_mode,
        before.st_mtime_ns,
    )
    assert not os.path.samefile(keep, target)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["a-keep.bin", "b-copy.bin"]


def test_read_only_target_in_a_bigger_group_only_skips_itself(tmp_path: Path) -> None:
    keep, target = _pair(tmp_path)
    other = write(tmp_path / "c-copy.bin", keep.read_bytes())
    _read_only(target)

    results = apply_actions(plan_actions(scan(tmp_path).groups), dry_run=False)

    assert {r.planned.target: r.status for r in results} == {target: "skipped", other: "done"}
    assert keep.exists() and target.exists() and not other.exists()


@pytest.mark.parametrize("action", ["delete", "hardlink"])
def test_read_only_kept_copy_is_fine(tmp_path: Path, action: str) -> None:
    keep, target = _pair(tmp_path)
    _read_only(keep)

    plan = plan_actions(scan(tmp_path).groups, action=action)  # type: ignore[arg-type]
    (result,) = apply_actions(plan, dry_run=False)

    assert result.status == "done"
    assert keep.read_bytes() == b"payload " * 100
    if action == "hardlink":
        assert os.path.samefile(keep, target)
    else:
        assert not target.exists()


def test_cli_reports_the_refusal_and_exits_0(tmp_path: Path) -> None:
    _, target = _pair(tmp_path)
    _read_only(target)
    out = io.StringIO()

    code = main([str(tmp_path), "--delete", "--apply", "-q"], stdout=out)

    assert code == 0
    assert f"[skipped] delete {target}" in out.getvalue()
    assert "target is read-only" in out.getvalue()
    assert target.exists()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX directory permissions")
@pytest.mark.parametrize("action", ["delete", "hardlink"])
def test_read_only_directory_fails_cleanly(tmp_path: Path, action: str) -> None:
    if getattr(os, "geteuid", lambda: 1)() == 0:
        pytest.skip("root ignores directory permissions")
    keep, target = _pair(tmp_path)
    locked = tmp_path / "locked"
    locked.mkdir()
    moved = target.rename(locked / target.name)
    plan = plan_actions(scan(tmp_path).groups, action=action)  # type: ignore[arg-type]
    locked.chmod(stat.S_IRUSR | stat.S_IXUSR)
    try:
        (result,) = apply_actions(plan, dry_run=False)
    finally:
        locked.chmod(stat.S_IRWXU)

    assert result.status == "failed"
    assert sorted(p.name for p in locked.iterdir()) == [moved.name]
    assert not os.path.samefile(keep, moved)
