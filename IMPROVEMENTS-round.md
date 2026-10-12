# dupefind improvement round

Progress:
- [x] Brainstorm ranked improvements (this file)
- [x] Typed results, options and scan issues (`ScanOptions`, `DuplicateGroup`, `ScanReport`)
- [x] Walker: hard-link identity, junctions and symlinks not followed, globs, size limits
- [x] Staging: configurable algorithm and partial size, change detection, progress callback
- [x] Safe actions: plan and apply delete or hardlink, dry run by default, keep policies
- [x] JSON output and CLI (`dupefind PATH...`)
- [x] Docs: README, GUIDE, CHANGELOG, docstrings
- [x] Gates: ruff format, ruff check, mypy --strict, pytest
- [x] Contracts, brute-force oracle on seeded trees, real wheel e2e
- [x] Pull request opened (#2)
- [x] Independent review findings fixed, guard clean
- [x] Read-only targets refused, documented and tested (Windows attribute, POSIX 0444 in WSL)
- [x] Swaps between scan and apply (TOCTOU) refused, with a last re-stat before acting, tested
- [x] Second independent review (junction loops and roots, repeated, cased and nested roots) fixed
- [ ] Gates, guard and PR body refreshed

Every item is additive. `find_duplicates` and `iter_duplicates` keep their names,
their positional `root` argument, `follow_symlinks`, and their return types.

## Starting point

`0.1.0` grouped files by size, a 4 KiB SHA-256 prefix and a full SHA-256. It had no
options beyond `follow_symlinks`, no way to see what was skipped, and two safety
gaps found while reading the walker:

- Hard links to one file were reported as duplicates of each other. Any tool that
  deleted "all but one" of such a group would free no space at best.
- On Windows a directory junction is not a symlink to `os.scandir`, so junctions
  were walked even with `follow_symlinks=False`. A junction pointing back into the
  tree made every file under it look like its own duplicate (the "same directory
  given twice" data-loss caveat both fdupes and jdupes document).

## Sources (fetched 2026-10-12)

- fdupes man page: https://raw.githubusercontent.com/adrianlopezroche/fdupes/master/fdupes.1
  (size, MD5, then byte-by-byte; `-H` "files that point to the same disk area are
  treated as non-duplicates" by default; `-s` follows symlinked directories only on
  request; `-G`/`-L` size bounds; caveat on listing a file as its own duplicate).
- jdupes README: https://codeberg.org/jbruchon/jdupes/raw/branch/master/README.md
  (linked files are non-duplicates "for safety" unless `-H`; zero-length files only
  match with `-z`; the change check before acting on a file guards against TOCTTOU;
  Windows allows at most 1023 hard links per file).
- rmlint man page: https://raw.githubusercontent.com/sahib/rmlint/master/docs/rmlint.1.rst
  (`--no-hardlinked` keeps one file of a hard-linked set; `-F` ignores symlinks;
  `--size` excludes empty files by default; rank criteria such as oldest mtime and
  path for the original to keep).

## Ranked improvements

1. **Hard-link identity.** Files sharing a device and file id (`st_dev`, `st_ino`,
   which Python fills from the NTFS file id on Windows) are one file. By default a
   hard-linked set is reported once, with the other names kept as `aliases`; a set
   made only of links to one file is never a duplicate group. `hardlinks=True`
   restores the old view (fdupes and jdupes `-H`).
2. **Links are not followed by default, junctions included.** Symlinks and Windows
   junctions (reparse tag `IO_REPARSE_TAG_MOUNT_POINT`) are skipped unless
   `follow_symlinks=True`. Every path is also de-duplicated by its normalised real
   path, so overlapping roots or a root given twice (also in another letter case on
   a case-insensitive filesystem) never list a file as its own duplicate.
3. **Typed results.** `DuplicateGroup` (digest, algorithm, size, `files`, `paths`,
   `wasted_bytes`), `DuplicateFile` (path, size, mtime, aliases) and `ScanReport`
   (groups, issues, stats). Frozen dataclasses, fully typed.
4. **Issues instead of silent drops.** Permission errors, vanished files and files
   that changed while being read are recorded as `ScanIssue(path, kind, message)`
   and left out of the results. Change detection re-stats size and mtime after the
   full hash, as jdupes does before acting.
5. **`ScanOptions`.** `algorithm` (any fixed-size `hashlib` algorithm, default
   `sha256` so keys are unchanged), `partial_size`, `min_size`, `max_size`,
   `include_empty`, `include`/`exclude` globs, `follow_symlinks`, `hardlinks`.
   Validated at construction with typed `ValueError`s.
6. **Staging that reads less.** A file no larger than the partial size is hashed
   once and its partial digest is its full digest, so it is never read twice.
7. **Multiple roots, streaming and progress.** `scan(*roots)` and
   `iter_groups(*roots)` take several paths (directories or files). Groups stream
   as they are confirmed. `on_progress` receives a `Progress(stage, done, total)`.
8. **Safe actions.** `plan_actions(groups, action="delete"|"hardlink", keep=...)`
   with keep policies `first`, `oldest`, `newest`, `shortest`; `apply_actions(plan,
   dry_run=True)` acts only with `dry_run=False`. Before each action it re-checks
   that both files exist, are not the same file, still have the scanned size, and
   are byte-for-byte equal. Hard links are created next to the target and moved
   over it atomically. Nothing is ever deleted without the explicit flag.
9. **JSON output.** `report_to_json(report)` with a versioned, documented schema.
10. **CLI.** `dupefind PATH...` prints fdupes-style groups, `--json`, the scan
    options, and `--delete`/`--hardlink` that only print a plan unless `--apply`.
11. **Docs.** Docstrings on every public name, a GUIDE covering policies, actions,
    JSON schema and the CLI, and a CHANGELOG entry.

## Out of scope

Byte-for-byte confirmation during the scan itself (hash equality is the scan
verdict; actions do the byte comparison), a hash cache database, and fuzzy
matching of media files.
