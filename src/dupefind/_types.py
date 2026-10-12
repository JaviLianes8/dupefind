"""Typed results of a scan: duplicate groups, the issues met and summary counts."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

IssueKind = Literal["permission", "missing", "changed", "error"]
"""Why a path was left out: access denied, gone, modified while read, other OS error."""

Stage = Literal["walk", "partial", "full"]
"""The scan stage a progress report belongs to."""


@dataclass(frozen=True, slots=True)
class DuplicateFile:
    """One file in a duplicate group.

    ``path`` is the name the scan reached first. ``aliases`` lists the other names of
    the very same file (hard links) met during the scan; they share its content and
    its storage, so they are not counted as separate copies. ``mtime_ns`` is the
    modification time in nanoseconds since the epoch, as reported by ``os.stat``.
    """

    path: Path
    size: int
    mtime_ns: int
    aliases: tuple[Path, ...] = ()


@dataclass(frozen=True, slots=True)
class DuplicateGroup:
    """Two or more distinct files with identical content.

    ``digest`` is the hex digest of the whole content with ``algorithm``. ``files``
    is sorted by path and always holds at least two entries.
    """

    digest: str
    algorithm: str
    size: int
    files: tuple[DuplicateFile, ...]

    @property
    def paths(self) -> list[Path]:
        """The first-reached path of every file in the group, in group order."""
        return [item.path for item in self.files]

    @property
    def wasted_bytes(self) -> int:
        """Bytes that would be freed by keeping one copy and removing the rest."""
        return self.size * (len(self.files) - 1)


@dataclass(frozen=True, slots=True)
class ScanIssue:
    """A path the scan could not use, and why. The path is left out of the results."""

    path: Path
    kind: IssueKind
    message: str


@dataclass(frozen=True, slots=True)
class Progress:
    """A progress report: ``done`` of ``total`` items finished in ``stage``.

    During ``walk`` the total is not known yet and equals ``done``. During
    ``partial`` and ``full`` the unit is files, and ``bytes_read`` counts the bytes
    read so far in that stage.
    """

    stage: Stage
    done: int
    total: int
    bytes_read: int = 0


@dataclass(slots=True)
class ScanStats:
    """Counters gathered while scanning."""

    files_seen: int = 0
    candidates: int = 0
    partial_hashed: int = 0
    full_hashed: int = 0
    bytes_read: int = 0
    groups: int = 0
    duplicate_files: int = 0
    wasted_bytes: int = 0


@dataclass(slots=True)
class ScanReport:
    """Everything a scan found: the groups, the skipped paths and the counters."""

    groups: list[DuplicateGroup] = field(default_factory=list)
    issues: list[ScanIssue] = field(default_factory=list)
    stats: ScanStats = field(default_factory=ScanStats)
