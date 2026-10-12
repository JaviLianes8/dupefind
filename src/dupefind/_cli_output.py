"""Plain-text rendering for the command line tool."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TextIO

from ._types import ActionResult, ScanReport


def print_groups(report: ScanReport, out: TextIO) -> None:
    """Print each group as a header line, its paths, then a blank line."""
    for group in report.groups:
        count = len(group.files)
        header = f"# {group.size} bytes x {count} files, {group.algorithm}:{group.digest}"
        out.write(header + "\n")
        for item in group.files:
            out.write(f"{item.path}\n")
            for alias in item.aliases:
                out.write(f"  = {alias}\n")
        out.write("\n")


def print_actions(results: Sequence[ActionResult], out: TextIO) -> None:
    """Print one line per action: status, action, target and the kept copy."""
    for result in results:
        item = result.planned
        line = f"[{result.status}] {item.action} {item.target} (keep {item.keep})"
        if result.reason:
            line += f": {result.reason}"
        out.write(line + "\n")


def print_summary(report: ScanReport, results: Sequence[ActionResult] | None, err: TextIO) -> None:
    """Print skipped paths and a one-line summary to the error stream."""
    for issue in report.issues:
        err.write(f"dupefind: skipped {issue.path} ({issue.kind}): {issue.message}\n")
    stats = report.stats
    line = (
        f"dupefind: {stats.groups} groups, {stats.duplicate_files} files, "
        f"{stats.wasted_bytes} bytes reclaimable, {len(report.issues)} issues"
    )
    if results is not None:
        counts: dict[str, int] = {}
        for result in results:
            counts[result.status] = counts.get(result.status, 0) + 1
        line += "; actions: " + ", ".join(f"{n} {s}" for s, n in sorted(counts.items()))
        if not results:
            line += "none"
    err.write(line + "\n")
