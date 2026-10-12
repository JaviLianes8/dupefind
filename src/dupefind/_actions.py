"""Plan and apply clean-up actions on duplicate groups. Dry run unless told otherwise."""

from __future__ import annotations

import os
import secrets
import stat
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ._hash import same_content
from ._types import DuplicateFile, DuplicateGroup

Action = Literal["delete", "hardlink"]
"""``delete`` removes the extra copies; ``hardlink`` replaces them with links to the kept one."""

KeepPolicy = Literal["first", "oldest", "newest", "shortest"]
"""Which copy of a group survives: first by path, oldest or newest mtime, shortest path."""

Status = Literal["done", "dry-run", "skipped", "failed"]

ACTIONS: tuple[Action, ...] = ("delete", "hardlink")
KEEP_POLICIES: tuple[KeepPolicy, ...] = ("first", "oldest", "newest", "shortest")


@dataclass(frozen=True, slots=True)
class PlannedAction:
    """Do ``action`` to ``target``, whose content equals the kept file ``keep``."""

    action: Action
    target: Path
    keep: Path
    size: int
    digest: str


@dataclass(frozen=True, slots=True)
class ActionResult:
    """What happened to one planned action, with the reason when it was not done."""

    planned: PlannedAction
    status: Status
    reason: str = ""


def choose_keeper(group: DuplicateGroup, keep: KeepPolicy = "oldest") -> DuplicateFile:
    """Return the file of ``group`` that ``keep`` says should survive.

    Ties are broken by path, so the choice is deterministic.
    """
    files = group.files
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

    Each action is re-checked right before it runs (and in a dry run): the kept file
    and the target must both exist, must not be the same file, must still have the
    planned size, and must be equal byte for byte. A target that is also a kept file
    in the plan is never touched. Failures are reported, never raised, and the next
    action still runs.
    """
    actions = list(plan)
    keepers = {_norm(item.keep) for item in actions}
    results: list[ActionResult] = []
    for item in actions:
        if _norm(item.target) in keepers:
            results.append(ActionResult(item, "skipped", "target is a kept file"))
            continue
        reason = _check(item)
        if reason:
            results.append(ActionResult(item, "skipped", reason))
        elif dry_run:
            results.append(ActionResult(item, "dry-run"))
        else:
            results.append(_run(item))
    return results


def _check(item: PlannedAction) -> str:
    try:
        kept = os.stat(item.keep)
        target = os.stat(item.target)
    except OSError as exc:
        return f"cannot stat: {exc}"
    if not (stat.S_ISREG(kept.st_mode) and stat.S_ISREG(target.st_mode)):
        return "not a regular file"
    if os.path.samestat(kept, target):
        return "already the same file as the kept copy"
    if kept.st_size != item.size or target.st_size != item.size:
        return "size changed since the scan"
    if item.action == "hardlink" and kept.st_dev != target.st_dev:
        return "on a different device than the kept copy"
    try:
        equal = same_content(item.keep, item.target)
    except OSError as exc:
        return f"cannot compare: {exc}"
    return "" if equal else "content differs from the kept copy"


def _run(item: PlannedAction) -> ActionResult:
    try:
        if item.action == "delete":
            os.remove(item.target)
        else:
            _relink(item.keep, item.target)
    except OSError as exc:
        return ActionResult(item, "failed", str(exc))
    return ActionResult(item, "done")


def _relink(keep: Path, target: Path) -> None:
    """Replace ``target`` with a hard link to ``keep`` without a moment of absence."""
    temp = target.with_name(f".{target.name}.{secrets.token_hex(6)}.dupefind")
    os.link(keep, temp)
    try:
        os.replace(temp, target)
    except OSError:
        os.remove(temp)
        raise


def _norm(path: Path) -> str:
    return os.path.normcase(os.path.abspath(path))
