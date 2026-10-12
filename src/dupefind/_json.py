"""Serialise a scan report, and optionally action results, to JSON."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import asdict
from typing import Any

from ._actions import ActionResult
from ._types import DuplicateGroup, ScanReport

SCHEMA_VERSION = 1
"""Bumped only when a field is removed or changes meaning. New fields may be added."""


def group_to_dict(group: DuplicateGroup) -> dict[str, Any]:
    """Return a JSON-ready dict for one group."""
    return {
        "digest": group.digest,
        "algorithm": group.algorithm,
        "size": group.size,
        "wasted_bytes": group.wasted_bytes,
        "files": [
            {
                "path": str(item.path),
                "mtime_ns": item.mtime_ns,
                "aliases": [str(alias) for alias in item.aliases],
            }
            for item in group.files
        ],
    }


def report_to_dict(
    report: ScanReport, actions: Iterable[ActionResult] | None = None
) -> dict[str, Any]:
    """Return a JSON-ready dict: ``schema``, ``groups``, ``issues``, ``stats``, ``actions``.

    ``actions`` is ``null`` when no action results are given.
    """
    return {
        "schema": SCHEMA_VERSION,
        "groups": [group_to_dict(group) for group in report.groups],
        "issues": [
            {"path": str(issue.path), "kind": issue.kind, "message": issue.message}
            for issue in report.issues
        ],
        "stats": asdict(report.stats),
        "actions": None
        if actions is None
        else [
            {
                "action": result.planned.action,
                "target": str(result.planned.target),
                "keep": str(result.planned.keep),
                "size": result.planned.size,
                "status": result.status,
                "reason": result.reason,
            }
            for result in actions
        ],
    }


def report_to_json(
    report: ScanReport,
    actions: Iterable[ActionResult] | None = None,
    *,
    indent: int | None = 2,
) -> str:
    """Return the report as a JSON string. See ``report_to_dict`` for the layout."""
    return json.dumps(report_to_dict(report, actions), indent=indent, ensure_ascii=False)
