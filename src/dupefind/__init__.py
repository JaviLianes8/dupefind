"""Find duplicate files by staged hashing: group by size, then partial hash, then full hash.

Scanning only ever reads files. Clean-up is a separate, explicit step:
``plan_actions`` decides, ``apply_actions`` acts, and only with ``dry_run=False``.
"""

from __future__ import annotations

from ._actions import (
    Action,
    ActionResult,
    KeepPolicy,
    PlannedAction,
    apply_actions,
    choose_keeper,
    plan_actions,
)
from ._find import find_duplicates, iter_duplicates, iter_groups, scan
from ._json import SCHEMA_VERSION, report_to_dict, report_to_json
from ._options import ScanOptions
from ._types import (
    DuplicateFile,
    DuplicateGroup,
    IssueKind,
    Progress,
    ScanIssue,
    ScanReport,
    ScanStats,
)

__version__ = "0.2.0"

__all__ = [
    "SCHEMA_VERSION",
    "Action",
    "ActionResult",
    "DuplicateFile",
    "DuplicateGroup",
    "IssueKind",
    "KeepPolicy",
    "PlannedAction",
    "Progress",
    "ScanIssue",
    "ScanOptions",
    "ScanReport",
    "ScanStats",
    "apply_actions",
    "choose_keeper",
    "find_duplicates",
    "iter_duplicates",
    "iter_groups",
    "plan_actions",
    "report_to_dict",
    "report_to_json",
    "scan",
]
