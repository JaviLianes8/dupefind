"""Carry out one verified action so that the data always exists under some name.

The target is first renamed aside to a random name next to it and checked to be
the file that was compared. Only then is it removed (delete), or a hard link to
the kept file is created at the freed name (hardlink) before the aside copy is
removed. While this happens the kept file is held open, which on Windows stops
anyone deleting or renaming it. Anything unexpected puts the target back.
"""

from __future__ import annotations

import os
import secrets
import stat
from pathlib import Path

from ._apply import pin, unchanged
from ._types import ActionResult, PlannedAction


def run(item: PlannedAction, kept: os.stat_result, target: os.stat_result) -> ActionResult:
    """Act on a checked item after last identity checks. Never raises ``OSError``."""
    try:
        hold = open(item.keep, "rb")  # noqa: SIM115 - held across the whole act
    except OSError as exc:
        return ActionResult(item, "skipped", f"cannot open the kept copy: {exc}")
    with hold:
        reason = unchanged(item, kept, target)
        if reason:
            return ActionResult(item, "skipped", reason)
        aside = _aside_name(item.target)
        try:
            os.rename(item.target, aside)
        except OSError as exc:
            return ActionResult(item, "failed", str(exc))
        reason = _still_the_same(item, aside, kept, target)
        if reason:
            return ActionResult(item, "skipped", reason + _restore(aside, item.target))
        try:
            if item.action == "hardlink":
                _link_in_place(item.keep, item.target, kept)
        except OSError as exc:
            return ActionResult(item, "failed", str(exc) + _restore(aside, item.target))
        try:
            os.remove(aside)
        except OSError as exc:
            return ActionResult(item, "failed", f"{exc}; the old copy is still at {aside}")
    return ActionResult(item, "done")


def _aside_name(target: Path) -> Path:
    return target.with_name(f".{target.name}.{secrets.token_hex(6)}.dupefind")


def _still_the_same(
    item: PlannedAction, aside: Path, kept: os.stat_result, target: os.stat_result
) -> str:
    try:
        moved = os.lstat(aside)
        now_kept = os.stat(item.keep)
    except OSError as exc:
        return f"changed while acting: {exc}"
    if pin(moved) != pin(target):
        return "target was replaced or modified before acting"
    if pin(now_kept) != pin(kept):
        return "the kept copy was replaced or modified before acting"
    return ""


def _link_in_place(keep: Path, target: Path, kept: os.stat_result) -> None:
    """Create a hard link to the real kept file at the (now free) target name."""
    os.link(os.path.realpath(keep), target)  # fails if anything appeared there
    made = os.lstat(target)
    if not stat.S_ISREG(made.st_mode) or not os.path.samestat(made, kept):
        _drop_link(target, keep)
        raise OSError(f"the new link at {target} is not the kept file")


def _restore(aside: Path, target: Path) -> str:
    """Put the aside copy back without overwriting anything; describe a failure."""
    try:
        if os.name == "nt":
            os.rename(aside, target)  # never replaces an existing file on Windows
        else:
            os.link(aside, target)  # never replaces an existing file
            os.remove(aside)
    except OSError as exc:
        return f"; could not put it back ({exc}), it is at {aside}"
    return ""


def _drop_link(link: Path, keep: Path) -> None:
    """Remove a link to the kept file, even when the kept file is read-only.

    The read-only flag belongs to the file, so it is cleared just long enough to
    remove the extra name and then put back on the kept file.
    """
    try:
        os.remove(link)
    except PermissionError:
        mode = os.lstat(link).st_mode
        if mode & stat.S_IWUSR:
            raise
        os.chmod(link, mode | stat.S_IWUSR)
        try:
            os.remove(link)
        finally:
            os.chmod(keep, mode)
