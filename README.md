# dupefind

Find duplicate files by staged hashing: group by size, then partial hash, then full hash.

A small, fully typed library with no dependencies (standard `hashlib` only) and a
command line tool. Scanning only reads files. Clean-up is a separate, explicit step
that is a dry run unless you say otherwise.

## Install

```
pip install dupefind
```

## Quick start

```python
from dupefind import scan

report = scan("photos/import", "photos/library")
for group in report.groups:
    print(group.size, group.digest)
    for path in group.paths:
        print("  ", path)
for issue in report.issues:  # unreadable, vanished or changed while reading
    print("skipped", issue.path, issue.kind)
```

The original interface still works and returns `dict[str, list[Path]]` keyed by
the SHA-256 of the content:

```python
from dupefind import find_duplicates, iter_duplicates

groups = find_duplicates("path/to/tree")
for digest, paths in iter_duplicates("path/to/tree"):
    ...
```

## Options

```python
from dupefind import ScanOptions, iter_groups

options = ScanOptions(
    algorithm="blake2b",     # any fixed-size hashlib algorithm, default sha256
    partial_size=64 * 1024,  # bytes hashed before any full read
    min_size=1,              # leave empty files alone
    exclude=(".git", "*.tmp"),
)
for group in iter_groups("data", options=options, on_progress=print):
    ...
```

Safe defaults, in line with fdupes, jdupes and rmlint:

- **Hard links are one file.** Several names of the same file are merged and kept
  in `aliases`; a set made only of hard links is never a duplicate group. Set
  `hardlinks=True` to list every name.
- **Links are not followed.** Symlinks and Windows junctions found while walking
  are skipped unless `follow_symlinks=True`. Paths you pass in are always used.
- **A file is never its own duplicate.** Overlapping roots, a root given twice, a
  root in another letter case, or a link loop never list one file twice.
- **Changes are caught.** A file whose size or modification time changes while it
  is read is left out and reported.
- **Errors are reported, not raised.** Permission errors and vanished files become
  `ScanIssue` entries.

## Cleaning up

```python
from dupefind import apply_actions, plan_actions, scan

plan = plan_actions(scan("photos").groups, action="delete", keep="oldest")
for result in apply_actions(plan):               # dry run: nothing changes
    print(result.status, result.planned.target)
apply_actions(plan, dry_run=False)               # now it happens
```

`keep` is `first`, `oldest`, `newest` or `shortest`. `action="hardlink"` replaces
each copy with a hard link to the kept file instead. Right before acting, every
pair is checked again: both files exist, are not the same file, have the scanned
size, and are equal byte for byte. Anything else is skipped and reported.

## Command line

```
dupefind ~/Pictures                       # list duplicate groups
dupefind a b --min-size 1M --json         # two trees, JSON report
dupefind . --exclude .git --exclude "*.tmp"
dupefind . --delete --keep oldest         # show the plan (dry run)
dupefind . --delete --keep oldest --apply # really delete the other copies
dupefind . --hardlink --apply             # link copies to one file
```

Nothing changes unless `--apply` is given with `--delete` or `--hardlink`. A
summary and any skipped paths go to stderr. Exit status is 0 on success and 1 on
an error or a failed action.

See [GUIDE.md](GUIDE.md) for the staging, every option, the JSON schema and the
safety checks in detail.

## Why

Finding duplicate files is a common chore, but the Python packages for it are
mostly stale: `fastdupes` last shipped in 2015, `dupfinder` in 2010, and `dupe` in
2021. The few that are maintained are command-line tools, not a typed library you
can import. `dupefind` is both: a typed API with safe link handling and explicit,
verified clean-up, and a CLI for the shell.

## License

MIT. See [LICENSE](LICENSE).

## Links

- Website: https://lianes8studio.com
- GitHub: https://github.com/JaviLianes8
- LinkedIn: https://www.linkedin.com/in/jlianes/
