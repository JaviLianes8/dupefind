"""Verify one planned action against the disk and carry it out. Refuse on any doubt."""

from __future__ import annotations

import os
import stat

from ._hash import same_content
from ._streams import extra_streams
from ._types import PlannedAction

_MOUNT_POINT = 0xA0000003  # IO_REPARSE_TAG_MOUNT_POINT: a Windows junction


def pin(info: os.stat_result) -> tuple[int, int, int, int, int]:
    """The facts that must not change between the check and the act."""
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_mode)


def check(item: PlannedAction) -> tuple[str, tuple[os.stat_result, os.stat_result] | None]:
    """Return ``("", (kept, target))`` when the action is safe, else a refusal reason.

    ``target`` is stat'ed without following links: it must be a regular, writable
    file of its own, so a link, a junction, a directory or a read-only file is never
    removed or replaced.
    """
    try:
        target = os.lstat(item.target)
    except OSError as exc:
        return f"cannot stat target: {exc}", None
    if stat.S_ISLNK(target.st_mode) or getattr(target, "st_reparse_tag", 0) == _MOUNT_POINT:
        return "target is a link; only regular files are acted on", None
    if not stat.S_ISREG(target.st_mode):
        return "target is not a regular file", None
    if not target.st_mode & stat.S_IWUSR or not os.access(item.target, os.W_OK):
        return "target is read-only", None
    try:
        kept = os.stat(item.keep)
    except OSError as exc:
        return f"cannot stat the kept copy: {exc}", None
    if not stat.S_ISREG(kept.st_mode):
        return "the kept copy is not a regular file", None
    if os.path.samestat(kept, target):
        return "already the same file as the kept copy", None
    if kept.st_size != item.size or target.st_size != item.size:
        return "size changed since the scan", None
    if item.action == "hardlink" and kept.st_dev != target.st_dev:
        return "on a different device than the kept copy", None
    try:
        equal = same_content(item.keep, item.target)
    except OSError as exc:
        return f"cannot compare: {exc}", None
    if not equal:
        return "content differs from the kept copy", None
    try:
        streams = extra_streams(item.target)
    except OSError as exc:
        return f"cannot list data streams: {exc}", None
    if streams:
        return f"target has extra data streams: {', '.join(streams)}", None
    return "", (kept, target)


def unchanged(item: PlannedAction, kept: os.stat_result, target: os.stat_result) -> str:
    """Re-stat both files right before acting; return a reason if either moved on."""
    try:
        now_target = os.lstat(item.target)
        now_kept = os.stat(item.keep)
    except OSError as exc:
        return f"changed before acting: {exc}"
    if pin(now_target) != pin(target):
        return "target was replaced or modified before acting"
    if pin(now_kept) != pin(kept):
        return "the kept copy was replaced or modified before acting"
    return ""
