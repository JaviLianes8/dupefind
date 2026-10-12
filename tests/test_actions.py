"""Planning and applying clean-up actions, only ever inside temporary directories."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from helpers import write

from dupefind import (
    DuplicateFile,
    DuplicateGroup,
    PlannedAction,
    apply_actions,
    choose_keeper,
    plan_actions,
    scan,
)


def _aged(path: Path, data: bytes, seconds: int) -> Path:
    write(path, data)
    os.utime(path, (seconds, seconds))
    return path


def _tree(tmp_path: Path) -> dict[str, Path]:
    return {
        "old": _aged(tmp_path / "zz" / "old.bin", b"payload", 1_000_000),
        "new": _aged(tmp_path / "new.bin", b"payload", 3_000_000),
        "mid": _aged(tmp_path / "deep" / "er" / "mid.bin", b"payload", 2_000_000),
        "unique": write(tmp_path / "unique.bin", b"one of a kind"),
    }


@pytest.mark.parametrize(
    ("keep", "survivor"),
    [("oldest", "old"), ("newest", "new"), ("shortest", "new"), ("first", "deep")],
)
def test_keep_policy_selects_the_documented_file(tmp_path: Path, keep: str, survivor: str) -> None:
    files = _tree(tmp_path)
    (group,) = scan(tmp_path).groups

    chosen = choose_keeper(group, keep)  # type: ignore[arg-type]

    expected = files["mid"] if survivor == "deep" else files[survivor]
    assert chosen.path == expected


def test_unknown_policy_and_action_are_rejected(tmp_path: Path) -> None:
    _tree(tmp_path)
    groups = scan(tmp_path).groups
    with pytest.raises(ValueError, match="keep policy"):
        plan_actions(groups, keep="largest")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="action"):
        plan_actions(groups, action="move")  # type: ignore[arg-type]


def test_dry_run_is_the_default_and_changes_nothing(tmp_path: Path) -> None:
    files = _tree(tmp_path)
    before = sorted(p for p in tmp_path.rglob("*") if p.is_file())

    results = apply_actions(plan_actions(scan(tmp_path).groups))

    assert {r.status for r in results} == {"dry-run"}
    assert sorted(p for p in tmp_path.rglob("*") if p.is_file()) == before
    assert files["unique"].exists()


@pytest.mark.parametrize("keep", ["first", "oldest", "newest", "shortest"])
def test_delete_keeps_exactly_one_copy_per_group(tmp_path: Path, keep: str) -> None:
    files = _tree(tmp_path)
    write(tmp_path / "b1", b"second group")
    write(tmp_path / "b2", b"second group")
    groups = scan(tmp_path).groups
    keepers = {choose_keeper(g, keep).path for g in groups}  # type: ignore[arg-type]

    plan = plan_actions(groups, keep=keep)  # type: ignore[arg-type]
    results = apply_actions(plan, dry_run=False)

    assert {r.status for r in results} == {"done"}
    remaining = {p for p in tmp_path.rglob("*") if p.is_file()}
    assert remaining == keepers | {files["unique"]}
    assert scan(tmp_path).groups == []


def test_delete_also_removes_hard_link_aliases_of_a_copy(tmp_path: Path) -> None:
    keep = _aged(tmp_path / "a.bin", b"payload", 1_000_000)
    copy = _aged(tmp_path / "b.bin", b"payload", 2_000_000)
    os.link(copy, tmp_path / "c.bin")

    apply_actions(plan_actions(scan(tmp_path).groups), dry_run=False)

    assert sorted(tmp_path.iterdir()) == [keep]


def test_hardlink_action_links_copies_to_the_kept_file(tmp_path: Path) -> None:
    files = _tree(tmp_path)

    plan = plan_actions(scan(tmp_path).groups, action="hardlink", keep="oldest")
    results = apply_actions(plan, dry_run=False)

    assert [r.status for r in results] == ["done", "done"]
    for name in ("new", "mid"):
        assert os.path.samefile(files[name], files["old"])
        assert files[name].read_bytes() == b"payload"
    assert scan(tmp_path).groups == []
    assert not list(tmp_path.rglob("*.dupefind"))


def test_second_hardlink_run_is_a_no_op(tmp_path: Path) -> None:
    _tree(tmp_path)
    apply_actions(plan_actions(scan(tmp_path).groups, action="hardlink"), dry_run=False)

    assert plan_actions(scan(tmp_path).groups, action="hardlink") == []


def test_a_target_modified_after_the_scan_is_not_deleted(tmp_path: Path) -> None:
    files = _tree(tmp_path)
    plan = plan_actions(scan(tmp_path).groups, keep="oldest")
    files["new"].write_bytes(b"paylod!")  # same size, now unique

    results = apply_actions(plan, dry_run=False)

    by_target = {r.planned.target: r for r in results}
    assert by_target[files["new"]].status == "skipped"
    assert "content differs" in by_target[files["new"]].reason
    assert files["new"].read_bytes() == b"paylod!"
    assert by_target[files["mid"]].status == "done"


def test_a_missing_kept_file_blocks_every_action_of_its_group(tmp_path: Path) -> None:
    files = _tree(tmp_path)
    plan = plan_actions(scan(tmp_path).groups, keep="oldest")
    files["old"].unlink()

    results = apply_actions(plan, dry_run=False)

    assert {r.status for r in results} == {"skipped"}
    assert files["new"].exists()
    assert files["mid"].exists()


def test_a_unique_file_survives_a_forged_plan(tmp_path: Path) -> None:
    unique = write(tmp_path / "unique.bin", b"one of a kind")
    other = write(tmp_path / "other.bin", b"another kind!")
    forged = [
        PlannedAction("delete", unique, unique, 13, "x"),
        PlannedAction("delete", unique, Path(str(unique).upper()), 13, "x"),
        PlannedAction("delete", unique, other, 13, "x"),
        PlannedAction("delete", other, unique, 13, "x"),
    ]

    results = apply_actions(forged, dry_run=False)

    assert {r.status for r in results} == {"skipped"}
    assert unique.read_bytes() == b"one of a kind"
    assert other.read_bytes() == b"another kind!"


def test_a_target_that_is_a_hard_link_of_the_keeper_is_left_alone(tmp_path: Path) -> None:
    keep = write(tmp_path / "a.bin", b"payload")
    os.link(keep, tmp_path / "b.bin")
    group = DuplicateGroup(
        "x", "sha256", 7, (DuplicateFile(keep, 7, 0), DuplicateFile(tmp_path / "b.bin", 7, 1))
    )

    (result,) = apply_actions(plan_actions([group], keep="first"), dry_run=False)

    assert result.status == "skipped"
    assert (tmp_path / "b.bin").read_bytes() == b"payload"
