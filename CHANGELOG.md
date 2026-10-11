# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0]

- First release.
- `find_duplicates` returns duplicate files grouped by their full content hash.
- `iter_duplicates` streams the same groups one at a time.
- Staged matching compares files by size, then a partial hash, then a full hash,
  so unique files are never read in full.
- Read-only by design: the search reads file contents and never modifies, moves
  or deletes anything on disk.
