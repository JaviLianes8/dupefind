# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0]

### Added

- `scan` and `iter_groups` take several roots (directories or files) and return
  typed results: `ScanReport`, `DuplicateGroup`, `DuplicateFile`, `ScanIssue`,
  `ScanStats`, `Progress`.
- `ScanOptions`: hash algorithm, partial hash size, size bounds, empty files,
  include and exclude globs, link following and hard-link reporting.
- Progress callback for the walk, partial and full stages.
- Files that change while being read, unreadable files and missing paths are
  reported as issues instead of being dropped silently.
- `plan_actions`, `apply_actions` and `choose_keeper`: delete or hard link extra
  copies with a keep policy (first, oldest, newest, shortest). Dry run by
  default; every action re-checks size, identity and byte-for-byte equality,
  stats both files again just before acting, moves the target aside and checks it
  once more before removing it, and refuses links, junctions, read-only targets
  and targets with extra NTFS data streams.
- `report_to_json` and `report_to_dict` with a versioned schema.
- The `dupefind` command line tool and `python -m dupefind`.
- GUIDE.md.

### Changed

- Hard links to one file are no longer reported as duplicates of each other;
  they are merged into one file and listed as `aliases`. Pass
  `ScanOptions(hardlinks=True)` for the previous view.
- Files no larger than the partial hash size are read once instead of twice.

### Fixed

- Windows junctions were walked even with `follow_symlinks=False`, so a junction
  into the tree listed files as duplicates of themselves.
- Overlapping or repeated roots no longer list a file twice.

## [0.1.0]

- First release.
- `find_duplicates` returns duplicate files grouped by their full content hash.
- `iter_duplicates` streams the same groups one at a time.
- Staged matching compares files by size, then a partial hash, then a full hash,
  so unique files are never read in full.
- Read-only by design: the search reads file contents and never modifies, moves
  or deletes anything on disk.
