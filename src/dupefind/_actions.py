"""Plan and apply clean-up actions on duplicate groups. Dry run unless told otherwise."""

from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path

from ._apply import check, run
from ._types import (
    Action,
    ActionResult,
    DuplicateFile,
    DuplicateGroup,
    KeepPolicy,
    PlannedAction,
)

ACTIONS: tuple[Action, ...] = ("delete", "hardlink")
KEEP_POLICIES: tuple[KeepPolicy, ...] = ("first", "oldest", "newest", "shortest")


def choose_keeper(group: DuplicateGroup, keep: KeepPolicy = "oldest") -> DuplicateFile:
    """Return the file of ``group`` that ``keep`` says should survive.

    A regular file is always preferred over a symlink (seen with
    ``follow_symlinks``), so the real data is what survives. Ties are broken by
    path, so the choice is deterministic.
    """
    real = [f for f in group.files if not os.path.islink(f.path)]
    files = real or list(group.files)
    if keep == "first":
        return min(files, key=lambda f: str(f.path))
    if keep == "oldest":
        return min(files, key=lambda f: (f.mtime_ns, str(f.path)))
    if keep == "newest":
        return min(files, key=lambda f: (-f.mtime_ns, str(f.path)))
    if keep == "shortest":
        return min(files, key=lambda f: (len(str(f.path)), str(f.path)))
    raise ValueError(f"unknown keep policy {keep!r}; choose one of {', '.join(KEEP_POLICIES)}")


def plan_actions(
    groups: Iterable[DuplicateGroup],
    *,
    action: Action = "delete",
    keep: KeepPolicy = "oldest",
) -> list[PlannedAction]:
    """Plan ``action`` for every copy of every group except the one ``keep`` selects.

    Exactly one file per group is kept, together with its hard-link aliases. Every
    other file, and every alias of it, gets one planned action, so a delete really
    frees the space. Planning touches nothing on disk.
    """
    if action not in ACTIONS:
        raise ValueError(f"unknown action {action!r}; choose one of {', '.join(ACTIONS)}")
    plan: list[PlannedAction] = []
    for group in groups:
        keeper = choose_keeper(group, keep)
        for item in group.files:
            if item is keeper:
                continue
            for target in (item.path, *item.aliases):
                plan.append(PlannedAction(action, target, keeper.path, group.size, group.digest))
    return plan


def apply_actions(plan: Iterable[PlannedAction], *, dry_run: bool = True) -> list[ActionResult]:
    """Carry out a plan. With the default ``dry_run=True`` nothing is changed.

    Each action is verified right before it runs (and in a dry run). The target
    must be a regular, writable file of its own (not a link, junction or read-only
    file); the kept copy must exist; the two must not be the same file, must still
    have the planned size and must be equal byte for byte. Just before the delete or
    the replace, both are stat'ed once more and must still be the very files that
    were compared. A target that is also a kept file in the plan is never touched.
    Anything that fails a check is ``skipped`` with a reason; an OS error while
    acting is ``failed``. Nothing is raised and the next action still runs.
    """
    actions = list(plan)
    keepers = {_norm(item.keep) for item in actions}
    results: list[ActionResult] = []
    for item in actions:
        if _norm(item.target) in keepers:
            results.append(ActionResult(item, "skipped", "target is a kept file"))
            continue
        reason, pinned = check(item)
        if pinned is None:
            results.append(ActionResult(item, "skipped", reason))
        elif dry_run:
            results.append(ActionResult(item, "dry-run"))
        else:
            results.append(run(item, *pinned))
    return results


def _norm(path: Path) -> str:
    return os.path.normcase(os.path.abspath(path))
