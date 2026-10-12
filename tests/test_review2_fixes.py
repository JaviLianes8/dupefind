"""Regressions from the second review: race windows, read-only keepers, data streams."""

from __future__ import annotations

import contextlib
import os
import stat
import sys
from collections.abc import Callable
from pathlib import Path

import pytest
from helpers import write

import dupefind._act as act_module
from dupefind import ActionResult, apply_actions, plan_actions, scan
from dupefind._apply import unchanged as real_unchanged

DATA = b"duplicate payload " * 40
OTHER = b"bystander content " * 40  # same size, different bytes
windows_only = pytest.mark.skipif(sys.platform != "win32", reason="Windows behaviour")


def _pair(tmp_path: Path, action: str) -> tuple[Path, Path, ActionResult]:
    keep = write(tmp_path / "a-keep.bin", DATA)
    os.utime(keep, (1_000_000, 1_000_000))
    target = write(tmp_path / "b-copy.bin", DATA)
    plan = plan_actions(scan(tmp_path).groups, action=action)  # type: ignore[arg-type]
    (result,) = apply_actions(plan)
    assert result.status == "dry-run"
    return keep, target, result


def _act(result: ActionResult) -> ActionResult:
    (done,) = apply_actions([result.planned], dry_run=False)
    return done


def _leftovers(root: Path) -> list[Path]:
    return list(root.glob(".*.dupefind"))


def _after_last_check(monkeypatch: pytest.MonkeyPatch, mutate: Callable[[], None]) -> None:
    """Run ``mutate`` right after the final pre-act stat check has passed."""

    def check_then_mutate(*args: object) -> str:
        reason = real_unchanged(*args)  # type: ignore[arg-type]
        mutate()
        return reason

    monkeypatch.setattr(act_module, "unchanged", check_then_mutate)


@pytest.mark.parametrize("action", ["delete", "hardlink"])
def test_target_swapped_after_the_last_check_is_put_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, action: str
) -> None:
    keep, target, planned = _pair(tmp_path, action)
    impostor = write(tmp_path / "impostor.tmp", OTHER)
    _after_last_check(monkeypatch, lambda: os.replace(impostor, target))

    result = _act(planned)

    assert result.status == "skipped" and "target was replaced" in result.reason
    assert target.read_bytes() == OTHER and keep.read_bytes() == DATA
    assert _leftovers(tmp_path) == []


@pytest.mark.parametrize("action", ["delete", "hardlink"])
def test_keeper_deleted_after_the_last_check_never_empties_the_group(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, action: str
) -> None:
    keep, target, planned = _pair(tmp_path, action)

    def try_delete_keeper() -> None:
        with contextlib.suppress(PermissionError):  # Windows: the kept file is held open
            keep.unlink()

    _after_last_check(monkeypatch, try_delete_keeper)

    result = _act(planned)

    copies = [p for p in (keep, target) if p.exists() and p.read_bytes() == DATA]
    assert copies
    if not keep.exists():
        assert result.status == "skipped" and target.read_bytes() == DATA
    assert _leftovers(tmp_path) == []


def test_failed_link_check_restores_target_and_read_only_keeper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    keep, target, planned = _pair(tmp_path, "hardlink")
    os.chmod(keep, 0o444)
    mode = os.stat(keep).st_mode
    monkeypatch.setattr(os.path, "samestat", lambda a, b: False)

    result = _act(planned)

    assert result.status == "failed" and "not the kept file" in result.reason
    assert os.stat(keep).st_mode == mode and not os.stat(keep).st_mode & stat.S_IWUSR
    assert target.read_bytes() == DATA and os.stat(target).st_nlink == 1
    assert os.stat(keep).st_nlink == 1
    assert _leftovers(tmp_path) == []


@windows_only
def test_read_only_keeper_with_a_busy_target_fails_cleanly(tmp_path: Path) -> None:
    keep, target, planned = _pair(tmp_path, "hardlink")
    os.chmod(keep, 0o444)

    with target.open("rb"):
        result = _act(planned)

    assert result.status == "failed"
    assert target.read_bytes() == DATA and not os.path.samefile(keep, target)
    assert _leftovers(tmp_path) == []


@windows_only
@pytest.mark.parametrize("action", ["delete", "hardlink"])
def test_target_with_an_extra_data_stream_is_refused(tmp_path: Path, action: str) -> None:
    _, target, planned = _pair(tmp_path, action)
    with open(f"{target}:notes", "wb") as stream:
        stream.write(b"only copy of these notes")

    result = _act(planned)

    assert result.status == "skipped" and ":notes:$DATA" in result.reason
    with open(f"{target}:notes", "rb") as stream:
        assert stream.read() == b"only copy of these notes"


@windows_only
def test_download_marker_stream_does_not_block(tmp_path: Path) -> None:
    _, target, planned = _pair(tmp_path, "delete")
    with open(f"{target}:Zone.Identifier", "wb") as stream:
        stream.write(b"[ZoneTransfer]\r\nZoneId=3\r\n")

    assert _act(planned).status == "done"
    assert not target.exists()


def test_an_issue_is_reported_once_per_path(tmp_path: Path) -> None:
    missing = tmp_path / "absent"

    report = scan(missing, missing, tmp_path)

    assert [(i.path, i.kind) for i in report.issues] == [(missing, "missing")]
