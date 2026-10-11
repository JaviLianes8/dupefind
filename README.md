# dupefind

Find duplicate files by staged hashing: group by size, then partial hash, then full hash.

## Install

```
pip install dupefind
```

## Usage

```python
from dupefind import find_duplicates

groups = find_duplicates("path/to/tree")
for digest, paths in groups.items():
    print(digest)
    for path in paths:
        print("  ", path)
```

`find_duplicates(root, *, follow_symlinks=False)` returns a `dict[str, list[Path]]`
keyed by the full content hash. Each value holds two or more paths with identical
content; files with no duplicate are left out. Symlinks are skipped unless
`follow_symlinks` is true.

For large trees, stream the groups instead of building the whole dictionary:

```python
from dupefind import iter_duplicates

for digest, paths in iter_duplicates("path/to/tree"):
    ...
```

The search is read-only. It reads file contents to compare them and never moves,
renames or deletes anything. What to do with a duplicate set is left to you.

### How the staging keeps it fast

Hashing every file would be wasteful, so the work is done in three passes and each
pass only looks at what survived the last:

1. Group files by byte size. A file whose size is unique cannot have a duplicate,
   so it is dropped without ever being opened.
2. For the remaining same-size files, hash only the first block. Files whose
   prefixes differ are separated here, before any full read.
3. Hash in full only the files that still share both a size and a prefix, and keep
   the sets that agree.

## Why

Finding duplicate files is a common chore, but the Python packages for it are
mostly stale: `fastdupes` last shipped in 2015, `dupfinder` in 2010, and `dupe` in
2021. The few that are maintained are command-line tools, not a typed library you
can import. `dupefind` is a small, fully typed, zero-dependency library (standard
`hashlib` only) with a clear read-only API and the staged size, prefix, full hash
strategy that avoids reading files that cannot match. Reach for it when you want
duplicate detection as a function in your own code rather than a separate CLI.

## License

MIT. See [LICENSE](LICENSE).

## Links

- Website: https://lianes8studio.com
- GitHub: https://github.com/JaviLianes8
- LinkedIn: https://www.linkedin.com/in/jlianes/
