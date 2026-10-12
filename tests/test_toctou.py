"""Files swapped between scan and apply, or inside the last moment before acting."""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

import pytest
from helpers import junction, symlink, write

import dupefind._apply as apply_module
from dupefind import ActionResult, apply_actions, plan_actions, scan
from dupefind._hash import same_content as real_same_content

DATA = b"original duplicate " * 50
OTHER = b"unique bystander!! " * 50  # same size, different bytes


def _setup(tmp_path: Path, action: str = "delete") -> tuple[Path, Path, list[object]]:
    keep = write(tmp_path / "a-keep.bin", DATA)
    os.utime(keep, (1_000_000, 1_000_000))
    target = write(tmp_path / "b-copy.bin", DATA)
    plan = plan_actions(scan(tmp_path).groups, action=action)  # type: ignore[arg-type]
    assert [(p.keep, p.target) for p in plan] == [(keep, target)]
    return keep, target, list(plan)


def _apply(plan: list[object]) -> ActionResult:
    (result,) = apply_actions(plan, dry_run=False)  # type: ignore[arg-type]
    return result


def _copies(*paths: Path) -> int:
    return sum(1 for p in paths if p.exists() and p.read_bytes() == DATA)


@pytest.mark.parametrize("action", ["delete", "hardlink"])
def test_target_swapped_for_a_symlink_to_the_keeper(tmp_path: Path, action: str) -> None:
    keep, target, plan = _setup(tmp_path, action)
    target.unlink()
    symlink(target, keep)

    result = _apply(plan)

    assert result.status == "skipped" and "link" in result.reason
    assert target.is_symlink() and keep.read_bytes() == DATA


@pytest.mark.parametrize("action", ["delete", "hardlink"])
def test_target_swapped_for_a_symlink_to_a_unique_file(tmp_path: Path, action: str) -> None:
    _, target, plan = _setup(tmp_path, action)
    bystander = write(tmp_path / "elsewhere" / "unique.bin", DATA)
    target.unlink()
    symlink(target, bystander)

    assert _apply(plan).status == "skipped"
    assert target.is_symlink() and bystander.read_bytes() == DATA


def test_target_swapped_for_a_junction(tmp_path: Path) -> None:
    _, target, plan = _setup(tmp_path)
    inside = tmp_path / "dir"
    write(inside / "precious", b"keep me")
    target.unlink()
    junction(target, inside)

    assert _apply(plan).status == "skipped"
    assert (inside / "precious").read_bytes() == b"keep me"


def test_target_swapped_for_a_different_file(tmp_path: Path) -> None:
    keep, target, plan = _setup(tmp_path)
    target.unlink()
    write(target, OTHER)

    result = _apply(plan)

    assert result.status == "skipped" and "content differs" in result.reason
    assert target.read_bytes() == OTHER and keep.read_bytes() == DATA


@pytest.mark.parametrize("action", ["delete", "hardlink"])
def test_keeper_swapped_for_a_symlink_to_the_target(tmp_path: Path, action: str) -> None:
    keep, target, plan = _setup(tmp_path, action)
    keep.unlink()
    symlink(keep, target)

    result = _apply(plan)

    assert result.status == "skipped" and "same file" in result.reason
    assert target.read_bytes() == DATA and not target.is_symlink()


def _swap_in_window(monkeypatch: pytest.MonkeyPatch, swap: Callable[[], None]) -> None:
    """Run ``swap`` after the byte comparison passed and before the act."""
    real = real_same_content

    def compare_then_swap(first: Path, second: Path) -> bool:
        equal = real(first, second)
        swap()
        return equal

    monkeypatch.setattr(apply_module, "same_content", compare_then_swap)


@pytest.mark.parametrize("action", ["delete", "hardlink"])
def test_target_replaced_in_the_last_moment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, action: str
) -> None:
    keep, target, plan = _setup(tmp_path, action)
    impostor = write(tmp_path / "impostor.tmp", OTHER)
    _swap_in_window(monkeypatch, lambda: os.replace(impostor, target))

    result = _apply(plan)

    assert result.status == "skipped" and "target was replaced" in result.reason
    assert target.read_bytes() == OTHER and keep.read_bytes() == DATA
    assert not list(tmp_path.glob(".*.dupefind"))


@pytest.mark.parametrize("action", ["delete", "hardlink"])
def test_target_turned_into_a_symlink_in_the_last_moment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, action: str
) -> None:
    _, target, plan = _setup(tmp_path, action)
    bystander = write(tmp_path / "other" / "unique.bin", DATA)

    def swap() -> None:
        target.unlink()
        symlink(target, bystander)

    _swap_in_window(monkeypatch, swap)

    assert _apply(plan).status == "skipped"
    assert target.is_symlink() and bystander.read_bytes() == DATA


@pytest.mark.parametrize("action", ["delete", "hardlink"])
def test_keeper_removed_in_the_last_moment_leaves_a_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, action: str
) -> None:
    keep, target, plan = _setup(tmp_path, action)
    _swap_in_window(monkeypatch, keep.unlink)

    result = _apply(plan)

    assert result.status == "skipped" and "changed before acting" in result.reason
    assert _copies(keep, target) == 1 and target.read_bytes() == DATA


@pytest.mark.parametrize("action", ["delete", "hardlink"])
def test_keeper_rewritten_in_the_last_moment_leaves_the_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, action: str
) -> None:
    keep, target, plan = _setup(tmp_path, action)

    def rewrite() -> None:
        keep.unlink()
        write(keep, OTHER)

    _swap_in_window(monkeypatch, rewrite)

    result = _apply(plan)

    assert result.status == "skipped" and "kept copy was replaced" in result.reason
    assert target.read_bytes() == DATA and keep.read_bytes() == OTHER
