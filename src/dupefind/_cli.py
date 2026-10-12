"""Command line entry point: ``dupefind PATH...``."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from typing import NoReturn, TextIO

from . import __version__
from ._actions import KEEP_POLICIES, Action, KeepPolicy, apply_actions, plan_actions
from ._cli_output import print_actions, print_groups, print_summary
from ._find import scan
from ._json import report_to_json
from ._options import ScanOptions

_EXAMPLES = """\
examples:
  dupefind ~/Pictures                    list duplicate groups
  dupefind a b --min-size 1M --json      scan two trees, files of 1 MiB or more, JSON out
  dupefind . --exclude .git --exclude "*.tmp"
  dupefind . --delete --keep oldest      show what would be deleted (dry run)
  dupefind . --delete --keep oldest --apply   really delete the newer copies
  dupefind . --hardlink --apply          replace copies with hard links to one file

Nothing is changed unless --apply is given with --delete or --hardlink.
Exit status: 0 on success, 1 on an error or a failed action.
"""


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        self.exit(1, f"{self.prog}: error: {message}\n")


def parse_size(text: str) -> int:
    """Parse a byte count with an optional K, M, G or T suffix (powers of 1024)."""
    units = {"": 1, "K": 1 << 10, "M": 1 << 20, "G": 1 << 30, "T": 1 << 40}
    raw = text.strip().upper().removesuffix("B").removesuffix("I")
    suffix = raw[-1:] if raw[-1:] in units else ""
    number = raw[: len(raw) - len(suffix)]
    if not number.isdigit():
        raise argparse.ArgumentTypeError(f"invalid size: {text!r}")
    return int(number) * units[suffix]


def build_parser() -> argparse.ArgumentParser:
    """Return the argument parser used by ``main``."""
    parser = _Parser(
        prog="dupefind",
        description="Find duplicate files by size, then partial hash, then full hash.",
        epilog=_EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    add = parser.add_argument
    add("paths", nargs="+", metavar="PATH", help="directories or files to scan")
    add("--version", action="version", version=f"%(prog)s {__version__}")
    add("--json", action="store_true", help="print one JSON document instead of text")
    add("--algorithm", default="sha256", help="hashlib algorithm (default: sha256)")
    add("--partial-size", type=parse_size, default=4096, help="prefix bytes hashed first")
    add("--min-size", type=parse_size, default=0, help="ignore smaller files (e.g. 10K)")
    add("--max-size", type=parse_size, default=None, help="ignore larger files (e.g. 2G)")
    add("--no-empty", action="store_true", help="ignore zero-length files")
    add("--include", action="append", default=[], metavar="GLOB", help="only these files")
    add("--exclude", action="append", default=[], metavar="GLOB", help="skip files and dirs")
    add("--follow-symlinks", action="store_true", help="follow symlinks and junctions")
    add("--hardlinks", action="store_true", help="report hard links to one file as copies")
    act = parser.add_mutually_exclusive_group()
    act.add_argument("--delete", action="store_true", help="plan deleting all but one copy")
    act.add_argument("--hardlink", action="store_true", help="plan linking copies to one")
    add("--keep", choices=KEEP_POLICIES, default="oldest", help="copy to keep (default: oldest)")
    add("--apply", action="store_true", help="carry out --delete or --hardlink")
    add("-q", "--quiet", action="store_true", help="no summary or issues on stderr")
    return parser


def main(argv: Sequence[str] | None = None, *, stdout: TextIO | None = None) -> int:
    """Run the command line tool and return its exit status."""
    out = stdout if stdout is not None else sys.stdout
    parser = build_parser()
    args = parser.parse_args(argv)
    action: Action | None = "delete" if args.delete else "hardlink" if args.hardlink else None
    if args.apply and action is None:
        parser.error("--apply needs --delete or --hardlink")
    missing = [path for path in args.paths if not os.path.exists(path)]
    if missing:
        parser.error(f"no such file or directory: {missing[0]}")
    try:
        options = ScanOptions(
            algorithm=args.algorithm,
            partial_size=args.partial_size,
            min_size=args.min_size,
            max_size=args.max_size,
            include_empty=not args.no_empty,
            include=tuple(args.include),
            exclude=tuple(args.exclude),
            follow_symlinks=args.follow_symlinks,
            hardlinks=args.hardlinks,
        )
    except ValueError as exc:
        parser.error(str(exc))
    report = scan(*args.paths, options=options)
    results = None
    if action is not None:
        keep: KeepPolicy = args.keep
        plan = plan_actions(report.groups, action=action, keep=keep)
        results = apply_actions(plan, dry_run=not args.apply)
    if args.json:
        out.write(report_to_json(report, results) + "\n")
    else:
        print_groups(report, out)
        if results is not None:
            print_actions(results, out)
    if not args.quiet:
        print_summary(report, results, sys.stderr)
    failed = results is not None and any(r.status == "failed" for r in results)
    return 1 if failed else 0
